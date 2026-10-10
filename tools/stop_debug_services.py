#!/usr/bin/env python3
"""Stop only known disposable reader smoke/debug ports; preserve port 8790."""
from __future__ import annotations

import os
import signal
import subprocess
import time


PORTS=(8765,8766,8775,8776,8785,8786,8792,8795)


def main()->int:
    stopped=[]
    for port in PORTS:
        result=subprocess.run(["lsof","-ti",f"TCP:{port}","-sTCP:LISTEN"],text=True,capture_output=True)
        for value in result.stdout.split():
            try:pid=int(value)
            except ValueError:continue
            try:os.kill(pid,signal.SIGTERM);stopped.append({"pid":pid,"port":port})
            except ProcessLookupError:pass
    time.sleep(.5);print({"stopped":stopped,"preservedPort":8790});return 0


if __name__=="__main__":raise SystemExit(main())
