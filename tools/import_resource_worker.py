"""Join the delegated memory budget BEFORE importing document/model libraries."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--official', action='store_true')
    args = parser.parse_args()
    # All fork/exec descendants inherit this membership. The parent API remains
    # outside the budget so it can persist an OOM failure and continue serving.
    root = Path(os.environ['SHIYUE_IMPORT_CGROUP'])
    with (root / 'cgroup.procs').open('w') as membership:
        membership.write(str(os.getpid()))
    from saas_auth import SaaSService
    from saas_resources import ResourceService
    from saas_media import MediaService
    from saas_imports import WorkspaceImportService
    accounts = SaaSService.from_env()
    resources = ResourceService(accounts)
    service = WorkspaceImportService(accounts, resources, MediaService(accounts, resources), official=args.official)
    service._isolated_worker = True
    service.complete(args.user, args.task)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # The regular service persists business failures; the outside supervisor
        # handles startup failures and OOM. Never print credentials or book text.
        raise SystemExit(1)
