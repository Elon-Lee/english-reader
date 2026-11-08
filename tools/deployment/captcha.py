"""Build and install the internal Tianai service without exposing app secrets."""
import shlex
import subprocess


def build_assets(job, root):
    result = subprocess.run(["bash", str(root / "services/captcha/build.sh")], cwd=root,
                            text=True, capture_output=True, timeout=900)
    if result.returncode:
        job.write((result.stdout + result.stderr)[-5000:])
        prerequisite = next((line.split("CAPTCHA_JDK_ERROR:", 1)[1].strip()
                             for line in (result.stdout + result.stderr).splitlines() if "CAPTCHA_JDK_ERROR:" in line), "")
        if prerequisite:
            raise ValueError(prerequisite)
        raise ValueError("验证码服务构建或测试失败")
    artifact = root / "services/captcha/target/shiyue-captcha-1.0.0.jar"
    if not artifact.is_file():
        raise ValueError("验证码服务构建产物缺失")
    job.write("验证码服务构建与测试通过")


def install_script(target, release, runtime_image):
    root = shlex.quote(target["remote_root"])
    source = shlex.quote(target["remote_root"] + "/releases/" + release + "/services/captcha")
    image = shlex.quote("shiyue-captcha:" + release)
    config_code = """from pathlib import Path
import os,secrets
path=Path('/config/saas.env')
lines=path.read_text().splitlines()
values=dict(line.split('=',1) for line in lines if '=' in line and not line.startswith('#'))
secret=values.get('SHIYUE_CAPTCHA_SECRET','')
if len(secret)<32:
    secret=secrets.token_urlsafe(48)
    lines=[line for line in lines if not line.startswith('SHIYUE_CAPTCHA_SECRET=')]
    lines.append('SHIYUE_CAPTCHA_SECRET='+secret)
    temporary=path.with_suffix('.captcha-tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream: stream.write('\\n'.join(lines)+'\\n')
    os.replace(temporary,path)
env=Path('/config/captcha.env')
fd=os.open(env,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as stream: stream.write('SHIYUE_CAPTCHA_SECRET='+secret+'\\n')
os.chmod(path,0o600)
os.chmod(env,0o600)
"""
    return f"""set -euo pipefail
docker run --rm --network none -v {root}/shared/config:/config:rw,z {shlex.quote(runtime_image)} python3 -c {shlex.quote(config_code)}
if ! docker image inspect eclipse-temurin:21-jre-jammy >/dev/null 2>&1; then
  if docker pull m.daocloud.io/docker.io/library/eclipse-temurin:21-jre-jammy; then
    docker tag m.daocloud.io/docker.io/library/eclipse-temurin:21-jre-jammy eclipse-temurin:21-jre-jammy
  else docker pull eclipse-temurin:21-jre-jammy; fi
fi
docker build -t {image} {source}
candidate=shiyue-captcha-candidate
previous=shiyue-captcha-previous
docker rm -f "$candidate" >/dev/null 2>&1 || true
docker run -d --name "$candidate" --network host --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --env-file {root}/shared/config/captcha.env -e SERVER_PORT=18081 {image} >/dev/null
ready=0
for attempt in $(seq 1 45); do
  if curl --fail --silent http://127.0.0.1:18081/health | grep -q '"ok"'; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != 1 ]; then docker logs --tail 80 "$candidate" >&2; docker rm -f "$candidate" >/dev/null; exit 4; fi
docker rm -f "$candidate" >/dev/null
docker rm -f "$previous" >/dev/null 2>&1 || true
had_previous=0
if docker inspect shiyue-captcha >/dev/null 2>&1; then
  docker stop shiyue-captcha >/dev/null
  docker rename shiyue-captcha "$previous"
  had_previous=1
fi
rollback() {{
  status=$?
  if [ "$status" != 0 ]; then
    docker rm -f shiyue-captcha >/dev/null 2>&1 || true
    if [ "$had_previous" = 1 ]; then docker rename "$previous" shiyue-captcha; docker start shiyue-captcha >/dev/null; fi
  fi
}}
trap rollback EXIT
docker run -d --name shiyue-captcha --restart unless-stopped --network host --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --env-file {root}/shared/config/captcha.env {image} >/dev/null
ready=0
for attempt in $(seq 1 45); do
  if curl --fail --silent http://127.0.0.1:18080/health | grep -q '"ok"'; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
trap - EXIT
docker rm -f "$previous" >/dev/null 2>&1 || true
echo SHIYUE_CAPTCHA_READY
"""
