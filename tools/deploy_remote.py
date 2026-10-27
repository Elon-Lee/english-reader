#!/usr/bin/env python3
"""Build and deploy a release through the configured deployment target."""
import argparse,json,sys,time

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
    mode.add_argument("--full",action="store_true",help="执行首次完整部署，启用 5173 HTTPS")
    mode.add_argument("--upgrade",action="store_true",help="升级已有部署并启用 5173 HTTPS（默认，保留远端数据）")
    mode.add_argument("--saas",action="store_true",help="完整部署根路径 SaaS、PostgreSQL、Redis 和公共资源，启用 5173 HTTPS")
    mode.add_argument("--sync-public",action="store_true",help="只增量同步 SaaS 公共书目与媒体")
    parser.add_argument("--timeout",type=int,default=1800,help="最长等待秒数，默认 1800")
    args=parser.parse_args()
    if args.package_only:
        package_only();return
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
