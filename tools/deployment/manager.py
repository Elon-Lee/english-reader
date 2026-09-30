#!/usr/bin/env python3
"""Versioned code deployment and finished-resource synchronization."""
import gzip,hashlib,ipaddress,json,os,shlex,shutil,sqlite3,subprocess,tarfile,tempfile,threading,time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/".local/library.sqlite3"
STATE=ROOT/".local/deployment"
LOGS=STATE/"logs";KNOWN_HOSTS=STATE/"known_hosts"
KEYS=STATE/"keys"
EXPECT=ROOT/"tools/deployment/ssh_expect.exp"
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
    def sync_tree_package(self,source,destination,backup_dir,manifest,remote_manifest):
        """Upload an offline incremental tar package without using rsync protocol."""
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
            self.job.update(40,f"本机打包增量资源（{transfer_size/1024/1024:.1f} MiB）")
            with tarfile.open(package,"w",dereference=True) as archive:
                for relative in changed:
                    archive.add(Path(source)/relative,arcname=relative,recursive=False)
            self.job.write(f"离线资源包：{package.name} · {package.stat().st_size/1024/1024:.1f} MiB")
            self.job.update(48,"上传离线增量资源包")
            self.scp(package,remote_package)
        self.scp(changed_list,remote_changed);self.scp(removed_list,remote_removed)
        self.job.update(74,"远程备份并应用增量资源")
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
def code_files():
    files=[ROOT/"reader",ROOT/"deployment",ROOT/"start-reader.sh",ROOT/"start-reader-https.sh"]
    files += list((ROOT/"tools").glob("*.py"))+[ROOT/"tools/deployment"]
    return files
def build_code_package(job,release):
    target=STATE/f"{release}.tar.gz";STATE.mkdir(parents=True,exist_ok=True)
    whisper_root=ROOT/"tools/vendor/whisper.cpp"
    excluded_prefixes=(".git/","build/","models/","media/","samples/",".github/",".devops/",".pi/")
    def archive_filter(info):
        name=info.name
        if "__pycache__" in name:return None
        marker="tools/vendor/whisper.cpp/"
        if marker in name:
            relative=name.split(marker,1)[1]
            if any(relative==prefix.rstrip("/") or relative.startswith(prefix) for prefix in excluded_prefixes):return None
        return info
    with tarfile.open(target,"w:gz") as archive:
        for path in code_files():
            if path.exists():archive.add(path,arcname=path.relative_to(ROOT),filter=archive_filter)
        if whisper_root.exists():archive.add(whisper_root,arcname="tools/vendor/whisper.cpp",filter=archive_filter)
    digest=hashlib.sha256(target.read_bytes()).hexdigest();job.write(f"代码包：{target.name} · {target.stat().st_size/1024/1024:.1f} MiB · sha256={digest}");return target,digest

def docker_run_command(target,image):
    root=shlex.quote(target["remote_root"]);port=int(target["service_port"]);recording=bool(target["install_recording"])
    options=["docker run -d --name shiyue-reader --restart unless-stopped",f"-p {port}:{port}","-e READER_HOST=0.0.0.0",f"-e READER_PORT={port}","-e SHIYUE_RUNTIME_MODE=reader",
      f"-v {root}/shared/books:/app/books",f"-v {root}/shared/.local:/app/.local",f"-v {root}/shared/cache:/app/.cache",f"-v {root}/shared/config/dioco.local.json:/app/.dioco.local.json"]
    if recording:options += [f"-v {root}/shared/https:/certs:ro",f"-v {root}/shared/whisper/ggml-base.en.bin:/opt/shiyue/models/ggml-base.en.bin:ro","-e READER_TLS_CERT=/certs/server-cert.pem","-e READER_TLS_KEY=/certs/server-key.pem"]
    options.append(shlex.quote(image));return " \\\n  ".join(options)

def docker_run_previous_command(target):
    return docker_run_command(target,"__SHIYUE_PREVIOUS_IMAGE__").replace("__SHIYUE_PREVIOUS_IMAGE__",'"$previous_image"')

def bootstrap_script(target,release,package_name):
    root=shlex.quote(target["remote_root"]);port=int(target["service_port"]);recording=bool(target["install_recording"]);image=f"shiyue-reader:{release}"
    scheme="https" if recording else "http";curl_flags="-k" if recording else "";tls=""
    if recording:
        host=target["host"]
        try:ipaddress.ip_address(host);san=f"IP:{host}"
        except ValueError:san=f"DNS:{host}"
        tls=f"""
mkdir -p {root}/shared/https
if [ ! -f {root}/shared/https/rootCA.pem ]; then
  openssl genrsa -out {root}/shared/https/rootCA-key.pem 3072
  openssl req -x509 -new -nodes -key {root}/shared/https/rootCA-key.pem -sha256 -days 3650 -subj '/CN=Shiyue Remote Root CA' -out {root}/shared/https/rootCA.pem
fi
cat > /tmp/shiyue-cert.cnf <<'CERTCFG'
[req]
distinguished_name=req_dn
req_extensions=req_ext
prompt=no
[req_dn]
CN={host}
[req_ext]
subjectAltName={san}
extendedKeyUsage=serverAuth
CERTCFG
openssl genrsa -out {root}/shared/https/server-key.pem 2048
openssl req -new -key {root}/shared/https/server-key.pem -out /tmp/shiyue-server.csr -config /tmp/shiyue-cert.cnf
openssl x509 -req -in /tmp/shiyue-server.csr -CA {root}/shared/https/rootCA.pem -CAkey {root}/shared/https/rootCA-key.pem -CAcreateserial -out {root}/shared/https/server-cert.pem -days 825 -sha256 -extensions req_ext -extfile /tmp/shiyue-cert.cnf
chmod 600 {root}/shared/https/*key.pem
"""
    run=docker_run_command(target,image)
    return f"""set -euo pipefail
if ! command -v docker >/dev/null; then
  if command -v apt-get >/dev/null; then curl -fsSL https://get.docker.com | sh; elif command -v yum >/dev/null; then yum install -y yum-utils && yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo && yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin; fi
fi
systemctl enable --now docker
if ! command -v curl >/dev/null || ! command -v openssl >/dev/null; then
  if command -v apt-get >/dev/null; then apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y curl openssl; elif command -v dnf >/dev/null; then dnf install -y curl openssl; elif command -v yum >/dev/null; then yum install -y curl openssl; fi
fi
systemctl disable --now shiyue-reader >/dev/null 2>&1 || true
mkdir -p {root}/releases/{release} {root}/shared/books {root}/shared/.local {root}/shared/cache {root}/shared/config {root}/backups/databases {root}/backups/resources {root}/manifests/history {root}/logs
[ -f {root}/shared/config/dioco.local.json ] || echo '{{}}' > {root}/shared/config/dioco.local.json
tar -xzf /tmp/{package_name} -C {root}/releases/{release}
{tls}
echo '构建Docker镜像 {image}'
docker build -t {shlex.quote(image)} -f {root}/releases/{release}/deployment/docker/Dockerfile {root}/releases/{release}
previous_image=$(docker inspect -f '{{{{.Config.Image}}}}' shiyue-reader 2>/dev/null || true)
docker rm -f shiyue-reader >/dev/null 2>&1 || true
ln -sfn {root}/releases/{release} {root}/current
{run}
sleep 3
if ! curl {curl_flags} -fsS {scheme}://127.0.0.1:{port}/api/health >/tmp/shiyue-health.json; then
  echo '新容器健康检查失败'
  docker logs --tail 200 shiyue-reader || true
  docker rm -f shiyue-reader >/dev/null 2>&1 || true
  if [ -n "$previous_image" ]; then
    echo "恢复旧镜像 $previous_image"
    {docker_run_previous_command(target)}
  fi
  exit 1
fi
cat /tmp/shiyue-health.json
rm -f /tmp/{package_name}
"""

def export_content(job,revision):
    stage=STATE/"staging"/revision;shutil.rmtree(stage,ignore_errors=True);stage.mkdir(parents=True)
    db=connect();books=[dict(row) for row in db.execute("SELECT * FROM books WHERE status='ready'")];artifacts=[dict(row) for row in db.execute("SELECT * FROM book_artifacts WHERE book_id IN (SELECT id FROM books WHERE status='ready')")];dictionary=[dict(row) for row in db.execute("SELECT * FROM dictionary_entries")];db.close()
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
            source=source.resolve();source.relative_to(books_root)
            if not source.is_file():continue
            relative=source.relative_to(books_root);destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.symlink_to(source);files.append({"path":str(relative),"size":source.stat().st_size,"mtime":source.stat().st_mtime_ns})
    payload={"revision":revision,"books":books,"book_artifacts":artifacts,"dictionary_entries":dictionary}
    bundle=STATE/f"{revision}.json.gz"
    with gzip.open(bundle,"wt",encoding="utf-8") as output:json.dump(payload,output,ensure_ascii=False)
    manifest=STATE/f"{revision}.manifest.json";manifest.write_text(json.dumps({"revision":revision,"books":len(books),"files":files},ensure_ascii=False,indent=2))
    job.write(f"成品清单：{len(books)}本 · {len(files)}个文件 · {sum(x['size'] for x in files)/1024/1024:.1f} MiB");return stage,bundle,manifest

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
        release=new_release_id("code");job.update(10,"生成代码发布包",release_id=release);package,digest=build_code_package(job,release);job.update(25,"上传代码包");remote.scp(package,f"/tmp/{package.name}")
        if target["install_recording"]:
            model=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"
            if not model.exists():raise ValueError("本地缺少 ggml-base.en.bin，无法安装远程录音模型")
            remote_model=f"{target['remote_root']}/shared/whisper/ggml-base.en.bin";local_hash=hashlib.sha256(model.read_bytes()).hexdigest();remote.ssh(f"mkdir -p {shlex.quote(target['remote_root'])}/shared/whisper")
            output=remote.ssh(f"test -f {shlex.quote(remote_model)} && sha256sum {shlex.quote(remote_model)} | cut -d' ' -f1 || true").strip().splitlines();remote_hash=output[-1] if output else ""
            if remote_hash!=local_hash:job.update(35,"上传服务器端录音模型（约141MiB）");remote.scp(model,remote_model)
            else:job.write("远程录音模型已存在且校验一致，跳过上传")
        job.update(50,"构建Docker镜像并激活版本");health=remote.ssh(bootstrap_script(target,release,package.name));certificate=""
        if target["install_recording"]:
            certificate=STATE/"certificates"/f"{target['host']}-rootCA.pem";job.update(93,"下载远程HTTPS根证书");remote.scp_from(f"{target['remote_root']}/shared/https/rootCA.pem",certificate);job.write(f"其他设备使用录音前请安装根证书：{certificate}")
        job.update(95,"远程健康检查");db=connect();db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,1,"active",digest,json.dumps({"raw":health}),now()));db.commit();db.close();job.complete({"releaseId":release,"health":health,"rootCertificate":str(certificate) if certificate else ""},"代码部署完成")
    return run_task("code_deploy",worker)
def start_sync():
    def worker(job,remote,target):
        revision=new_release_id("content");job.update(5,"扫描本地已导入点读资源",release_id=revision);stage,bundle,manifest=export_content(job,revision);root=target["remote_root"];backup=f"{root}/backups/resources/{revision}";remote_bundle=f"{root}/shared/.local/{bundle.name}"
        job.update(25,"准备远程资源目录");remote.ssh(f"set -e; docker inspect shiyue-reader >/dev/null; mkdir -p {shlex.quote(root)}/shared/books {shlex.quote(backup)} {shlex.quote(root)}/manifests/history {shlex.quote(root)}/shared/.local")
        job.update(35,"生成离线增量资源包");sync_result=remote.sync_tree_package(stage,f"{root}/shared/books",backup,manifest,f"{root}/manifests/current-content.json")
        job.update(80,"上传内容数据库包");remote.scp(bundle,remote_bundle);remote.scp(manifest,f"/tmp/{manifest.name}")
        job.update(88,"备份并合并远程内容数据库");scheme="https" if target["install_recording"] else "http";flags="-k" if target["install_recording"] else ""
        script=f"set -e; cp {shlex.quote(root)}/shared/.local/library.sqlite3 {shlex.quote(root)}/backups/databases/{revision}.sqlite3 2>/dev/null || true; docker exec shiyue-reader python3 /app/tools/deployment/remote_apply.py /app/.local/{bundle.name} /app/.local/library.sqlite3; cp /tmp/{manifest.name} {shlex.quote(root)}/manifests/current-content.json; cp /tmp/{manifest.name} {shlex.quote(root)}/manifests/history/{revision}.json; docker restart shiyue-reader >/dev/null; sleep 3; curl {flags} -fsS {scheme}://127.0.0.1:{target['service_port']}/api/health; rm -f {shlex.quote(remote_bundle)} /tmp/{manifest.name}"
        health=remote.ssh(script);job.complete({"contentRevision":revision,"health":health,"media":sync_result},"点读资源同步完成")
    return run_task("resource_sync",worker)
def start_rollback(release):
    def worker(job,remote,target):
        root=target["remote_root"];image=f"shiyue-reader:{release}";scheme="https" if target["install_recording"] else "http";flags="-k" if target["install_recording"] else "";job.update(20,f"检查Docker镜像 {release}")
        run=docker_run_command(target,image);restore=docker_run_previous_command(target)
        script=f"set -e; docker image inspect {shlex.quote(image)} >/dev/null; previous_image=$(docker inspect -f '{{{{.Config.Image}}}}' shiyue-reader 2>/dev/null || true); docker rm -f shiyue-reader >/dev/null 2>&1 || true; ln -sfn {shlex.quote(root)}/releases/{shlex.quote(release)} {shlex.quote(root)}/current; {run}; sleep 3; curl {flags} -fsS {scheme}://127.0.0.1:{target['service_port']}/api/health || {{ docker logs --tail 150 shiyue-reader || true; docker rm -f shiyue-reader; [ -n \"$previous_image\" ] && {restore}; exit 1; }}"
        health=remote.ssh(script);job.complete({"releaseId":release,"health":health},"版本回滚完成")
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
    code=db.execute("SELECT result_json FROM deployment_jobs WHERE kind='code_deploy' AND status='complete' ORDER BY id DESC LIMIT 1").fetchone()
    content=db.execute("SELECT result_json FROM deployment_jobs WHERE kind='resource_sync' AND status='complete' ORDER BY id DESC LIMIT 1").fetchone();db.close()
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
        remote=Remote(target,job);output=remote.ssh("current=$(docker inspect -f '{{.Config.Image}}' shiyue-reader 2>/dev/null | sed 's#^shiyue-reader:##' || true); docker images --format '{{.Tag}}' shiyue-reader | grep '^code-' | while read b; do [ \"$b\" = \"$current\" ] && echo \"$b|current\" || echo \"$b|available\"; done");job.complete()
        return [{"releaseId":line.split("|",1)[0],"status":line.split("|",1)[1]} for line in output.splitlines() if line.startswith("code-") and "|" in line]
    except Exception as exc:job.fail(exc);return []
