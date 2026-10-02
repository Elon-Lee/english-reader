#!/usr/bin/env python3
"""Versioned code deployment and finished-resource synchronization."""
import gzip,hashlib,ipaddress,json,os,re,shlex,shutil,sqlite3,subprocess,tarfile,tempfile,threading,time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/".local/library.sqlite3"
STATE=ROOT/".local/deployment"
LOGS=STATE/"logs";KNOWN_HOSTS=STATE/"known_hosts"
KEYS=STATE/"keys"
EXPECT=ROOT/"tools/deployment/ssh_expect.exp"
RUNTIME=STATE/"runtime";TLS=STATE/"tls"
RUNTIME_IMAGE="shiyue-reader-runtime:20260930-1"
TASK_LOCK=threading.Lock();MEMORY_PASSWORDS={}

def now():return datetime.now().astimezone().isoformat(timespec="seconds")
def connect():
    from library_db import connect as library_connect
    return library_connect()

def keychain_service(target):return f"shiyue-deploy:{target['username']}@{target['host']}:{target['port']}"
def save_password(target,password):
    MEMORY_PASSWORDS[target["id"]]=password
    if shutil.which("security"):
        subprocess.run(["security","add-generic-password","-U","-a",target["username"],"-s",keychain_service(target),"-w"],input=password+"\n",text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def load_password(target):
    if target["id"] in MEMORY_PASSWORDS:return MEMORY_PASSWORDS[target["id"]]
    if shutil.which("security"):
        result=subprocess.run(["security","find-generic-password","-a",target["username"],"-s",keychain_service(target),"-w"],text=True,capture_output=True)
        if result.returncode==0:return result.stdout.strip()
    return ""

def get_target():
    db=connect();row=db.execute("SELECT * FROM deployment_targets WHERE id=1").fetchone();db.close();return dict(row) if row else None
def save_target(data,password=""):
    host=str(data.get("host","")).strip();username=str(data.get("username","root")).strip() or "root"
    if not host:raise ValueError("请输入SSH地址")
    port=max(1,min(65535,int(data.get("port",22))));remote_root=str(data.get("remoteRoot","/srv/shiyue")).strip() or "/srv/shiyue"
    service_port=max(1,min(65535,int(data.get("servicePort",8765))));stamp=now();db=connect()
    db.execute("INSERT INTO deployment_targets(id,name,host,port,username,remote_root,service_port,install_recording,created_at,updated_at) VALUES(1,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,host=excluded.host,port=excluded.port,username=excluded.username,remote_root=excluded.remote_root,service_port=excluded.service_port,install_recording=excluded.install_recording,updated_at=excluded.updated_at",
      (str(data.get("name","远程服务器")),host,port,username,remote_root,service_port,1 if data.get("installRecording",True) else 0,stamp,stamp));db.commit();row=dict(db.execute("SELECT * FROM deployment_targets WHERE id=1").fetchone());db.close()
    if password:save_password(row,password)
    return public_target(row)
def public_target(row):
    if not row:return None
    result=dict(row);key=KEYS/f"target-{row['id']}-ed25519";result["passwordConfigured"]=bool(load_password(row) or key.exists());result["keyConfigured"]=key.exists();result.pop("created_at",None);return result

class Job:
    def __init__(self,kind):
        LOGS.mkdir(parents=True,exist_ok=True);stamp=now();db=connect();cur=db.execute("INSERT INTO deployment_jobs(kind,status,progress,step,log_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(kind,"queued",0,"等待开始","",stamp,stamp));self.id=cur.lastrowid;self.log=LOGS/f"{self.id}.log";db.execute("UPDATE deployment_jobs SET log_path=? WHERE id=?",(str(self.log),self.id));db.commit();db.close();self.write(f"任务 #{self.id} · {kind} · {stamp}")
    def update(self,progress,step,status="running",**extra):
        fields={"progress":int(progress),"step":step,"status":status,"updated_at":now(),**extra};db=connect();db.execute("UPDATE deployment_jobs SET "+",".join(f"{key}=?" for key in fields)+" WHERE id=?",[*fields.values(),self.id]);db.commit();db.close();self.write(f"[{progress:3}%] {step}")
    def write(self,text):
        self.log.parent.mkdir(parents=True,exist_ok=True)
        with self.log.open("a",encoding="utf-8") as output:
            for line in str(text).rstrip().splitlines() or [""]:output.write(f"{datetime.now().strftime('%H:%M:%S')} {line}\n")
    def complete(self,result=None,step="完成"):
        self.update(100,step,"complete",result_json=json.dumps(result or {},ensure_ascii=False),error="")
    def fail(self,error):self.update(100,"失败","failed",error=str(error));self.write(f"ERROR: {error}")

class Remote:
    def __init__(self,target,job):
        self.t=target;self.job=job;self.password=load_password(target);self.key=KEYS/f"target-{target['id']}-ed25519"
        STATE.mkdir(parents=True,exist_ok=True);KEYS.mkdir(parents=True,exist_ok=True);KNOWN_HOSTS.touch(exist_ok=True)
        if not self.password and not self.key.exists():raise ValueError("没有可用SSH密码或部署密钥，请重新保存远程配置")
    def ssh_options(self,use_key=True):
        options=["-p",str(self.t["port"]),"-o",f"UserKnownHostsFile={KNOWN_HOSTS}","-o","StrictHostKeyChecking=accept-new","-o","ConnectTimeout=15"]
        if use_key and self.key.exists():options += ["-i",str(self.key),"-o","IdentitiesOnly=yes"]
        return options
    def base_ssh(self,use_key=True):return ["ssh",*self.ssh_options(use_key),f"{self.t['username']}@{self.t['host']}"]
    def execute(self,args,redact=False):
        env=dict(os.environ,SHIYUE_SSH_PASSWORD=self.password);command=[str(EXPECT),*map(str,args)];self.job.write("$ "+("[受保护命令]" if redact else " ".join(shlex.quote(str(x)) for x in args)))
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        lines=[]
        for line in process.stdout:lines.append(line);self.job.write(line.rstrip())
        code=process.wait()
        if code:raise RuntimeError(f"远程命令失败，返回码 {code}")
        return "".join(lines)
    def ssh(self,script):return self.execute([*self.base_ssh(),"bash","-lc",shlex.quote(script)])
    def scp(self,local,remote):
        options=self.ssh_options();options[0:2]=["-P",str(self.t["port"])]
        return self.execute(["scp",*options,str(local),f"{self.t['username']}@{self.t['host']}:{remote}"])
    def scp_from(self,remote,local):
        options=self.ssh_options();options[0:2]=["-P",str(self.t["port"])]
        Path(local).parent.mkdir(parents=True,exist_ok=True)
        return self.execute(["scp",*options,f"{self.t['username']}@{self.t['host']}:{remote}",str(local)])
    def sync_tree_package(self,source,destination,backup_dir,manifest,remote_manifest,progress=None):
        """Upload an offline incremental tar package without using rsync protocol."""
        progress=progress or {"package":40,"upload":48,"apply":74}
        current_copy=STATE/f"remote-{self.t['id']}-content.json"
        remote_copy=f"/tmp/shiyue-current-content-{self.t['id']}.json"
        self.ssh(
            f"if [ -f {shlex.quote(remote_manifest)} ]; then "
            f"cp {shlex.quote(remote_manifest)} {shlex.quote(remote_copy)}; "
            f"else printf '%s' '{{\"files\":[]}}' > {shlex.quote(remote_copy)}; fi"
        )
        self.scp_from(remote_copy,current_copy)
        try:previous=json.loads(current_copy.read_text(encoding="utf-8"))
        except Exception:previous={"files":[]}
        latest=json.loads(Path(manifest).read_text(encoding="utf-8"))
        old_files={item["path"]:item for item in previous.get("files",[]) if item.get("path")}
        new_files={item["path"]:item for item in latest.get("files",[]) if item.get("path")}
        changed=[path for path,item in new_files.items() if path not in old_files or old_files[path].get("size")!=item.get("size") or old_files[path].get("mtime")!=item.get("mtime")]
        removed=[path for path in old_files if path not in new_files]
        package=STATE/f"{latest['revision']}.resources.tar"
        changed_list=STATE/f"{latest['revision']}.changed.txt"
        removed_list=STATE/f"{latest['revision']}.removed.txt"
        changed_list.write_text("".join(f"{path}\n" for path in changed),encoding="utf-8")
        removed_list.write_text("".join(f"{path}\n" for path in removed),encoding="utf-8")
        transfer_size=sum(new_files[path].get("size",0) for path in changed)
        self.job.write(f"增量清单：新增或修改 {len(changed)} 个，删除 {len(removed)} 个，需上传 {transfer_size/1024/1024:.1f} MiB")
        remote_package=f"/tmp/{package.name}"
        remote_changed=f"/tmp/{changed_list.name}"
        remote_removed=f"/tmp/{removed_list.name}"
        if changed:
            self.job.update(progress["package"],f"本机打包增量资源（{transfer_size/1024/1024:.1f} MiB）")
            with tarfile.open(package,"w",dereference=True) as archive:
                for relative in changed:
                    archive.add(Path(source)/relative,arcname=relative,recursive=False)
            self.job.write(f"离线资源包：{package.name} · {package.stat().st_size/1024/1024:.1f} MiB")
            self.job.update(progress["upload"],"上传离线增量资源包")
            self.scp(package,remote_package)
        self.scp(changed_list,remote_changed);self.scp(removed_list,remote_removed)
        self.job.update(progress["apply"],"远程备份并应用增量资源")
        apply_script=f"""set -euo pipefail
mkdir -p {shlex.quote(destination)} {shlex.quote(backup_dir)}
backup_file() {{
  rel="$1"
  [ -n "$rel" ] || return 0
  case "/$rel/" in *"/../"*|*"/./"*) echo "非法资源路径: $rel" >&2; exit 2;; esac
  src={shlex.quote(destination)}/"$rel"
  dst={shlex.quote(backup_dir)}/"$rel"
  if [ -f "$src" ]; then mkdir -p "$(dirname "$dst")"; cp -p "$src" "$dst"; fi
}}
while IFS= read -r rel; do backup_file "$rel"; done < {shlex.quote(remote_changed)}
while IFS= read -r rel; do backup_file "$rel"; done < {shlex.quote(remote_removed)}
{f'tar -xf {shlex.quote(remote_package)} -C {shlex.quote(destination)}' if changed else ':'}
while IFS= read -r rel; do [ -n "$rel" ] && rm -f {shlex.quote(destination)}/"$rel"; done < {shlex.quote(remote_removed)}
find {shlex.quote(destination)} -depth -type d -empty -delete 2>/dev/null || true
rm -f {shlex.quote(remote_copy)} {shlex.quote(remote_package)} {shlex.quote(remote_changed)} {shlex.quote(remote_removed)}
"""
        self.ssh(apply_script)
        for path in (package,changed_list,removed_list,current_copy):
            try:path.unlink()
            except FileNotFoundError:pass
        return {"changed":len(changed),"removed":len(removed),"bytes":transfer_size}
    def ensure_key(self):
        if self.key.exists():return
        if not self.password:raise ValueError("首次连接需要root密码以安装部署密钥")
        self.job.update(8,"生成并安装专用SSH密钥")
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-C","shiyue-deploy","-f",str(self.key)],check=True)
        public=self.key.with_suffix(".pub").read_text().strip();script=f"umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF {shlex.quote(public)} ~/.ssh/authorized_keys || echo {shlex.quote(public)} >> ~/.ssh/authorized_keys"
        self.execute([*self.base_ssh(False),"bash","-lc",script],redact=True);os.chmod(self.key,0o600);self.job.write("专用SSH密钥安装完成，后续操作优先使用密钥认证")

def new_release_id(prefix):return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}"
def normalized_arch(value):
    value=str(value).strip().lower()
    if value in ("x86_64","amd64"):return "x86_64","amd64"
    if value in ("aarch64","arm64"):return "aarch64","arm64"
    raise ValueError(f"暂不支持远程CPU架构：{value or '未知'}")
def remote_arch(remote):
    output=remote.ssh("uname -m").strip().splitlines()
    for line in reversed(output):
        if line.strip() in ("x86_64","amd64","aarch64","arm64"):return normalized_arch(line)
    raise ValueError("无法识别远程CPU架构")
def runtime_archive(oci_arch):return RUNTIME/f"shiyue-reader-runtime-{oci_arch}-20260930-1.tar.gz"
def safe_host(value):return re.sub(r"[^A-Za-z0-9_.-]+","_",str(value))[:80] or "remote"
def code_files():
    files=[ROOT/"reader",ROOT/"deployment",ROOT/"start-reader.sh",ROOT/"start-reader-https.sh"]
    files += list((ROOT/"tools").glob("*.py"))+[ROOT/"tools/deployment"]
    return files
def build_code_package(job,release):
    target=STATE/f"{release}.tar.gz";STATE.mkdir(parents=True,exist_ok=True)
    def archive_filter(info):
        if "__pycache__" in info.name:return None
        return info
    with tarfile.open(target,"w:gz") as archive:
        for path in code_files():
            if path.exists():archive.add(path,arcname=path.relative_to(ROOT),filter=archive_filter)
    digest=hashlib.sha256(target.read_bytes()).hexdigest();job.write(f"代码包：{target.name} · {target.stat().st_size/1024/1024:.1f} MiB · sha256={digest}");return target,digest

def ensure_remote_docker(job,remote):
    probe=remote.ssh("if command -v docker >/dev/null 2>&1; then (docker info >/dev/null 2>&1 || (command -v systemctl >/dev/null 2>&1 && systemctl start docker >/dev/null 2>&1) || service docker start >/dev/null 2>&1 || true); docker info >/dev/null 2>&1 && echo SHIYUE_DOCKER_READY; fi")
    if "SHIYUE_DOCKER_READY" in probe:
        job.write("远程Docker已安装且运行正常");return
    job.update(9,"远程安装Docker")
    script="""set -e
if command -v curl >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
elif command -v wget >/dev/null 2>&1; then
  wget -qO- https://get.docker.com | sh
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y docker
elif command -v yum >/dev/null 2>&1; then
  yum install -y docker
else
  echo '无法自动安装Docker：远程缺少curl、wget和支持的包管理器' >&2
  exit 2
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now docker
else
  service docker start
fi
docker info >/dev/null
docker --version
"""
    remote.ssh(script);job.write("远程Docker安装完成")

def ensure_remote_runtime(job,remote,oci_arch):
    output=remote.ssh(f"docker image inspect {shlex.quote(RUNTIME_IMAGE)} >/dev/null 2>&1 && echo SHIYUE_RUNTIME_READY || true")
    remote_ready="SHIYUE_RUNTIME_READY" in output;archive=runtime_archive(oci_arch);archive.parent.mkdir(parents=True,exist_ok=True)
    if remote_ready and archive.exists():
        job.write(f"远程运行镜像和本机离线缓存均已存在：{RUNTIME_IMAGE}");return archive
    created_on_target=False
    if not archive.exists():
        job.update(13,"从现有远程镜像制作本机离线运行包")
        remote_temp=f"/tmp/{archive.name}"
        script=f"""set -e
source_image=$(docker inspect -f '{{{{.Config.Image}}}}' shiyue-reader 2>/dev/null || true)
if [ -z "$source_image" ]; then
  source_image=$(docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' | grep '^shiyue-reader:' | head -1 || true)
fi
[ -n "$source_image" ] || {{ echo '远程没有可导出的拾页运行镜像' >&2; exit 3; }}
docker tag "$source_image" {shlex.quote(RUNTIME_IMAGE)}
docker save {shlex.quote(RUNTIME_IMAGE)} | gzip -1 > {shlex.quote(remote_temp)}
"""
        remote.ssh(script);remote.scp_from(remote_temp,archive);remote.ssh(f"rm -f {shlex.quote(remote_temp)}");created_on_target=True
    if archive.stat().st_size<20*1024*1024:raise ValueError("本机离线运行镜像异常，文件过小")
    with gzip.open(archive,"rb") as source:
        if not source.read(512):raise ValueError("本机离线运行镜像无法读取")
    job.write(f"本机离线运行镜像：{archive.name} · {archive.stat().st_size/1024/1024:.1f} MiB")
    if remote_ready or created_on_target:
        job.write("运行镜像已在当前服务器生成，同时缓存到本机，跳过重复上传")
    else:
        job.update(18,"上传完整Docker运行镜像")
        remote_temp=f"/tmp/{archive.name}";remote.scp(archive,remote_temp)
        remote.ssh(f"set -e; gzip -dc {shlex.quote(remote_temp)} | docker load; docker image inspect {shlex.quote(RUNTIME_IMAGE)} >/dev/null; rm -f {shlex.quote(remote_temp)}")
    return archive

def build_tls_bundle(target):
    directory=TLS/safe_host(target["host"]);directory.mkdir(parents=True,exist_ok=True)
    root_key=directory/"rootCA-key.pem";root_cert=directory/"rootCA.pem";server_key=directory/"server-key.pem";server_cert=directory/"server-cert.pem"
    if all(path.exists() and path.stat().st_size for path in (root_key,root_cert,server_key,server_cert)):return directory
    openssl=shutil.which("openssl")
    if not openssl:raise ValueError("本机缺少openssl，无法生成远程HTTPS证书")
    host=target["host"]
    try:ipaddress.ip_address(host);san=f"IP:{host}"
    except ValueError:san=f"DNS:{host}"
    config=directory/"server.cnf";config.write_text(f"""[req]
distinguished_name=req_dn
req_extensions=req_ext
prompt=no
[req_dn]
CN={host}
[req_ext]
subjectAltName={san}
extendedKeyUsage=serverAuth
""",encoding="utf-8")
    commands=[
      [openssl,"genrsa","-out",root_key,"3072"],
      [openssl,"req","-x509","-new","-nodes","-key",root_key,"-sha256","-days","3650","-subj","/CN=Shiyue Remote Root CA","-out",root_cert],
      [openssl,"genrsa","-out",server_key,"2048"],
      [openssl,"req","-new","-key",server_key,"-out",directory/"server.csr","-config",config],
      [openssl,"x509","-req","-in",directory/"server.csr","-CA",root_cert,"-CAkey",root_key,"-CAcreateserial","-out",server_cert,"-days","825","-sha256","-extensions","req_ext","-extfile",config],
    ]
    for command in commands:subprocess.run([str(value) for value in command],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    os.chmod(root_key,0o600);os.chmod(server_key,0o600);return directory

def ensure_remote_tls(job,remote,target):
    root=target["remote_root"];certificate=STATE/"certificates"/f"{target['host']}-rootCA.pem"
    output=remote.ssh(f"test -s {shlex.quote(root)}/shared/https/rootCA.pem -a -s {shlex.quote(root)}/shared/https/server-cert.pem -a -s {shlex.quote(root)}/shared/https/server-key.pem && echo SHIYUE_TLS_READY || true")
    if "SHIYUE_TLS_READY" not in output:
        job.update(42,"本机生成并上传HTTPS证书")
        directory=build_tls_bundle(target);remote.ssh(f"mkdir -p {shlex.quote(root)}/shared/https")
        for name in ("rootCA.pem","rootCA-key.pem","server-cert.pem","server-key.pem"):remote.scp(directory/name,f"{root}/shared/https/{name}")
        remote.ssh(f"chmod 600 {shlex.quote(root)}/shared/https/*key.pem")
    certificate.parent.mkdir(parents=True,exist_ok=True);remote.scp_from(f"{root}/shared/https/rootCA.pem",certificate);return certificate

def docker_run_command(target,image=RUNTIME_IMAGE):
    root=shlex.quote(target["remote_root"]);port=int(target["service_port"]);recording=bool(target["install_recording"])
    options=["docker run -d --name shiyue-reader --restart unless-stopped","--network host","-e READER_HOST=0.0.0.0",f"-e READER_PORT={port}","-e SHIYUE_RUNTIME_MODE=reader",
      f"-v {root}/current/reader:/app/reader:ro",f"-v {root}/current/tools:/app/tools:ro",f"-v {root}/shared/books:/app/books",f"-v {root}/shared/.local:/app/.local",f"-v {root}/shared/cache:/app/.cache",f"-v {root}/shared/config/dioco.local.json:/app/.dioco.local.json"]
    if recording:options += [f"-v {root}/shared/https:/certs:ro",f"-v {root}/shared/whisper/ggml-base.en.bin:/opt/shiyue/models/ggml-base.en.bin:ro","-e READER_TLS_CERT=/certs/server-cert.pem","-e READER_TLS_KEY=/certs/server-key.pem"]
    options.append(shlex.quote(image));return " \\\n  ".join(options)

def health_check_command(target):
    scheme="https" if target["install_recording"] else "http";port=int(target["service_port"])
    code=f"import json,ssl,urllib.request; u='{scheme}://127.0.0.1:{port}/api/health'; c=ssl._create_unverified_context() if u.startswith('https') else None; print(urllib.request.urlopen(u,context=c,timeout=20).read().decode())"
    return f"docker exec shiyue-reader python3 -c {shlex.quote(code)}"

def bootstrap_script(target,release,package_name):
    root=shlex.quote(target["remote_root"]);run=docker_run_command(target);health=health_check_command(target)
    return f"""set -euo pipefail
systemctl disable --now shiyue-reader >/dev/null 2>&1 || true
mkdir -p {root}/releases/{release} {root}/shared/books {root}/shared/.local {root}/shared/cache {root}/shared/config {root}/backups/databases {root}/backups/resources {root}/manifests/history {root}/logs
[ -f {root}/shared/config/dioco.local.json ] || echo '{{}}' > {root}/shared/config/dioco.local.json
tar -xzf /tmp/{package_name} -C {root}/releases/{release}
previous_release=$(readlink -f {root}/current 2>/dev/null || true)
docker rm -f shiyue-reader >/dev/null 2>&1 || true
ln -sfn {root}/releases/{release} {root}/current
{run}
healthy=0
for attempt in $(seq 1 15); do
  if {health} >/tmp/shiyue-health.json 2>/tmp/shiyue-health-error.log; then healthy=1; break; fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  echo '新容器健康检查失败'
  cat /tmp/shiyue-health-error.log >&2 2>/dev/null || true
  docker logs --tail 200 shiyue-reader || true
  docker rm -f shiyue-reader >/dev/null 2>&1 || true
  if [ -n "$previous_release" ] && [ -d "$previous_release" ]; then
    echo "恢复旧代码版本 $previous_release"
    ln -sfn "$previous_release" {root}/current
    {run}
  fi
  exit 1
fi
cat /tmp/shiyue-health.json
rm -f /tmp/{package_name}
"""

def content_file_entry(source,books_root):
    """Keep the URL path while dereferencing its file content for transfer."""
    books_root=Path(books_root).resolve();source=Path(source)
    logical=source.parent.resolve()/source.name
    logical.relative_to(books_root)
    actual=logical.resolve();actual.relative_to(books_root)
    if not actual.is_file():return None
    return logical.relative_to(books_root),actual

def export_content(job,revision):
    stage=STATE/"staging"/revision;shutil.rmtree(stage,ignore_errors=True);stage.mkdir(parents=True)
    db=connect();books=[dict(row) for row in db.execute("SELECT * FROM books WHERE status='ready'")];artifacts=[dict(row) for row in db.execute("SELECT * FROM book_artifacts WHERE book_id IN (SELECT id FROM books WHERE status='ready')")];dictionary=[dict(row) for row in db.execute("SELECT * FROM dictionary_entries")];grammar=[dict(row) for row in db.execute("SELECT * FROM sentence_grammar WHERE book_id IN (SELECT id FROM books WHERE status='ready')")];db.close()
    files=[];books_root=(ROOT/"books").resolve()
    for row in books:
        data=json.loads(row["data_json"])
        paths=[]
        for key in ("audio","video"):
            url=data.get(key,"")
            if url.startswith("/books/"):paths.append(books_root/unquote(url[len('/books/'):]))
        base=data.get("pageBase","")
        if base.startswith("/books/"):
            directory=books_root/unquote(base[len('/books/'):]);paths.extend(directory.glob("page-*.jpg")) if directory.is_dir() else None
        for source in paths:
            entry=content_file_entry(source,books_root)
            if not entry:continue
            relative,actual=entry;destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.symlink_to(actual);files.append({"path":str(relative),"size":actual.stat().st_size,"mtime":actual.stat().st_mtime_ns})
    payload={"revision":revision,"books":books,"book_artifacts":artifacts,"dictionary_entries":dictionary,"sentence_grammar":grammar}
    bundle=STATE/f"{revision}.json.gz"
    with gzip.open(bundle,"wt",encoding="utf-8") as output:json.dump(payload,output,ensure_ascii=False)
    manifest=STATE/f"{revision}.manifest.json";manifest.write_text(json.dumps({"revision":revision,"books":len(books),"grammarSentences":len(grammar),"files":files},ensure_ascii=False,indent=2))
    job.write(f"成品清单：{len(books)}本 · {len(grammar)}句语法 · {len(files)}个文件 · {sum(x['size'] for x in files)/1024/1024:.1f} MiB");return stage,bundle,manifest

def sync_content(job,remote,target,progress=None):
    progress=progress or {"scan":5,"prepare":25,"generate":35,"package":40,"upload":48,"apply":74,"database":80,"merge":88}
    revision=new_release_id("content");job.update(progress["scan"],"扫描本地已导入点读资源");stage,bundle,manifest=export_content(job,revision)
    root=target["remote_root"];backup=f"{root}/backups/resources/{revision}";remote_bundle=f"{root}/shared/.local/{bundle.name}"
    job.update(progress["prepare"],"准备远程资源目录");remote.ssh(f"set -e; docker inspect shiyue-reader >/dev/null; mkdir -p {shlex.quote(root)}/shared/books {shlex.quote(backup)} {shlex.quote(root)}/manifests/history {shlex.quote(root)}/shared/.local {shlex.quote(root)}/backups/databases")
    job.update(progress["generate"],"生成离线增量资源包");sync_result=remote.sync_tree_package(stage,f"{root}/shared/books",backup,manifest,f"{root}/manifests/current-content.json",progress)
    job.update(progress["database"],"上传内容数据库包");remote.scp(bundle,remote_bundle);remote.scp(manifest,f"/tmp/{manifest.name}")
    job.update(progress["merge"],"备份并合并远程内容数据库");health=health_check_command(target)
    script=f"set -e; cp {shlex.quote(root)}/shared/.local/library.sqlite3 {shlex.quote(root)}/backups/databases/{revision}.sqlite3 2>/dev/null || true; docker exec shiyue-reader python3 /app/tools/deployment/remote_apply.py /app/.local/{bundle.name} /app/.local/library.sqlite3; cp /tmp/{manifest.name} {shlex.quote(root)}/manifests/current-content.json; cp /tmp/{manifest.name} {shlex.quote(root)}/manifests/history/{revision}.json; cp {shlex.quote(remote_bundle)} {shlex.quote(root)}/manifests/history/{revision}.json.gz; docker restart shiyue-reader >/dev/null; sleep 3; {health}; rm -f {shlex.quote(remote_bundle)} /tmp/{manifest.name}"
    output=remote.ssh(script);return {"contentRevision":revision,"health":output,"media":sync_result}

def run_task(kind,worker):
    job=Job(kind)
    def target():
        if not TASK_LOCK.acquire(blocking=False):job.fail("已有部署或同步任务正在运行");return
        try:
            job.update(1,"读取远程配置");config=get_target()
            if not config:raise ValueError("请先保存远程服务器配置")
            remote=Remote(config,job);remote.ensure_key();worker(job,remote,config)
        except Exception as exc:job.fail(exc)
        finally:TASK_LOCK.release()
    threading.Thread(target=target,daemon=True).start();return job.id

def start_test():
    return run_task("connection_test",lambda job,remote,target:(job.update(30,"连接SSH"),remote.ssh("uname -a && id && df -h /"),job.complete({"connected":True},"连接正常")))
def start_deploy():
    def worker(job,remote,target):
        release=new_release_id("code");job.update(4,"检查远程Linux架构",release_id=release);download_arch,oci_arch=remote_arch(remote);job.write(f"远程架构：{download_arch}")
        ensure_remote_docker(job,remote);runtime=ensure_remote_runtime(job,remote,oci_arch)
        job.update(26,"生成代码发布包");package,digest=build_code_package(job,release);job.update(31,"上传代码版本");remote.scp(package,f"/tmp/{package.name}")
        certificate=""
        if target["install_recording"]:
            model=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"
            if not model.exists():raise ValueError("本地缺少 ggml-base.en.bin，无法安装远程录音模型")
            remote_model=f"{target['remote_root']}/shared/whisper/ggml-base.en.bin";local_hash=hashlib.sha256(model.read_bytes()).hexdigest();remote.ssh(f"mkdir -p {shlex.quote(target['remote_root'])}/shared/whisper")
            output=remote.ssh(f"command -v sha256sum >/dev/null 2>&1 && test -f {shlex.quote(remote_model)} && sha256sum {shlex.quote(remote_model)} | cut -d' ' -f1 || true").strip().splitlines();remote_hash=output[-1] if output else ""
            if remote_hash!=local_hash:job.update(37,"上传服务器端录音模型（约141MiB）");remote.scp(model,remote_model)
            else:job.write("远程录音模型已存在且校验一致，跳过上传")
            certificate=ensure_remote_tls(job,remote,target);job.write(f"其他设备使用录音前请安装根证书：{certificate}")
        job.update(50,"激活代码版本并启动运行容器");health=remote.ssh(bootstrap_script(target,release,package.name))
        content=sync_content(job,remote,target,{"scan":58,"prepare":62,"generate":65,"package":68,"upload":72,"apply":80,"database":86,"merge":91})
        job.update(97,"最终健康检查");final_health=remote.ssh(health_check_command(target));db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=1 AND status='active'");db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,1,"active",digest,json.dumps({"raw":final_health}),now()));db.commit();db.close();job.complete({"releaseId":release,"health":final_health,"initialHealth":health,"contentRevision":content["contentRevision"],"media":content["media"],"runtimeArchive":str(runtime),"rootCertificate":str(certificate) if certificate else ""},"一键完整部署完成")
    return run_task("code_deploy",worker)
def start_upgrade():
    def worker(job,remote,target):
        release=new_release_id("code");job.update(8,"检查远程运行环境",release_id=release)
        output=remote.ssh(f"set -e; docker info >/dev/null; docker image inspect {shlex.quote(RUNTIME_IMAGE)} >/dev/null; test -d {shlex.quote(target['remote_root'])}/shared/.local; echo SHIYUE_UPGRADE_READY")
        if "SHIYUE_UPGRADE_READY" not in output:raise ValueError("远程尚未完成初始化，请先执行一键完整部署")
        job.update(25,"生成程序版本包");package,digest=build_code_package(job,release)
        job.update(42,"上传修改后的程序代码");remote.scp(package,f"/tmp/{package.name}")
        job.update(65,"切换程序版本");health=remote.ssh(bootstrap_script(target,release,package.name))
        job.update(92,"验证升级结果");final_health=remote.ssh(health_check_command(target))
        db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=1 AND status='active'");db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,1,"active",digest,json.dumps({"raw":final_health}),now()));db.commit();db.close()
        job.complete({"releaseId":release,"health":final_health,"initialHealth":health,"codeBytes":package.stat().st_size},"程序升级完成")
    return run_task("program_upgrade",worker)
def start_sync():
    def worker(job,remote,target):
        result=sync_content(job,remote,target);job.complete(result,"点读资源同步完成")
    return run_task("resource_sync",worker)
def content_rollback_run_command(target,release,operation,restore=False):
    root=target["remote_root"];arguments=["python3","/app/tools/deployment/content_rollback.py","--operation",operation,"--books","/app/books","--manifests","/state/manifests","--backups","/state/backups","--database","/app/.local/library.sqlite3"]
    if restore:arguments.append("--restore")
    else:arguments += ["--target",release]
    options=["docker run --rm --network none",f"-v {shlex.quote(root)}/current/tools:/app/tools:ro",f"-v {shlex.quote(root)}/shared/books:/app/books",f"-v {shlex.quote(root)}/shared/.local:/app/.local",f"-v {shlex.quote(root)}/manifests:/state/manifests",f"-v {shlex.quote(root)}/backups:/state/backups",shlex.quote(RUNTIME_IMAGE),*(shlex.quote(value) for value in arguments)]
    return (" \\"+"\n  ").join(options)
    return " \\\n+  ".join(options)

def start_content_rollback(release):
    def worker(job,remote,target):
        if not re.fullmatch(r"content-\d{8}-\d{6}-[A-Za-z0-9]+",release or ""):raise ValueError("无效的内容版本")
        root=target["remote_root"];operation=new_release_id("content-rollback");job.update(12,f"检查内容快照 {release}",release_id=release)
        remote.ssh(f"set -e; test -f {shlex.quote(root)}/manifests/history/{shlex.quote(release)}.json; test -f {shlex.quote(root)}/manifests/history/{shlex.quote(release)}.json.gz; docker image inspect {shlex.quote(RUNTIME_IMAGE)} >/dev/null")
        run=content_rollback_run_command(target,release,operation);restore=content_rollback_run_command(target,release,operation,True);health=health_check_command(target)
        job.update(35,"创建恢复点并回滚内容")
        script=f"""set -e
docker stop shiyue-reader >/dev/null
if ! {run}; then docker start shiyue-reader >/dev/null || true; exit 1; fi
docker start shiyue-reader >/dev/null
sleep 3
if ! {health}; then
  echo '内容回滚后健康检查失败，正在恢复操作前内容' >&2
  docker stop shiyue-reader >/dev/null || true
  {restore}
  docker start shiyue-reader >/dev/null
  sleep 3
  {health} || true
  exit 1
fi
"""
        output=remote.ssh(script);job.complete({"contentRevision":release,"operation":operation,"health":output},"内容回滚完成")
    return run_task("content_rollback",worker)

def start_cleanup(retention_days=30):
    days=max(1,min(3650,int(retention_days or 30)));cutoff=datetime.now()-timedelta(days=days);stamp=cutoff.strftime("%Y%m%d-%H%M%S")
    def worker(job,remote,target):
        root=target["remote_root"];job.update(20,f"扫描{days}天前的代码和内容版本")
        script=f"""set -euo pipefail
root={shlex.quote(root)}
code_cutoff=code-{stamp}
content_cutoff=content-{stamp}
current_code=$(basename "$(readlink -f "$root/current" 2>/dev/null || true)")
current_content=$(sed -n 's/.*"revision"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' "$root/manifests/current-content.json" | head -1)
code_removed=0
content_removed=0
for path in "$root"/releases/code-*; do
  [ -d "$path" ] || continue
  name=$(basename "$path")
  if [[ "$name" < "$code_cutoff" && "$name" != "$current_code" ]]; then rm -rf -- "$path"; code_removed=$((code_removed+1)); fi
done
for manifest in "$root"/manifests/history/content-*.json; do
  [ -f "$manifest" ] || continue
  name=$(basename "$manifest" .json)
  if [[ "$name" < "$content_cutoff" && "$name" != "$current_content" ]]; then
    rm -f -- "$root/manifests/history/$name.json" "$root/manifests/history/$name.json.gz" "$root/backups/databases/$name.sqlite3"
    rm -rf -- "$root/backups/resources/$name"
    content_removed=$((content_removed+1))
  fi
done
mkdir -p "$root/backups/content-rollbacks"
find "$root/backups/content-rollbacks" -mindepth 1 -maxdepth 1 -type d -mtime +{days} -exec rm -rf -- {{}} + 2>/dev/null || true
docker images shiyue-reader --format '{{{{.Tag}}}}' 2>/dev/null | while read tag; do
  case "$tag" in code-*) if [[ "$tag" < "$code_cutoff" && "$tag" != "$current_code" ]]; then docker image rm "shiyue-reader:$tag" >/dev/null 2>&1 || true; fi;; esac
done
echo "代码版本已清理:$code_removed"
echo "内容版本已清理:$content_removed"
echo "保留天数:{days}"
echo "当前代码:$current_code"
echo "当前内容:$current_content"
"""
        output=remote.ssh(script);job.update(85,"清理本机过期发布包")
        threshold=cutoff.timestamp();removed_local=0
        for pattern in ("code-*.tar.gz","content-*.json.gz","content-*.manifest.json","content-*.resources.tar","content-*.changed.txt","content-*.removed.txt"):
            for path in STATE.glob(pattern):
                if path.is_file() and path.stat().st_mtime<threshold:path.unlink();removed_local+=1
        staging=STATE/"staging"
        if staging.exists():
            for path in staging.iterdir():
                if path.is_dir() and path.stat().st_mtime<threshold:shutil.rmtree(path,ignore_errors=True);removed_local+=1
        job.complete({"retentionDays":days,"remote":output,"localArtifactsRemoved":removed_local},"过期版本清理完成")
    return run_task("version_cleanup",worker)

def start_rollback(release):
    def worker(job,remote,target):
        if not re.fullmatch(r"code-[A-Za-z0-9-]+",release or ""):raise ValueError("无效的回滚版本")
        root=target["remote_root"];job.update(20,f"检查代码版本 {release}");run=docker_run_command(target);health_command=health_check_command(target)
        script=f"set -e; test -d {shlex.quote(root)}/releases/{shlex.quote(release)}; previous_release=$(readlink -f {shlex.quote(root)}/current 2>/dev/null || true); docker rm -f shiyue-reader >/dev/null 2>&1 || true; ln -sfn {shlex.quote(root)}/releases/{shlex.quote(release)} {shlex.quote(root)}/current; {run}; healthy=0; for attempt in $(seq 1 15); do if {health_command}; then healthy=1; break; fi; sleep 1; done; [ \"$healthy\" -eq 1 ] || {{ docker logs --tail 150 shiyue-reader || true; docker rm -f shiyue-reader; if [ -n \"$previous_release\" ]; then ln -sfn \"$previous_release\" {shlex.quote(root)}/current; {run}; fi; exit 1; }}"
        health=remote.ssh(script);db=connect();db.execute("UPDATE deployment_releases SET status=CASE WHEN release_id=? THEN 'active' ELSE 'available' END WHERE target_id=1",(release,));db.commit();db.close();job.complete({"releaseId":release,"health":health},"代码回滚完成")
    return run_task("code_rollback",worker)

def job_info(job_id,offset=0):
    db=connect();row=db.execute("SELECT * FROM deployment_jobs WHERE id=?",(job_id,)).fetchone();db.close()
    if not row:return None
    result=dict(row);path=Path(result["log_path"]);text=path.read_text(errors="replace") if path.exists() else "";offset=max(0,min(int(offset),len(text)));result["logChunk"]=text[offset:];result["logOffset"]=len(text)
    try:result["result"]=json.loads(result.pop("result_json"))
    except Exception:result["result"]={}
    return result
def recent_jobs(limit=20):
    db=connect();rows=[dict(row) for row in db.execute("SELECT id,kind,status,progress,step,error,release_id,created_at,updated_at FROM deployment_jobs ORDER BY id DESC LIMIT ?",(limit,))];db.close();return rows
def dashboard_status():
    db=connect();books=db.execute("SELECT COUNT(*) FROM books WHERE status='ready'").fetchone()[0]
    code=db.execute("SELECT result_json FROM deployment_jobs WHERE kind IN ('code_deploy','program_upgrade') AND status='complete' ORDER BY id DESC LIMIT 1").fetchone()
    content=db.execute("SELECT result_json FROM deployment_jobs WHERE kind IN ('resource_sync','code_deploy','content_rollback') AND status='complete' ORDER BY id DESC LIMIT 1").fetchone();db.close()
    def value(row,key):
        if not row:return ""
        try:return json.loads(row[0]).get(key,"")
        except Exception:return ""
    return {"codeVersion":value(code,"releaseId"),"contentVersion":value(content,"contentRevision"),"localBooks":books,"localRuntime":"约1.3 GiB"}
def remote_releases():
    target=get_target()
    if not target:return []
    job=Job("release_list")
    try:
        root=shlex.quote(target["remote_root"]);remote=Remote(target,job);output=remote.ssh(f"current=$(basename \"$(readlink -f {root}/current 2>/dev/null || true)\"); find {root}/releases -mindepth 1 -maxdepth 1 -type d -name 'code-*' -printf '%f\\n' 2>/dev/null | sort -r | while read b; do [ \"$b\" = \"$current\" ] && echo \"$b|current\" || echo \"$b|available\"; done");job.complete()
        return [{"releaseId":line.split("|",1)[0],"status":line.split("|",1)[1]} for line in output.splitlines() if line.startswith("code-") and "|" in line]
    except Exception as exc:job.fail(exc);return []
def remote_content_releases():
    target=get_target()
    if not target:return []
    job=Job("content_release_list")
    try:
        root=shlex.quote(target["remote_root"]);remote=Remote(target,job);output=remote.ssh(f"current=$(sed -n 's/.*\"revision\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p' {root}/manifests/current-content.json 2>/dev/null | head -1); for bundle in {root}/manifests/history/content-*.json.gz; do [ -f \"$bundle\" ] || continue; b=$(basename \"$bundle\" .json.gz); if [ \"$b\" = \"$current\" ]; then echo \"$b|current\"; elif [[ \"$b\" < \"$current\" ]]; then echo \"$b|available\"; fi; done | sort -r");job.complete()
        return [{"releaseId":line.split("|",1)[0],"status":line.split("|",1)[1]} for line in output.splitlines() if line.startswith("content-") and "|" in line]
    except Exception as exc:job.fail(exc);return []
