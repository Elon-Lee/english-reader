#!/usr/bin/env python3
"""Versioned code deployment and finished-resource synchronization."""
import gzip,hashlib,io,ipaddress,json,os,re,secrets,shlex,shutil,sqlite3,subprocess,tarfile,tempfile,threading,time
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
SAAS_IMAGE="shiyue-saas-runtime:20261012-1"
SAAS_FRONTEND_PORT=5173
SAAS_BACKEND_PORT=8790
POSTGRES_IMAGE="postgres:16-bookworm"
REDIS_IMAGE="redis:7-bookworm"
TASK_LOCK=threading.Lock();MEMORY_PASSWORDS={}
PRIVATE_CONFIG=ROOT/".dioco.local.json"

def now():return datetime.now().astimezone().isoformat(timespec="seconds")
def connect():
    from library_db import connect as library_connect
    return library_connect()

def keychain_service(target):return f"shiyue-deploy:{target['username']}@{target['host']}:{target['port']}"
def save_password(target,password):
    if shutil.which("security"):
        try:
            result=subprocess.run(["security","add-generic-password","-U","-a",target["username"],"-s",keychain_service(target),"-w",password],text=True,capture_output=True,timeout=15)
        except subprocess.TimeoutExpired as exc:raise ValueError("保存SSH密码到macOS钥匙串超时") from exc
        if result.returncode!=0:raise ValueError("无法保存SSH密码到macOS钥匙串："+(result.stderr.strip() or "security命令失败"))
    MEMORY_PASSWORDS[target["id"]]=password
def load_password(target):
    if target["id"] in MEMORY_PASSWORDS:return MEMORY_PASSWORDS[target["id"]]
    if shutil.which("security"):
        result=subprocess.run(["security","find-generic-password","-a",target["username"],"-s",keychain_service(target),"-w"],text=True,capture_output=True)
        if result.returncode==0:return result.stdout.strip()
    return ""

def get_target(target_id):
    try:target_id=int(target_id)
    except (TypeError,ValueError):return None
    db=connect();row=db.execute("SELECT * FROM deployment_targets WHERE id=?",(target_id,)).fetchone();db.close();return dict(row) if row else None
def list_targets():
    db=connect();rows=[dict(row) for row in db.execute("SELECT * FROM deployment_targets ORDER BY updated_at DESC,id")]
    latest={}
    for row in db.execute("SELECT * FROM deployment_jobs WHERE target_id IS NOT NULL AND kind NOT IN ('release_list','content_release_list') ORDER BY id DESC"):
        latest.setdefault(row["target_id"],dict(row))
    db.close();result=[]
    for row in rows:
        item=public_target(row);job=latest.get(row["id"])
        item["latestJob"]={key:job.get(key) for key in ("id","kind","status","progress","step","error","updated_at")} if job else None
        result.append(item)
    return result
def save_target(data,password=""):
    host=str(data.get("host","")).strip();username=str(data.get("username","root")).strip() or "root"
    if not host:raise ValueError("请输入SSH地址")
    port=max(1,min(65535,int(data.get("port",22))));remote_root=str(data.get("remoteRoot","/srv/shiyue")).strip() or "/srv/shiyue"
    if remote_root in {"","/","/root","/home","/srv"}:raise ValueError("远程目录范围过大，请使用类似 /srv/shiyue 的独立目录")
    service_port=SAAS_FRONTEND_PORT;stamp=now();db=connect();target_id=data.get("id") or data.get("targetId")
    if target_id:
        target_id=int(target_id)
        if not db.execute("SELECT 1 FROM deployment_targets WHERE id=?",(target_id,)).fetchone():db.close();raise ValueError("远程节点不存在")
        db.execute("UPDATE deployment_targets SET name=?,host=?,port=?,username=?,remote_root=?,service_port=?,install_recording=?,use_https=?,updated_at=? WHERE id=?",(str(data.get("name","远程服务器")).strip() or "远程服务器",host,port,username,remote_root,service_port,1 if data.get("installRecording",True) else 0,1 if data.get("useHttps",True) else 0,stamp,target_id))
    else:
        existing=db.execute("SELECT id FROM deployment_targets WHERE host=? AND port=? AND username=? AND remote_root=? ORDER BY id LIMIT 1",(host,port,username,remote_root)).fetchone()
        if existing:
            target_id=existing[0];db.execute("UPDATE deployment_targets SET name=?,service_port=?,install_recording=?,use_https=?,updated_at=? WHERE id=?",(str(data.get("name","远程服务器")).strip() or "远程服务器",service_port,1 if data.get("installRecording",True) else 0,1 if data.get("useHttps",True) else 0,stamp,target_id))
        else:
            cur=db.execute("INSERT INTO deployment_targets(name,host,port,username,remote_root,service_port,install_recording,use_https,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(str(data.get("name","远程服务器")).strip() or "远程服务器",host,port,username,remote_root,service_port,1 if data.get("installRecording",True) else 0,1 if data.get("useHttps",True) else 0,stamp,stamp));target_id=cur.lastrowid
    row=dict(db.execute("SELECT * FROM deployment_targets WHERE id=?",(target_id,)).fetchone())
    try:
        if password:save_password(row,password)
        db.commit()
    except Exception:
        db.rollback();db.close();raise
    db.close()
    return public_target(row)
def delete_target_config(target_id):
    target=get_target(target_id)
    if not target:raise ValueError("远程节点不存在")
    db=connect();active=db.execute("SELECT 1 FROM deployment_jobs WHERE target_id=? AND status IN ('queued','running')",(target["id"],)).fetchone()
    if active:db.close();raise ValueError("该节点仍有任务运行，不能删除配置")
    db.execute("DELETE FROM deployment_releases WHERE target_id=?",(target["id"],));db.execute("DELETE FROM deployment_jobs WHERE target_id=?",(target["id"],));db.execute("DELETE FROM deployment_targets WHERE id=?",(target["id"],));db.commit();db.close()
    MEMORY_PASSWORDS.pop(target["id"],None)
    for path in (KEYS/f"target-{target['id']}-ed25519",KEYS/f"target-{target['id']}-ed25519.pub"):
        path.unlink(missing_ok=True)
    if shutil.which("security"):subprocess.run(["security","delete-generic-password","-a",target["username"],"-s",keychain_service(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return {"id":target["id"],"name":target["name"],"deleted":True}
def public_target(row):
    if not row:return None
    result=dict(row);key=KEYS/f"target-{row['id']}-ed25519";result["passwordConfigured"]=bool(load_password(row) or key.exists());result["keyConfigured"]=key.exists();result.pop("created_at",None);return result

class Job:
    def __init__(self,kind,target_id=None):
        LOGS.mkdir(parents=True,exist_ok=True);stamp=now();db=connect();cur=db.execute("INSERT INTO deployment_jobs(kind,status,progress,step,log_path,target_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(kind,"queued",0,"等待开始","",target_id,stamp,stamp));self.id=cur.lastrowid;self.target_id=target_id;self.log=LOGS/f"{self.id}.log";db.execute("UPDATE deployment_jobs SET log_path=? WHERE id=?",(str(self.log),self.id));db.commit();db.close();self.write(f"任务 #{self.id} · {kind} · 节点 {target_id or '-'} · {stamp}")
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
def build_frontend_assets(job):
    package=ROOT/"package.json"
    if not package.is_file():raise ValueError("缺少 package.json，无法构建 React 前端")
    job.update(27,"构建 React 生产前端")
    try:
        result=subprocess.run(["npm","run","build:modern"],cwd=ROOT,text=True,capture_output=True,timeout=600)
    except FileNotFoundError as exc:raise ValueError("本机缺少 npm，无法构建 React 前端") from exc
    except subprocess.TimeoutExpired as exc:raise ValueError("React 前端构建超时") from exc
    output="\n".join(part.strip() for part in (result.stdout,result.stderr) if part and part.strip())
    if result.returncode!=0:
        if output:job.write(output[-4000:])
        raise ValueError("React 前端构建失败")
    required=(ROOT/"reader/site/index.html",ROOT/"reader/site/assets/index.js",ROOT/"reader/site/assets/index.css")
    missing=[str(path.relative_to(ROOT)) for path in required if not path.is_file() or path.stat().st_size==0]
    if missing:raise ValueError("React 前端构建产物不完整："+", ".join(missing))
    summary=next((line for line in reversed(output.splitlines()) if line.strip()),"构建完成")
    job.write(f"React 生产前端已构建：{summary[:500]}")

def release_metadata(release):
    commit=""
    dirty=False
    try:
        commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,timeout=15,check=True).stdout.strip()
        dirty=bool(subprocess.run(["git","status","--porcelain"],cwd=ROOT,text=True,capture_output=True,timeout=15,check=True).stdout.strip())
    except (FileNotFoundError,subprocess.SubprocessError):pass
    return {"releaseId":release,"gitCommit":commit,"sourceDirty":dirty,"builtAt":now(),"packageFormat":2}

def code_files():
    files=[ROOT/"reader",ROOT/"deployment",ROOT/"requirements-saas.txt",ROOT/"start-reader.sh",ROOT/"start-reader-https.sh"]
    files += list((ROOT/"tools").glob("*.py"))+[ROOT/"tools/deployment",ROOT/"tools/saas_migrations",ROOT/"tools/vendor/ECDICT/lemma.en.txt"]
    return files
def build_code_package(job,release):
    metadata=release_metadata(release)
    build_frontend_assets(job)
    target=STATE/f"{release}.tar.gz";STATE.mkdir(parents=True,exist_ok=True)
    def archive_filter(info):
        if "__pycache__" in info.name or info.name.endswith((".pyc",".pyo",".DS_Store")):return None
        if info.name=="reader/modern.html" or info.name=="reader/modern-assets" or info.name.startswith("reader/modern-assets/"):return None
        return info
    with tarfile.open(target,"w:gz") as archive:
        for path in code_files():
            if path.exists():archive.add(path,arcname=path.relative_to(ROOT),filter=archive_filter)
        metadata_bytes=json.dumps(metadata,ensure_ascii=False,indent=2).encode("utf-8")
        info=tarfile.TarInfo(".shiyue-release.json");info.size=len(metadata_bytes);info.mtime=int(time.time());info.mode=0o644
        archive.addfile(info,io.BytesIO(metadata_bytes))
    digest=hashlib.sha256(target.read_bytes()).hexdigest();job.write(f"代码包：{target.name} · {target.stat().st_size/1024/1024:.1f} MiB · sha256={digest}");return target,digest

def local_env_values():
    values={}
    path=ROOT/".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:continue
            key,value=line.split("=",1);values[key.strip()]=value.strip().strip('"').strip("'")
    return {**values,**{key:value for key,value in os.environ.items() if value}}

def local_saas_database_url():
    value=str(local_env_values().get("DATABASE_URL","")).strip()
    if not value:raise ValueError("本机 .env 缺少 DATABASE_URL，无法迁移 SaaS 数据")
    return value

def build_saas_database_dump(job,release):
    target=STATE/f"{release}.database.dump";target.parent.mkdir(parents=True,exist_ok=True)
    pg_dump=shutil.which("pg_dump") or "/usr/local/opt/postgresql@16/bin/pg_dump"
    if not Path(pg_dump).is_file():raise ValueError("本机缺少 pg_dump，无法迁移 SaaS 数据")
    job.update(32,"导出本地 SaaS PostgreSQL 数据库")
    try:subprocess.run([pg_dump,"--format=custom","--no-owner","--no-acl","--file",str(target),local_saas_database_url()],cwd=ROOT,check=True,timeout=900,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:raise ValueError("本地 SaaS PostgreSQL 导出失败") from exc
    if not target.is_file() or target.stat().st_size<1024:raise ValueError("本地 SaaS 数据库导出文件异常")
    digest=hashlib.sha256(target.read_bytes()).hexdigest();job.write(f"SaaS 数据库快照：{target.name} · {target.stat().st_size/1024/1024:.1f} MiB · sha256={digest}");return target,digest

def export_saas_public_content(job,revision):
    stage=STATE/"staging"/revision;shutil.rmtree(stage,ignore_errors=True);stage.mkdir(parents=True)
    bundle=STATE/f"{revision}.public.json.gz";manifest=STATE/f"{revision}.public.manifest.json"
    media_root=Path(local_env_values().get("MEDIA_ROOT",str(ROOT/"books"))).expanduser().resolve()
    python=ROOT/".local/saas-venv/bin/python"
    if not python.is_file():python=Path(sys.executable)
    command=[str(python),str(ROOT/"tools/deployment/saas_public_sync.py"),"export","--database-url",local_saas_database_url(),"--media-root",str(media_root),"--bundle",str(bundle),"--manifest",str(manifest)]
    try:result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,check=True,timeout=900)
    except subprocess.CalledProcessError as exc:raise ValueError("生成 SaaS 公共内容包失败") from exc
    summary=json.loads(result.stdout.strip().splitlines()[-1]);payload=json.loads(manifest.read_text(encoding="utf-8"));payload["revision"]=revision;manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    for item in payload.get("files",[]):
        source=(media_root/item["path"]).resolve();source.relative_to(media_root)
        destination=stage/item["path"];destination.parent.mkdir(parents=True,exist_ok=True);destination.symlink_to(source)
    job.write(f"待审核内容：{summary['catalogBooks']} 本 · {summary['files']} 个文件 · {summary['bytes']/1024/1024:.1f} MiB；上传后需在线上运营后台审核发布")
    return stage,bundle,manifest,summary

def ensure_remote_docker(job,remote):
    probe=remote.ssh("if command -v docker >/dev/null 2>&1; then (docker info >/dev/null 2>&1 || (command -v systemctl >/dev/null 2>&1 && systemctl enable --now docker >/dev/null 2>&1) || service docker start >/dev/null 2>&1 || true); docker info >/dev/null 2>&1 && echo SHIYUE_DOCKER_READY; fi")
    if "SHIYUE_DOCKER_READY" in probe:
        job.write("远程Docker已安装且运行正常");return
    job.update(9,"远程安装Docker")
    script="""set -e
as_root=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || { echo '当前SSH账号不是root且没有sudo，无法安装Docker' >&2; exit 2; }
  as_root=sudo
fi
if command -v yum >/dev/null 2>&1; then
  echo '检测到yum，使用阿里云Docker CE仓库安装'
  $as_root yum install -y yum-utils
  $as_root rm -f /etc/yum.repos.d/docker-ce.repo
  $as_root yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
  if ! $as_root grep -Eq 'mirrors\\.aliyun\\.com/docker-ce' /etc/yum.repos.d/docker-ce.repo; then
    echo '阿里云Docker CE仓库配置写入失败' >&2
    exit 3
  fi
  $as_root yum clean all
  $as_root yum makecache fast || $as_root yum makecache
  installed=0
  attempt=1
  while [ "$attempt" -le 3 ]; do
    echo "Docker CE安装尝试 $attempt/3"
    if $as_root yum --setopt=retries=5 --setopt=timeout=60 install -y docker-ce docker-ce-cli containerd.io; then
      installed=1
      break
    fi
    echo "Docker CE第 $attempt 次安装失败，清理缓存后重试" >&2
    $as_root yum clean packages || true
    $as_root rm -rf /var/cache/yum/*/docker-ce-* /var/cache/yum/*/*/packages/docker-* /var/cache/yum/*/*/packages/containerd.io-* 2>/dev/null || true
    $as_root yum makecache fast || $as_root yum makecache
    attempt=$((attempt+1))
  done
  if [ "$installed" -ne 1 ]; then
    echo 'Docker CE通过阿里云仓库连续3次安装失败，请检查服务器到mirrors.aliyun.com的网络' >&2
    exit 4
  fi
elif command -v curl >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
elif command -v wget >/dev/null 2>&1; then
  wget -qO- https://get.docker.com | sh
elif command -v apt-get >/dev/null 2>&1; then
  $as_root apt-get update -y && $as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
elif command -v dnf >/dev/null 2>&1; then
  $as_root dnf install -y docker
else
  echo '无法自动安装Docker：远程缺少curl、wget和支持的包管理器' >&2
  exit 2
fi
if command -v systemctl >/dev/null 2>&1; then
  $as_root systemctl enable --now docker
else
  $as_root service docker start
fi
if ! docker info >/dev/null 2>&1; then
  echo 'Docker已安装，但daemon启动或连接失败' >&2
  if command -v systemctl >/dev/null 2>&1; then $as_root systemctl status docker --no-pager -l >&2 || true; fi
  exit 5
fi
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
    root=shlex.quote(target["remote_root"]);port=int(target["service_port"]);recording=bool(target["install_recording"]);use_https=bool(target.get("use_https",1))
    options=["docker run -d --name shiyue-reader --restart unless-stopped","--network host","-e READER_HOST=0.0.0.0",f"-e READER_PORT={port}","-e SHIYUE_RUNTIME_MODE=reader",
      f"-v {root}/current/reader:/app/reader:ro",f"-v {root}/current/tools:/app/tools:ro",f"-v {root}/shared/books:/app/books",f"-v {root}/shared/.local:/app/.local",f"-v {root}/shared/cache:/app/.cache",f"-v {root}/shared/config/dioco.local.json:/app/.dioco.local.json"]
    if recording:options += [f"-v {root}/shared/whisper/ggml-base.en.bin:/opt/shiyue/models/ggml-base.en.bin:ro"]
    if use_https:options += [f"-v {root}/shared/https:/certs:ro","-e READER_TLS_CERT=/certs/server-cert.pem","-e READER_TLS_KEY=/certs/server-key.pem"]
    options.append(shlex.quote(image));return " \\\n  ".join(options)

def health_check_command(target):
    scheme="https" if target.get("use_https",1) else "http";port=int(target["service_port"])
    code=f"import json,ssl,urllib.request; u='{scheme}://127.0.0.1:{port}/api/health'; c=ssl._create_unverified_context() if u.startswith('https') else None; print(urllib.request.urlopen(u,context=c,timeout=20).read().decode())"
    return f"docker exec shiyue-reader python3 -c {shlex.quote(code)}"

def saas_app_run_command(target,release_path,name="shiyue-saas",port=None,restart=True):
    root=shlex.quote(target["remote_root"]);release=shlex.quote(release_path);port=int(port or SAAS_BACKEND_PORT);recording=bool(target["install_recording"])
    options=[f"docker run -d --name {shlex.quote(name)}"]
    if restart:options.append("--restart unless-stopped")
    options += ["--network host",f"--env-file {root}/shared/config/saas.env","-e READER_HOST=127.0.0.1",f"-e READER_PORT={port}","-e SHIYUE_RUNTIME_MODE=saas","-e SHIYUE_SAAS_ENABLED=1","-e MEDIA_ROOT=/app/books","-e SAAS_BACKUP_ROOT=/state/backups/saas","-e SHIYUE_PDF_OCR=/opt/shiyue/pdf_ocr","-e SHIYUE_YTDLP=/usr/local/bin/yt-dlp","-e SHIYUE_NODE=/usr/bin/node",
      f"-v {release}/reader:/app/reader:ro,z",f"-v {release}/tools:/app/tools:ro,z",f"-v {root}/shared/books:/app/books:z",f"-v {root}/shared/.local:/app/.local:z",f"-v {root}/shared/cache:/app/.cache:z",f"-v {root}/backups:/state/backups:z"]
    if recording:options += [f"-v {root}/shared/whisper/ggml-base.en.bin:/opt/shiyue/models/ggml-base.en.bin:ro,z","-e SHIYUE_WHISPER_CLI=/opt/shiyue/whisper/whisper-cli","-e SHIYUE_WHISPER_MODEL=/opt/shiyue/models/ggml-base.en.bin"]
    options.append(shlex.quote(SAAS_IMAGE));return " \\\n  ".join(options)

def saas_frontend_run_command(target,release_path,name="shiyue-saas-frontend",port=None,backend_port=None,restart=True):
    root=shlex.quote(target["remote_root"]);release=shlex.quote(release_path);port=int(port or SAAS_FRONTEND_PORT);backend_port=int(backend_port or SAAS_BACKEND_PORT)
    options=[f"docker run -d --name {shlex.quote(name)}"]
    if restart:options.append("--restart unless-stopped")
    options += ["--network host",f"-e FRONTEND_HOST=0.0.0.0",f"-e FRONTEND_PORT={port}",f"-e SAAS_BACKEND_URL=http://127.0.0.1:{backend_port}","-e FRONTEND_ROOT=/app/site",f"-v {release}/reader/site:/app/site:ro,z",f"-v {release}/tools:/app/tools:ro,z",shlex.quote(SAAS_IMAGE),"python3","/app/tools/saas_frontend_server.py"]
    if target.get("use_https",0):options[-3:-3]=[f"-e FRONTEND_TLS_CERT=/certs/server-cert.pem",f"-e FRONTEND_TLS_KEY=/certs/server-key.pem",f"-v {root}/shared/https:/certs:ro,z"]
    return " \\\n  ".join(options)

def saas_health_check_command(port,container="shiyue-saas"):
    backend_port=SAAS_BACKEND_PORT if int(port)==SAAS_FRONTEND_PORT else int(port)
    code=f"import json,urllib.request; h=json.loads(urllib.request.urlopen('http://127.0.0.1:{backend_port}/api/health',timeout=20).read()); assert h.get('status')=='ok' and h.get('saasEnabled') and h.get('redisReady'); print(json.dumps(h,ensure_ascii=False))"
    return f"docker exec {shlex.quote(container)} python3 -c {shlex.quote(code)}"

def saas_frontend_health_check_command(port=SAAS_FRONTEND_PORT,container="shiyue-saas-frontend",https=False):
    scheme="https" if https else "http";context=",context=ssl._create_unverified_context()" if https else ""
    code=f"import ssl,urllib.request; h=urllib.request.urlopen('{scheme}://127.0.0.1:{int(port)}/',timeout=20{context}); assert h.status==200 and b'<div id=\\\"root\\\"' in h.read(); a=urllib.request.urlopen('{scheme}://127.0.0.1:{int(port)}/api/health',timeout=20{context}); assert a.status==200; print('SHIYUE_FRONTEND_READY')"
    return f"docker exec {shlex.quote(container)} python3 -c {shlex.quote(code)}"

def saas_migration_check_command(container="shiyue-saas-candidate"):
    code="""import sys
sys.path.insert(0,'/app/tools')
from pathlib import Path
from saas_auth import SaaSService
import os
service=SaaSService(os.environ.get('DATABASE_URL',''))
service.ensure_migrated()
versions=sorted(path.name for path in Path('/app/tools/saas_migrations').glob('*.sql'))
print('SHIYUE_MIGRATIONS_READY '+','.join(versions))"""
    return f"docker exec {shlex.quote(container)} python3 -c {shlex.quote(code)}"

def ensure_remote_saas_config(job,remote,target):
    root=target["remote_root"];destination=f"{root}/shared/config/saas.env"
    found=remote.ssh(f"test -s {shlex.quote(destination)} && echo SHIYUE_SAAS_ENV_READY || true")
    if "SHIYUE_SAAS_ENV_READY" in found:
        scheme="https" if target.get("use_https",0) else "http"
        remote.ssh(f"sed -i -E 's#^APP_BASE_URL=.*#APP_BASE_URL={scheme}://{target['host']}:{SAAS_FRONTEND_PORT}#' {shlex.quote(destination)}")
        job.write("远程 SaaS 密钥配置已存在，保留现有数据库和会话密钥，并更新前台入口地址");return
    postgres_password=secrets.token_hex(24);redis_password=secrets.token_hex(24);session_secret=secrets.token_urlsafe(48);scheme="https" if target.get("use_https",0) else "http"
    values={
      "POSTGRES_DB":"shiyue","POSTGRES_USER":"shiyue","POSTGRES_PASSWORD":postgres_password,
      "DATABASE_URL":f"postgresql://shiyue:{postgres_password}@127.0.0.1:5432/shiyue","REDIS_PASSWORD":redis_password,"REDIS_URL":f"redis://:{redis_password}@127.0.0.1:6379/0",
      "SESSION_SECRET":session_secret,"APP_BASE_URL":f"{scheme}://{target['host']}:{SAAS_FRONTEND_PORT}","SHIYUE_SAAS_AUTO_MIGRATE":"1","BOOTSTRAP_ADMIN_EMAIL":"","BOOTSTRAP_ADMIN_PASSWORD":"",
    }
    with tempfile.TemporaryDirectory(prefix="shiyue-saas-env-") as temp:
        path=Path(temp)/"saas.env";path.write_text("".join(f"{key}={value}\n" for key,value in values.items()),encoding="utf-8");os.chmod(path,0o600)
        remote.scp(path,f"/tmp/shiyue-saas-{target['id']}.env")
    remote.ssh(f"set -e; mkdir -p {shlex.quote(root)}/shared/config; install -m 600 /tmp/shiyue-saas-{target['id']}.env {shlex.quote(destination)}; rm -f /tmp/shiyue-saas-{target['id']}.env")
    job.write("已生成远程专用 PostgreSQL、Redis 和会话密钥（未写入日志）")

def prepare_remote_saas_release(remote,target,release,package_name,package_digest):
    root=shlex.quote(target["remote_root"])
    return remote.ssh(f"""set -euo pipefail
mkdir -p {root}/releases/{release} {root}/shared/books {root}/shared/.local {root}/shared/cache {root}/shared/config {root}/shared/postgres {root}/shared/redis {root}/backups/saas {root}/backups/resources {root}/manifests/history {root}/logs
archive=/tmp/{package_name}
actual_digest=$(sha256sum "$archive" | awk '{{print $1}}')
[ "$actual_digest" = "{package_digest}" ] || {{ echo '代码包 SHA-256 校验失败' >&2; exit 3; }}
tar -xzf "$archive" -C {root}/releases/{release}
test -s {root}/releases/{release}/reader/site/index.html
test -s {root}/releases/{release}/reader/site/assets/index.js
test -s {root}/releases/{release}/tools/reader_server.py
test -d {root}/releases/{release}/tools/saas_migrations
rm -f "$archive"
""")

def backup_remote_saas_database(job,remote,target,release):
    root=target["remote_root"];backup=f"{root}/backups/saas/pre-upgrade-{release}.dump"
    script=f"""set -euo pipefail
umask 077
set -a; . {shlex.quote(root)}/shared/config/saas.env; set +a
docker exec shiyue-postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > {shlex.quote(backup)}
test -s {shlex.quote(backup)}
chmod 600 {shlex.quote(backup)}
sha256sum {shlex.quote(backup)} | awk '{{print "SHIYUE_SAAS_BACKUP_READY " $1}}'
"""
    output=remote.ssh(script)
    if "SHIYUE_SAAS_BACKUP_READY" not in output:raise ValueError("远程 SaaS 数据库备份未完成")
    job.write(f"远程数据库备份已完成：{Path(backup).name}")
    return backup

def check_remote_saas_upgrade_target(remote,target):
    root=shlex.quote(target["remote_root"])
    output=remote.ssh(f"""set -euo pipefail
docker info >/dev/null
docker inspect shiyue-saas >/dev/null
docker inspect shiyue-postgres >/dev/null
docker inspect shiyue-redis >/dev/null
docker image inspect {shlex.quote(SAAS_IMAGE)} >/dev/null
test -s {root}/shared/config/saas.env
test -s {root}/current/.shiyue-release.json
test -s {root}/current/reader/site/index.html
test "$(docker inspect -f '{{{{.State.Running}}}}' shiyue-saas)" = true
docker exec shiyue-saas python3 -c 'import json,urllib.request; import os; port=os.environ.get("READER_PORT","8765"); h=json.load(urllib.request.urlopen("http://127.0.0.1:"+port+"/api/health",timeout=20)); assert h.get("status")=="ok" and h.get("runtimeMode")=="saas" and h.get("saasEnabled") and h.get("redisReady")'
echo SHIYUE_SAAS_UPGRADE_READY
""")
    if "SHIYUE_SAAS_UPGRADE_READY" not in output:raise ValueError("远程 SaaS 服务未通过升级前检查")

def ensure_remote_saas_services(job,remote,target,release):
    root=target["remote_root"];release_path=f"{root}/releases/{release}";env=f"{root}/shared/config/saas.env"
    job.update(50,"安装并启动 PostgreSQL 与 Redis")
    script=f"""set -euo pipefail
pull_official_image() {{
  target="$1"
  mirror="$2"
  docker image inspect "$target" >/dev/null 2>&1 && return 0
  attempt=1
  while [ "$attempt" -le 3 ]; do
    if docker pull "$mirror"; then docker tag "$mirror" "$target"; return 0; fi
    echo "国内镜像拉取失败，尝试 Docker Hub（$attempt/3）" >&2
    if docker pull "$target"; then return 0; fi
    attempt=$((attempt+1)); sleep 3
  done
  return 1
}}
pull_official_image {POSTGRES_IMAGE} m.daocloud.io/docker.io/library/{POSTGRES_IMAGE}
pull_official_image {REDIS_IMAGE} m.daocloud.io/docker.io/library/{REDIS_IMAGE}
set -a; . {shlex.quote(env)}; set +a
if docker container inspect shiyue-postgres >/dev/null 2>&1; then
  docker start shiyue-postgres >/dev/null 2>&1 || true
  sleep 2
  docker exec shiyue-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1 || docker rm -f shiyue-postgres >/dev/null
fi
if ! docker container inspect shiyue-postgres >/dev/null 2>&1; then
  docker run -d --name shiyue-postgres --restart unless-stopped -p 127.0.0.1:5432:5432 --env-file {shlex.quote(env)} -v {shlex.quote(root)}/shared/postgres:/var/lib/postgresql/data:Z --shm-size=256m {POSTGRES_IMAGE} -c shared_buffers=128MB -c max_connections=100 >/dev/null
fi
printf 'bind 0.0.0.0\nprotected-mode yes\nrequirepass %s\nappendonly yes\nmaxmemory 192mb\nmaxmemory-policy allkeys-lru\n' "$REDIS_PASSWORD" > {shlex.quote(root)}/shared/config/redis.conf
redis_uid=$(docker run --rm --entrypoint id {REDIS_IMAGE} -u redis)
redis_gid=$(docker run --rm --entrypoint id {REDIS_IMAGE} -g redis)
chown "$redis_uid:$redis_gid" {shlex.quote(root)}/shared/config/redis.conf {shlex.quote(root)}/shared/redis
chmod 600 {shlex.quote(root)}/shared/config/redis.conf
if docker container inspect shiyue-redis >/dev/null 2>&1; then
  docker start shiyue-redis >/dev/null 2>&1 || true
  sleep 1
  docker exec shiyue-redis redis-cli -a "$REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG || docker rm -f shiyue-redis >/dev/null
fi
if ! docker container inspect shiyue-redis >/dev/null 2>&1; then
  docker run -d --name shiyue-redis --restart unless-stopped -p 127.0.0.1:6379:6379 -v {shlex.quote(root)}/shared/redis:/data:Z -v {shlex.quote(root)}/shared/config/redis.conf:/usr/local/etc/redis/redis.conf:ro,Z {REDIS_IMAGE} redis-server /usr/local/etc/redis/redis.conf >/dev/null
fi
ready=0
for attempt in $(seq 1 60); do docker exec shiyue-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1 && ready=1 && break; sleep 1; done
[ "$ready" -eq 1 ] || {{ docker logs --tail 200 shiyue-postgres >&2; exit 4; }}
docker exec shiyue-redis redis-cli -a "$REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG
"""
    remote.ssh(script)
    job.update(57,"构建 SaaS 运行镜像")
    remote.ssh(f"set -e; docker build -f {shlex.quote(release_path)}/deployment/docker/Dockerfile.saas -t {shlex.quote(SAAS_IMAGE)} {shlex.quote(release_path)}; docker image inspect {shlex.quote(SAAS_IMAGE)} >/dev/null")

def restore_remote_saas_database(job,remote,target,dump,digest):
    root=target["remote_root"];remote_dump=f"/tmp/{dump.name}";job.update(63,"上传并初始化 SaaS PostgreSQL 数据")
    remote.scp(dump,remote_dump)
    script=f"""set -euo pipefail
actual=$(sha256sum {shlex.quote(remote_dump)} | awk '{{print $1}}')
[ "$actual" = "{digest}" ] || {{ echo '数据库快照 SHA-256 校验失败' >&2; exit 3; }}
set -a; . {shlex.quote(root)}/shared/config/saas.env; set +a
existing=$(docker exec shiyue-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT COALESCE(to_regclass('public.schema_migrations')::text,'')")
if [ -z "$existing" ]; then
  docker cp {shlex.quote(remote_dump)} shiyue-postgres:/tmp/shiyue-initial.dump
  docker exec shiyue-postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error /tmp/shiyue-initial.dump
  docker exec shiyue-postgres rm -f /tmp/shiyue-initial.dump
  echo SHIYUE_DATABASE_RESTORED
else
  echo SHIYUE_DATABASE_PRESERVED
fi
rm -f {shlex.quote(remote_dump)}
"""
    output=remote.ssh(script);restored="SHIYUE_DATABASE_RESTORED" in output;job.write("远程 PostgreSQL 已从本地正式库初始化" if restored else "远程 PostgreSQL 已存在，未覆盖远程用户数据");return restored

def prune_initial_database_to_published_content(job,remote,target):
    root=target["remote_root"]
    sql="""BEGIN;
CREATE TEMP TABLE shiyue_public_catalog AS SELECT id,source_content_book_id FROM catalog_books WHERE publication_status IN ('draft','published') AND rights_status IN ('public_domain','licensed','private');
DELETE FROM official_book_unlocks WHERE catalog_book_id NOT IN (SELECT id FROM shiyue_public_catalog);
DELETE FROM user_library WHERE catalog_book_id NOT IN (SELECT id FROM shiyue_public_catalog);
DELETE FROM catalog_books WHERE id NOT IN (SELECT id FROM shiyue_public_catalog);
DELETE FROM media_assets ma WHERE NOT EXISTS (SELECT 1 FROM shiyue_public_catalog pc WHERE pc.id=ma.catalog_book_id OR pc.source_content_book_id=ma.content_book_id);
DELETE FROM content_books WHERE id NOT IN (SELECT source_content_book_id FROM shiyue_public_catalog WHERE source_content_book_id IS NOT NULL);
UPDATE catalog_books SET publication_status='draft',reviewed_by=NULL,published_at=NULL,updated_at=NOW();
COMMIT;"""
    job.update(67,"移除首次快照中的非公开书籍数据")
    command=f"set -e; set -a; . {shlex.quote(root)}/shared/config/saas.env; set +a; docker exec shiyue-postgres psql -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -c {shlex.quote(sql)}"
    remote.ssh(command);job.write("远程初始数据库仅保留已登记书目及关联内容，统一设为未审核；需在线上运营后台审核后发布。账号、订阅和平台配置已保留")

def local_dioco_config():
    if not PRIVATE_CONFIG.exists():return None
    try:data=json.loads(PRIVATE_CONFIG.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):return None
    email=str(data.get("userEmail","")).strip();token=str(data.get("diocoToken","")).strip()
    if not email or "@" not in email or not token:return None
    return {"userEmail":email,"diocoToken":token}

def sync_remote_private_config(job,remote,target):
    """Fill an unconfigured reader node from the local secret without logging it.

    A token edited directly on the remote reader is preserved. This makes deploy,
    program upgrade and content sync safe to repeat across independently managed
    nodes while still repairing older nodes whose deployment created an empty {}.
    """
    local=local_dioco_config();root=target["remote_root"]
    destination=f"{root}/shared/config/dioco.local.json"
    configured=remote.ssh(
        f"test -f {shlex.quote(destination)} && "
        f"grep -Eq '\"userEmail\"[[:space:]]*:[[:space:]]*\"[^\"]+\"' {shlex.quote(destination)} && "
        f"grep -Eq '\"diocoToken\"[[:space:]]*:[[:space:]]*\"[^\"]+\"' {shlex.quote(destination)} && "
        "echo SHIYUE_DIOCO_CONFIGURED || true"
    )
    if "SHIYUE_DIOCO_CONFIGURED" in configured:
        job.write("远程词典服务凭据已配置，保留远程配置")
        return {"configured":True,"uploaded":False,"source":"remote"}
    if not local:
        job.write("本机未配置Dioco凭据；远程可在系统设置中单独配置")
        return {"configured":False,"uploaded":False,"source":"none"}
    with tempfile.TemporaryDirectory(prefix="shiyue-private-config-") as tmp:
        staged=Path(tmp)/"dioco.local.json"
        staged.write_text(json.dumps(local,ensure_ascii=False,indent=2),encoding="utf-8");os.chmod(staged,0o600)
        remote.ssh(f"mkdir -p {shlex.quote(root)}/shared/config")
        remote_path=f"/tmp/shiyue-dioco-{target['id']}.json"
        remote.scp(staged,remote_path)
        remote.ssh(f"install -m 600 {shlex.quote(remote_path)} {shlex.quote(destination)} && rm -f {shlex.quote(remote_path)}")
    job.write("已安全同步词典与语境服务凭据（日志不包含账号和令牌）")
    return {"configured":True,"uploaded":True,"source":"local"}

def remote_dioco_check(job,remote,target):
    scheme="https" if target.get("use_https",1) else "http";port=int(target["service_port"])
    code=f'''import json,ssl,urllib.request
base="{scheme}://127.0.0.1:{port}"
context=ssl._create_unverified_context() if base.startswith("https") else None
try:
    settings=json.loads(urllib.request.urlopen(base+"/api/settings",context=context,timeout=15).read())
    if not settings.get("tokenConfigured"):
        print("SHIYUE_DIOCO_MISSING")
    else:
        payload=json.dumps({{"word":"incredible","contextSentence":"This is incredible.","expandedContext":"This is incredible."}}).encode()
        request=urllib.request.Request(base+"/api/word-context",data=payload,headers={{"Content-Type":"application/json"}},method="POST")
        result=json.loads(urllib.request.urlopen(request,context=context,timeout=45).read())
        print("SHIYUE_DIOCO_READY" if result.get("explanation") else "SHIYUE_DIOCO_EMPTY")
except Exception as exc:
    print("SHIYUE_DIOCO_ERROR:"+str(exc)[:180])'''
    output=remote.ssh(f"docker exec shiyue-reader python3 -c {shlex.quote(code)}")
    ready="SHIYUE_DIOCO_READY" in output
    if ready:job.write("远程词典与语境接口验证通过")
    elif "SHIYUE_DIOCO_MISSING" in output:job.write("警告：远程尚未配置Dioco凭据，请在系统设置保存")
    else:job.write("警告：远程在线语境接口验证失败，请检查服务器外网访问")
    return ready

def bootstrap_script(target,release,package_name,package_digest):
    if not re.fullmatch(r"code-\d{8}-\d{6}-[A-Za-z0-9]+",release or ""):raise ValueError("无效的代码版本")
    if not re.fullmatch(r"code-[A-Za-z0-9._-]+\.tar\.gz",package_name or ""):raise ValueError("无效的代码包名称")
    if not re.fullmatch(r"[0-9a-f]{64}",package_digest or ""):raise ValueError("无效的代码包校验值")
    root=shlex.quote(target["remote_root"]);run=docker_run_command(target);health=health_check_command(target)
    return f"""set -euo pipefail
systemctl disable --now shiyue-reader >/dev/null 2>&1 || true
mkdir -p {root}/releases/{release} {root}/shared/books {root}/shared/.local {root}/shared/cache {root}/shared/config {root}/backups/databases {root}/backups/resources {root}/manifests/history {root}/logs
[ -f {root}/shared/config/dioco.local.json ] || echo '{{}}' > {root}/shared/config/dioco.local.json
archive=/tmp/{package_name}
actual_digest=$(sha256sum "$archive" | awk '{{print $1}}')
if [ "$actual_digest" != "{package_digest}" ]; then
  echo "代码包校验失败：expected={package_digest} actual=$actual_digest" >&2
  exit 3
fi
tar -xzf /tmp/{package_name} -C {root}/releases/{release}
test -s {root}/releases/{release}/.shiyue-release.json
test -s {root}/releases/{release}/reader/site/index.html
test -s {root}/releases/{release}/reader/site/assets/index.js
test -s {root}/releases/{release}/reader/site/assets/index.css
test -s {root}/releases/{release}/tools/reader_server.py
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
        cover=row.get("cover_url","")
        if cover.startswith("/books/"):paths.append(books_root/unquote(cover[len('/books/'):]))
        for key in ("audio","video"):
            url=data.get(key,"")
            if url.startswith("/books/"):paths.append(books_root/unquote(url[len('/books/'):]))
        for variant in (data.get("videoVariants") or {}).values():
            url=variant.get("url","") if isinstance(variant,dict) else ""
            if url.startswith("/books/"):paths.append(books_root/unquote(url[len('/books/'):]))
        base=data.get("pageBase","")
        if base.startswith("/books/"):
            directory=books_root/unquote(base[len('/books/'):]);paths.extend(directory.glob("page-*.jpg")) if directory.is_dir() else None
        seen=set()
        for source in paths:
            entry=content_file_entry(source,books_root)
            if not entry:continue
            relative,actual=entry
            if str(relative) in seen:continue
            seen.add(str(relative));destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.symlink_to(actual);files.append({"path":str(relative),"size":actual.stat().st_size,"mtime":actual.stat().st_mtime_ns})
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

def sync_saas_public_content(job,remote,target,release_path=None,progress=None,restart=True):
    progress=progress or {"scan":8,"prepare":22,"package":30,"upload":42,"apply":70,"database":78,"merge":88}
    revision=new_release_id("public");job.update(progress["scan"],"扫描本地 SaaS 公共书目与媒体");stage,bundle,manifest,summary=export_saas_public_content(job,revision)
    root=target["remote_root"];release_path=release_path or f"{root}/current";backup=f"{root}/backups/resources/{revision}";remote_bundle=f"{root}/shared/.local/{bundle.name}";remote_manifest=f"/tmp/{manifest.name}"
    job.update(progress["prepare"],"准备远程公共资源目录");remote.ssh(f"set -e; docker inspect shiyue-postgres >/dev/null; docker image inspect {shlex.quote(SAAS_IMAGE)} >/dev/null; mkdir -p {shlex.quote(root)}/shared/books {shlex.quote(backup)} {shlex.quote(root)}/manifests/history {shlex.quote(root)}/shared/.local")
    sync_result=remote.sync_tree_package(stage,f"{root}/shared/books",backup,manifest,f"{root}/manifests/current-saas-public.json",progress)
    apply_helper=f"{revision}.apply.py"
    job.update(progress["database"],"上传待审核书目数据库包");remote.scp(bundle,remote_bundle);remote.scp(manifest,remote_manifest)
    remote.scp(ROOT/"tools/deployment/saas_public_sync.py",f"{root}/shared/.local/{apply_helper}")
    job.update(progress["merge"],"合并公共书目并保留远程用户数据")
    command=(f"docker run --rm --network host --env-file {shlex.quote(root)}/shared/config/saas.env "
      f"-v {shlex.quote(release_path)}/tools:/app/tools:ro,z -v {shlex.quote(root)}/shared/.local:/app/.local:z "
      f"-v {shlex.quote(root)}/manifests:/state/manifests:z {shlex.quote(SAAS_IMAGE)} python3 /app/.local/{shlex.quote(apply_helper)} apply "
      f"--bundle /app/.local/{shlex.quote(bundle.name)} --previous-manifest /state/manifests/current-saas-public.json")
    script=f"""set -euo pipefail
{command}
cp {shlex.quote(remote_manifest)} {shlex.quote(root)}/manifests/current-saas-public.json
cp {shlex.quote(remote_manifest)} {shlex.quote(root)}/manifests/history/{revision}.json
cp {shlex.quote(remote_bundle)} {shlex.quote(root)}/manifests/history/{revision}.json.gz
rm -f {shlex.quote(remote_bundle)} {shlex.quote(remote_manifest)} {shlex.quote(root+'/shared/.local/'+apply_helper)}
"""
    output=remote.ssh(script)
    if restart:
        remote.ssh("docker restart shiyue-saas shiyue-saas-frontend >/dev/null")
        output += remote.ssh(saas_health_check_command(target["service_port"]))
    return {"contentRevision":revision,"database":output,"media":sync_result,"summary":summary}

def activate_saas_release(job,remote,target,release):
    root=target["remote_root"];release_path=f"{root}/releases/{release}"
    candidate_backend=SAAS_BACKEND_PORT+10000;candidate_frontend=SAAS_FRONTEND_PORT+10000
    candidate=saas_app_run_command(target,release_path,"shiyue-saas-candidate",candidate_backend,False)
    candidate_frontend_command=saas_frontend_run_command(target,release_path,"shiyue-saas-frontend-candidate",candidate_frontend,candidate_backend,False)
    candidate_health=saas_health_check_command(candidate_backend,"shiyue-saas-candidate")
    frontend_health=saas_frontend_health_check_command(candidate_frontend,"shiyue-saas-frontend-candidate",bool(target.get("use_https",0)))
    frontend_scheme="https" if target.get("use_https",0) else "http";frontend_context=",context=ssl._create_unverified_context()" if target.get("use_https",0) else ""
    root_check_code=f"import ssl,urllib.request; r=urllib.request.urlopen(\'{frontend_scheme}://127.0.0.1:{candidate_frontend}/\',timeout=20{frontend_context}); assert r.status==200 and b'id=\"root\"' in r.read(); print(\'SHIYUE_FRONTEND_READY\')"
    job.update(91,"候选端口验收 SaaS 前后台服务")
    script=f"""set -euo pipefail
 docker rm -f shiyue-saas-candidate shiyue-saas-frontend-candidate >/dev/null 2>&1 || true
 {candidate}
 {candidate_frontend_command}
 healthy=0
 for attempt in $(seq 1 60); do
   if {candidate_health} >/tmp/shiyue-saas-candidate-health.json 2>/tmp/shiyue-saas-candidate-error.log && {frontend_health} >/tmp/shiyue-saas-frontend-health.log 2>/tmp/shiyue-saas-frontend-error.log; then healthy=1; break; fi
   sleep 1
 done
 if [ "$healthy" -ne 1 ]; then docker logs --tail 200 shiyue-saas-candidate >&2 || true; docker logs --tail 200 shiyue-saas-frontend-candidate >&2 || true; exit 5; fi
 {saas_migration_check_command("shiyue-saas-candidate")}
 docker exec shiyue-saas-frontend-candidate python3 -c {shlex.quote(root_check_code)}
 cat /tmp/shiyue-saas-candidate-health.json
 docker rm -f shiyue-saas-candidate shiyue-saas-frontend-candidate >/dev/null
 """
    candidate_output=remote.ssh(script)
    job.update(95,"替换旧站并启用 SaaS 前后台")
    production=saas_app_run_command(target,f"{root}/current","shiyue-saas",SAAS_BACKEND_PORT,True)
    production_frontend=saas_frontend_run_command(target,f"{root}/current","shiyue-saas-frontend",SAAS_FRONTEND_PORT,SAAS_BACKEND_PORT,True)
    production_health=saas_health_check_command(SAAS_BACKEND_PORT,"shiyue-saas")
    frontend_production_health=saas_frontend_health_check_command(SAAS_FRONTEND_PORT,"shiyue-saas-frontend",bool(target.get("use_https",0)))
    legacy=docker_run_command(target)
    previous_saas=saas_app_run_command(target,f"{root}/current","shiyue-saas",SAAS_BACKEND_PORT,True)
    previous_frontend=saas_frontend_run_command(target,f"{root}/current","shiyue-saas-frontend",SAAS_FRONTEND_PORT,SAAS_BACKEND_PORT,True)
    switch=f"""set -euo pipefail
 previous_release=$(readlink -f {shlex.quote(root)}/current 2>/dev/null || true)
 docker rm -f shiyue-saas shiyue-saas-frontend shiyue-reader >/dev/null 2>&1 || true
 ln -sfn {shlex.quote(release_path)} {shlex.quote(root)}/current
 {production}
 {production_frontend}
 healthy=0
 for attempt in $(seq 1 60); do
   if {production_health} >/tmp/shiyue-saas-health.json 2>/tmp/shiyue-saas-health-error.log && {frontend_production_health} >/tmp/shiyue-saas-frontend-health.log 2>/tmp/shiyue-saas-frontend-error.log; then healthy=1; break; fi
   sleep 1
 done
 if [ "$healthy" -ne 1 ]; then
   docker logs --tail 200 shiyue-saas >&2 || true; docker logs --tail 200 shiyue-saas-frontend >&2 || true
   docker rm -f shiyue-saas shiyue-saas-frontend >/dev/null 2>&1 || true
   if [ -n "$previous_release" ] && [ -d "$previous_release" ]; then
     ln -sfn "$previous_release" {shlex.quote(root)}/current
     if [ -s "$previous_release/reader/site/index.html" ]; then {previous_saas}; {previous_frontend}; else {legacy}; fi
   fi
   exit 6
 fi
 cat /tmp/shiyue-saas-health.json
 """
    return {"candidate":candidate_output,"production":remote.ssh(switch)}

def run_task(kind,worker,target_id):
    target_id=int(target_id);job=Job(kind,target_id)
    def target():
        if not TASK_LOCK.acquire(blocking=False):job.fail("已有部署或同步任务正在运行");return
        try:
            job.update(1,"读取远程配置");config=get_target(target_id)
            if not config:raise ValueError("请先保存远程服务器配置")
            remote=Remote(config,job);remote.ensure_key();worker(job,remote,config)
        except Exception as exc:job.fail(exc)
        finally:TASK_LOCK.release()
    threading.Thread(target=target,daemon=True).start();return job.id

def start_test(target_id):
    return run_task("connection_test",lambda job,remote,target:(job.update(30,"连接SSH"),remote.ssh("uname -a && id && df -h /"),job.complete({"connected":True,"targetId":target["id"]},"连接正常")),target_id)
def start_deploy(target_id):
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
        if target.get("use_https",1):
            certificate=ensure_remote_tls(job,remote,target);job.write(f"HTTPS根证书：{certificate}")
        job.update(47,"同步远程词典服务配置");dioco=sync_remote_private_config(job,remote,target)
        job.update(50,"激活代码版本并启动运行容器");health=remote.ssh(bootstrap_script(target,release,package.name,digest))
        content=sync_content(job,remote,target,{"scan":58,"prepare":62,"generate":65,"package":68,"upload":72,"apply":80,"database":86,"merge":91})
        job.update(96,"验证远程词典与语境接口");dioco_ready=remote_dioco_check(job,remote,target)
        job.update(97,"最终健康检查");final_health=remote.ssh(health_check_command(target));db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=? AND status='active'",(target["id"],));db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,target["id"],"active",digest,json.dumps({"raw":final_health}),now()));db.commit();db.close();job.complete({"targetId":target["id"],"releaseId":release,"health":final_health,"initialHealth":health,"contentRevision":content["contentRevision"],"media":content["media"],"runtimeArchive":str(runtime),"rootCertificate":str(certificate) if certificate else "","diocoConfigured":dioco["configured"],"diocoReady":dioco_ready},"一键完整部署完成")
    return run_task("code_deploy",worker,target_id)
def start_upgrade(target_id):
    def worker(job,remote,target):
        release=new_release_id("code");job.update(8,"检查远程运行环境",release_id=release)
        output=remote.ssh(f"set -e; docker info >/dev/null; docker image inspect {shlex.quote(RUNTIME_IMAGE)} >/dev/null; test -d {shlex.quote(target['remote_root'])}/shared/.local; echo SHIYUE_UPGRADE_READY")
        if "SHIYUE_UPGRADE_READY" not in output:raise ValueError("远程尚未完成初始化，请先执行一键完整部署")
        job.update(25,"生成程序版本包");package,digest=build_code_package(job,release)
        job.update(42,"上传修改后的程序代码");remote.scp(package,f"/tmp/{package.name}")
        job.update(58,"同步远程词典服务配置");dioco=sync_remote_private_config(job,remote,target)
        job.update(65,"切换程序版本");health=remote.ssh(bootstrap_script(target,release,package.name,digest))
        job.update(88,"验证远程词典与语境接口");dioco_ready=remote_dioco_check(job,remote,target)
        job.update(92,"验证升级结果");final_health=remote.ssh(health_check_command(target))
        db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=? AND status='active'",(target["id"],));db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,target["id"],"active",digest,json.dumps({"raw":final_health}),now()));db.commit();db.close()
        job.complete({"targetId":target["id"],"releaseId":release,"health":final_health,"initialHealth":health,"codeBytes":package.stat().st_size,"diocoConfigured":dioco["configured"],"diocoReady":dioco_ready},"程序升级完成")
    return run_task("program_upgrade",worker,target_id)

def start_saas_upgrade(target_id):
    def worker(job,remote,target):
        release=new_release_id("code");job.update(5,"检查远程 SaaS 生产栈",release_id=release)
        check_remote_saas_upgrade_target(remote,target)
        job.update(15,"生成 SaaS 程序发布包");package,digest=build_code_package(job,release)
        with tarfile.open(package,"r:gz") as archive:build_info=json.load(archive.extractfile(".shiyue-release.json"))
        job.write(f"本地发布来源：commit={build_info.get('gitCommit') or 'unknown'}，工作区未提交改动={bool(build_info.get('sourceDirty'))}")
        job.update(38,"上传并校验 SaaS 程序包");remote.scp(package,f"/tmp/{package.name}")
        prepare_remote_saas_release(remote,target,release,package.name,digest)
        job.update(52,"备份远程 SaaS 数据库");backup=backup_remote_saas_database(job,remote,target,release)
        job.update(60,"同步远程词典服务配置");dioco=sync_remote_private_config(job,remote,target)
        job.update(70,"启动候选版本并执行 SaaS 健康检查")
        activation=activate_saas_release(job,remote,target,release)
        health=remote.ssh(saas_health_check_command(target["service_port"]))
        job.update(95,"核对线上版本指针与运行容器")
        root=shlex.quote(target["remote_root"])
        verification=remote.ssh(f"""set -euo pipefail
current_release=$(readlink -f {root}/current)
test "$(basename "$current_release")" = {shlex.quote(release)}
test "$(docker inspect -f '{{{{.State.Running}}}}' shiyue-saas)" = true
test "$(docker inspect -f '{{{{.State.Running}}}}' shiyue-saas-frontend)" = true
mount_source=$(docker inspect -f '{{{{range .Mounts}}}}{{{{if eq .Destination "/app/reader"}}}}{{{{.Source}}}}{{{{end}}}}{{{{end}}}}' shiyue-saas)
test "$(readlink -f "$mount_source")" = "$current_release/reader"
{saas_frontend_health_check_command(SAAS_FRONTEND_PORT,"shiyue-saas-frontend",bool(target.get("use_https",0)))}
echo SHIYUE_SAAS_RELEASE_ACTIVE
""")
        if "SHIYUE_SAAS_RELEASE_ACTIVE" not in verification:raise ValueError("线上 SaaS 容器与 current 发布版本不一致")
        db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=? AND status='active'",(target["id"],));db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,target["id"],"active",digest,json.dumps({"raw":health,"mode":"saas"}),now()));db.commit();db.close()
        job.complete({"targetId":target["id"],"releaseId":release,"health":health,"backup":backup,"candidate":activation["candidate"],"verification":verification,"buildInfo":build_info,"diocoConfigured":dioco["configured"]},"SaaS 程序升级完成")
    return run_task("saas_upgrade",worker,target_id)

def start_saas_deploy(target_id):
    def worker(job,remote,target):
        release=new_release_id("code");job.update(4,"检查远程 SaaS 运行环境",release_id=release);_,oci_arch=remote_arch(remote)
        ensure_remote_docker(job,remote);ensure_remote_runtime(job,remote,oci_arch)
        job.update(24,"生成根路径 SaaS 程序包");package,digest=build_code_package(job,release);dump,dump_digest=build_saas_database_dump(job,release)
        job.update(38,"上传 SaaS 程序版本");remote.scp(package,f"/tmp/{package.name}")
        ensure_remote_saas_config(job,remote,target);prepare_remote_saas_release(remote,target,release,package.name,digest)
        if target["install_recording"]:
            model=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"
            if not model.exists():raise ValueError("本地缺少 ggml-base.en.bin，无法安装 SaaS 录音转写")
            remote_model=f"{target['remote_root']}/shared/whisper/ggml-base.en.bin";local_hash=hashlib.sha256(model.read_bytes()).hexdigest();remote.ssh(f"mkdir -p {shlex.quote(target['remote_root'])}/shared/whisper")
            output=remote.ssh(f"test -f {shlex.quote(remote_model)} && sha256sum {shlex.quote(remote_model)} | cut -d' ' -f1 || true").strip().splitlines();remote_hash=output[-1] if output else ""
            if remote_hash!=local_hash:job.update(45,"上传 SaaS 录音模型");remote.scp(model,remote_model)
        if target.get("use_https",0):ensure_remote_tls(job,remote,target)
        ensure_remote_saas_services(job,remote,target,release);restored=restore_remote_saas_database(job,remote,target,dump,dump_digest)
        if restored:prune_initial_database_to_published_content(job,remote,target)
        public=sync_saas_public_content(job,remote,target,f"{target['remote_root']}/releases/{release}",{"scan":70,"prepare":73,"package":76,"upload":79,"apply":82,"database":85,"merge":88},False)
        activation=activate_saas_release(job,remote,target,release);final_health=remote.ssh(saas_health_check_command(target["service_port"]))
        db=connect();db.execute("UPDATE deployment_releases SET status='available' WHERE target_id=? AND status='active'",(target["id"],));db.execute("INSERT OR REPLACE INTO deployment_releases(release_id,target_id,status,content_hash,health_json,deployed_at) VALUES(?,?,?,?,?,?)",(release,target["id"],"active",digest,json.dumps({"raw":final_health,"mode":"saas"}),now()));db.commit();db.close()
        job.complete({"targetId":target["id"],"releaseId":release,"health":final_health,"databaseImported":restored,"publicContentRevision":public["contentRevision"],"publicMedia":public["media"],"candidate":activation["candidate"]},"SaaS 根站完整部署完成")
    return run_task("saas_deploy",worker,target_id)
def start_saas_public_sync(target_id):
    def worker(job,remote,target):
        output=remote.ssh(f"set -e; docker inspect shiyue-saas >/dev/null; docker inspect shiyue-saas-frontend >/dev/null; docker inspect shiyue-postgres >/dev/null; docker inspect shiyue-redis >/dev/null; test -s {shlex.quote(target['remote_root'])}/current/reader/site/index.html; echo SHIYUE_SAAS_READY")
        if "SHIYUE_SAAS_READY" not in output:raise ValueError("远程尚未完成 SaaS 根站部署")
        result=sync_saas_public_content(job,remote,target);job.complete(result,"SaaS 公共资源增量同步完成")
    return run_task("saas_public_sync",worker,target_id)
def start_sync(target_id):
    def worker(job,remote,target):
        job.update(3,"检查远程词典服务配置");dioco=sync_remote_private_config(job,remote,target)
        result=sync_content(job,remote,target);job.update(96,"验证远程词典与语境接口");dioco_ready=remote_dioco_check(job,remote,target)
        job.complete({**result,"diocoConfigured":dioco["configured"],"diocoReady":dioco_ready},"点读资源同步完成")
    return run_task("resource_sync",worker,target_id)
def content_rollback_run_command(target,release,operation,restore=False):
    root=target["remote_root"];arguments=["python3","/app/tools/deployment/content_rollback.py","--operation",operation,"--books","/app/books","--manifests","/state/manifests","--backups","/state/backups","--database","/app/.local/library.sqlite3"]
    if restore:arguments.append("--restore")
    else:arguments += ["--target",release]
    options=["docker run --rm --network none",f"-v {shlex.quote(root)}/current/tools:/app/tools:ro",f"-v {shlex.quote(root)}/shared/books:/app/books",f"-v {shlex.quote(root)}/shared/.local:/app/.local",f"-v {shlex.quote(root)}/manifests:/state/manifests",f"-v {shlex.quote(root)}/backups:/state/backups",shlex.quote(RUNTIME_IMAGE),*(shlex.quote(value) for value in arguments)]
    return (" \\"+"\n  ").join(options)
    return " \\\n+  ".join(options)

def start_content_rollback(target_id,release):
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
    return run_task("content_rollback",worker,target_id)

def start_cleanup(target_id,retention_days=30):
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
    return run_task("version_cleanup",worker,target_id)

def start_rollback(target_id,release):
    def worker(job,remote,target):
        if not re.fullmatch(r"code-[A-Za-z0-9-]+",release or ""):raise ValueError("无效的回滚版本")
        root=target["remote_root"];job.update(20,f"检查代码版本 {release}");run=docker_run_command(target);health_command=health_check_command(target)
        script=f"set -e; test -d {shlex.quote(root)}/releases/{shlex.quote(release)}; previous_release=$(readlink -f {shlex.quote(root)}/current 2>/dev/null || true); docker rm -f shiyue-reader >/dev/null 2>&1 || true; ln -sfn {shlex.quote(root)}/releases/{shlex.quote(release)} {shlex.quote(root)}/current; {run}; healthy=0; for attempt in $(seq 1 15); do if {health_command}; then healthy=1; break; fi; sleep 1; done; [ \"$healthy\" -eq 1 ] || {{ docker logs --tail 150 shiyue-reader || true; docker rm -f shiyue-reader; if [ -n \"$previous_release\" ]; then ln -sfn \"$previous_release\" {shlex.quote(root)}/current; {run}; fi; exit 1; }}"
        health=remote.ssh(script);db=connect();db.execute("UPDATE deployment_releases SET status=CASE WHEN release_id=? THEN 'active' ELSE 'available' END WHERE target_id=?",(release,target["id"]));db.commit();db.close();job.complete({"targetId":target["id"],"releaseId":release,"health":health},"代码回滚完成")
    return run_task("code_rollback",worker,target_id)

def start_uninstall(target_id,confirmation):
    target=get_target(target_id)
    if not target:raise ValueError("远程节点不存在")
    if str(confirmation).strip()!=str(target["name"]).strip():raise ValueError("节点名称确认不匹配")
    root=str(target["remote_root"]).strip()
    if root in {"","/","/root","/home","/srv"} or len(Path(root).parts)<3:raise ValueError("远程目录范围过大，拒绝卸载")
    def worker(job,remote,target):
        job.update(20,"停止并删除拾页容器")
        quoted=shlex.quote(root)
        script=f"""set -e
if command -v systemctl >/dev/null 2>&1; then systemctl disable --now shiyue-reader >/dev/null 2>&1 || true; fi
docker rm -f shiyue-saas shiyue-saas-frontend >/dev/null 2>&1 || true
docker rm -f shiyue-reader >/dev/null 2>&1 || true
if [ -d {quoted} ]; then rm -rf -- {quoted}; fi
docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' 2>/dev/null | while read image; do
  case "$image" in
    shiyue-saas:*|shiyue-reader:*|shiyue-reader-runtime:*) docker image rm "$image" >/dev/null 2>&1 || true ;;
  esac
done
test ! -e {quoted}
echo SHIYUE_UNINSTALLED
"""
        output=remote.ssh(script)
        if "SHIYUE_UNINSTALLED" not in output:raise ValueError("远程卸载未完成")
        db=connect();db.execute("UPDATE deployment_releases SET status='uninstalled' WHERE target_id=?",(target["id"],));db.commit();db.close()
        job.complete({"targetId":target["id"],"remoteRoot":root,"dockerPreserved":True},"远程拾页已卸载")
    return run_task("remote_uninstall",worker,target_id)

def job_info(job_id,offset=0):
    db=connect();row=db.execute("SELECT * FROM deployment_jobs WHERE id=?",(job_id,)).fetchone();db.close()
    if not row:return None
    result=dict(row);path=Path(result["log_path"]);text=path.read_text(errors="replace") if path.exists() else "";offset=max(0,min(int(offset),len(text)));result["logChunk"]=text[offset:];result["logOffset"]=len(text)
    try:result["result"]=json.loads(result.pop("result_json"))
    except Exception:result["result"]={}
    return result
def recent_jobs(target_id=None,limit=20):
    db=connect()
    if target_id is None:rows=db.execute("SELECT id,target_id,kind,status,progress,step,error,release_id,created_at,updated_at FROM deployment_jobs WHERE kind NOT IN ('release_list','content_release_list') ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    else:rows=db.execute("SELECT id,target_id,kind,status,progress,step,error,release_id,created_at,updated_at FROM deployment_jobs WHERE target_id=? AND kind NOT IN ('release_list','content_release_list') ORDER BY id DESC LIMIT ?",(int(target_id),limit)).fetchall()
    result=[dict(row) for row in rows];db.close();return result
def dashboard_status(target_id=None):
    db=connect();books=db.execute("SELECT COUNT(*) FROM books WHERE status='ready'").fetchone()[0]
    clause=" AND target_id=?" if target_id is not None else "";params=(int(target_id),) if target_id is not None else ()
    code=db.execute(f"SELECT result_json FROM deployment_jobs WHERE kind IN ('code_deploy','program_upgrade','saas_upgrade','saas_deploy') AND status='complete'{clause} ORDER BY id DESC LIMIT 1",params).fetchone()
    content=db.execute(f"SELECT result_json FROM deployment_jobs WHERE kind IN ('resource_sync','code_deploy','content_rollback') AND status='complete'{clause} ORDER BY id DESC LIMIT 1",params).fetchone();db.close()
    def value(row,key):
        if not row:return ""
        try:return json.loads(row[0]).get(key,"")
        except Exception:return ""
    return {"codeVersion":value(code,"releaseId"),"contentVersion":value(content,"contentRevision"),"localBooks":books,"localRuntime":"约1.3 GiB"}
def remote_releases(target_id):
    target=get_target(target_id)
    if not target:return []
    job=Job("release_list",target["id"])
    try:
        root=shlex.quote(target["remote_root"]);remote=Remote(target,job);output=remote.ssh(f"current=$(basename \"$(readlink -f {root}/current 2>/dev/null || true)\"); find {root}/releases -mindepth 1 -maxdepth 1 -type d -name 'code-*' -printf '%f\\n' 2>/dev/null | sort -r | while read b; do [ \"$b\" = \"$current\" ] && echo \"$b|current\" || echo \"$b|available\"; done");job.complete()
        return [{"releaseId":line.split("|",1)[0],"status":line.split("|",1)[1]} for line in output.splitlines() if line.startswith("code-") and "|" in line]
    except Exception as exc:job.fail(exc);return []
def remote_content_releases(target_id):
    target=get_target(target_id)
    if not target:return []
    job=Job("content_release_list",target["id"])
    try:
        root=shlex.quote(target["remote_root"]);remote=Remote(target,job);output=remote.ssh(f"current=$(sed -n 's/.*\"revision\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p' {root}/manifests/current-content.json 2>/dev/null | head -1); for bundle in {root}/manifests/history/content-*.json.gz; do [ -f \"$bundle\" ] || continue; b=$(basename \"$bundle\" .json.gz); if [ \"$b\" = \"$current\" ]; then echo \"$b|current\"; elif [[ \"$b\" < \"$current\" ]]; then echo \"$b|available\"; fi; done | sort -r");job.complete()
        return [{"releaseId":line.split("|",1)[0],"status":line.split("|",1)[1]} for line in output.splitlines() if line.startswith("content-") and "|" in line]
    except Exception as exc:job.fail(exc);return []
