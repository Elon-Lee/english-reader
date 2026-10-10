#!/usr/bin/env python3
"""Stop only the formal local SaaS web and debug SMTP listeners."""
from __future__ import annotations

import os
import signal
import subprocess
import time


def main()->int:
    stopped=[]
    for port in (8790,1025):
        result=subprocess.run(["lsof","-ti",f"TCP:{port}","-sTCP:LISTEN"],text=True,capture_output=True)
        for value in result.stdout.split():
            try:pid=int(value)
            except ValueError:continue
            try:os.kill(pid,signal.SIGTERM);stopped.append({"pid":pid,"port":port})
            except ProcessLookupError:pass
    time.sleep(.5);print({"stopped":stopped});return 0


if __name__=="__main__":raise SystemExit(main())
