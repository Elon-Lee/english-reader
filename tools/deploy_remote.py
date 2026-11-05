#!/usr/bin/env python3
"""Build and deploy a release through the configured deployment target."""
import argparse,json,os,sys,time

from deployment import manager


class ConsoleJob:
    def update(self,progress,step,**_):print(f"[{int(progress):3d}%] {step}",flush=True)
    def write(self,message):print(str(message),flush=True)


def resolve_target(value):
    targets=manager.list_targets()
    if str(value).isdigit():
        target=next((item for item in targets if item["id"]==int(value)),None)
    else:
        target=next((item for item in targets if item["name"]==value),None)
    if not target:
        available=", ".join(f"{item['id']}:{item['name']}" for item in targets) or "无"
        raise ValueError(f"找不到部署节点 {value!r}；可用节点：{available}")
    return target


def package_only():
    release=manager.new_release_id("code")
    package,digest=manager.build_code_package(ConsoleJob(),release)
    print(json.dumps({"releaseId":release,"package":str(package),"sha256":digest},ensure_ascii=False,indent=2))


def follow_job(job_id,timeout):
    deadline=time.monotonic()+timeout;offset=0;last_status=""
    while time.monotonic()<deadline:
        job=manager.job_info(job_id,offset)
        if not job:raise RuntimeError(f"部署任务 {job_id} 不存在")
        chunk=job.get("logChunk","")
        if chunk:
            print(chunk,end="" if chunk.endswith("\n") else "\n",flush=True)
            offset=job.get("logOffset",offset+len(chunk))
        if job["status"]!=last_status:
            print(f"任务状态：{job['status']} · {job['progress']}% · {job['step']}",flush=True)
            last_status=job["status"]
        if job["status"]=="complete":
            print(json.dumps(job.get("result",{}),ensure_ascii=False,indent=2))
            return
        if job["status"]=="failed":raise RuntimeError(job.get("error") or "部署失败")
        time.sleep(1)
    raise TimeoutError(f"部署任务 {job_id} 在 {timeout} 秒内未完成")


def main():
    parser=argparse.ArgumentParser(description="构建并部署拾页远程阅读节点")
    parser.add_argument("--package-only",action="store_true",help="只构建发布包，不连接服务器")
    parser.add_argument("--target",help="部署节点 ID 或完整名称")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--full",action="store_true",help="首次完整部署；已配置域名使用标准 80/443，否则兼容 5173 HTTPS")
    mode.add_argument("--upgrade",action="store_true",help="升级已有部署并保留数据、标准 HTTPS 入口（默认）")
    mode.add_argument("--saas",action="store_true",help="完整部署 SaaS、PostgreSQL、Redis 和公共资源；启用已配置的 HTTPS 入口")
    mode.add_argument("--sync-public",action="store_true",help="只增量同步 SaaS 公共书目与媒体")
    mode.add_argument("--https-entry",action="store_true",help="仅安装/更新标准 HTTPS 入口及域名，不发布业务代码或替换数据库")
    parser.add_argument("--domain",help="标准 HTTPS 域名，例如 rynenglish.com（不带协议或路径）")
    parser.add_argument("--host",help="仅入口模式的 SSH 地址，可替代 --target")
    parser.add_argument("--identity-file",help="现有 SSH 私钥文件；使用已验证的默认 known_hosts")
    parser.add_argument("--smtp-config",help="可选的 0600 SMTP 配置文件，安全合并到远端 saas.env")
    parser.add_argument("--ssh-user",default="root",help="仅入口模式的 SSH 用户")
    parser.add_argument("--ssh-port",type=int,default=22,help="仅入口模式的 SSH 端口")
    parser.add_argument("--remote-root",default="/srv/shiyue",help="仅入口模式的现有安装目录")
    parser.add_argument("--acme-email",help="可选的 ACME 账户联系邮箱；留空不注册邮箱")
    parser.add_argument("--timeout",type=int,default=1800,help="最长等待秒数，默认 1800")
    args=parser.parse_args()
    if args.package_only:
        package_only();return
    if args.https_entry:
        if args.host:
            if args.target:parser.error("--host 和 --target 只能指定一个")
            if not args.identity_file:parser.error("--host 模式必须提供 --identity-file")
            if not 1<=args.ssh_port<=65535:parser.error("SSH 端口必须在 1–65535")
            target={"id":0,"host":args.host,"username":args.ssh_user,"port":args.ssh_port,
                    "remote_root":args.remote_root,"identity_file":args.identity_file}
        else:
            if not args.target:parser.error("仅入口模式必须提供 --target 或 --host")
            target=dict(resolve_target(args.target))
            if args.identity_file:target["identity_file"]=args.identity_file
        target["public_domain"]=manager.normalize_domain(args.domain or target.get("public_domain",""))
        if not target["public_domain"]:parser.error("仅入口模式必须提供 --domain 或在节点保存域名")
        if args.acme_email:target["acme_email"]=args.acme_email
        job=ConsoleJob()
        result=manager.configure_existing_https_entry(job,manager.Remote(target,job),target)
        if args.target:
            db=manager.connect()
            db.execute("UPDATE deployment_targets SET public_domain=?,use_https=1,updated_at=? WHERE id=?",
                       (target["public_domain"],manager.now(),target["id"]))
            db.commit();db.close()
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.host or args.domain or args.acme_email:
        parser.error("--host/--domain/--acme-email 仅用于 --https-entry；部署域名请在节点设置保存")
    if args.identity_file:os.environ["SHIYUE_DEPLOY_IDENTITY_FILE"]=args.identity_file
    if args.smtp_config:os.environ["SHIYUE_DEPLOY_SMTP_CONFIG"]=args.smtp_config
    if not args.target:parser.error("部署时必须提供 --target")
    target=resolve_target(args.target)
    action="SaaS 根站完整部署" if args.saas else "公共资源增量同步" if args.sync_public else "完整部署" if args.full else "SaaS 程序升级"
    print(f"目标：{target['id']} · {target['name']} · {target['host']}:{target['port']} · {action}",flush=True)
    if args.saas:job_id=manager.start_saas_deploy(target["id"])
    elif args.sync_public:job_id=manager.start_saas_public_sync(target["id"])
    elif args.full:job_id=manager.start_saas_deploy(target["id"])
    else:job_id=manager.start_saas_upgrade(target["id"])
    print(f"部署任务：{job_id}",flush=True)
    follow_job(job_id,max(30,args.timeout))


if __name__=="__main__":
    try:main()
    except (ValueError,RuntimeError,TimeoutError) as exc:
        print(f"错误：{exc}",file=sys.stderr)
        raise SystemExit(1)
