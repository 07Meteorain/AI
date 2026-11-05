# -*- coding: utf-8 -*-
"""跨语言探针：用 Python 复跑同一张探针表（Windows / macOS / Linux 通用）。

用法：python probe.py
期望（正常机器）：所有行的 status 为 0，末行打印「全部通过」。
受限环境：status 变成 3221225794（0xC0000142）或 OSError/EPERM。
"""
import shutil
import subprocess
import sys

PROBES = [
    (["cmd.exe", "/c", "echo hi"] if sys.platform == "win32" else ["sh", "-c", "echo hi"], "pipe"),
    (["git", "--version"], "pipe"),
    (["git", "--version"], "devnull"),
]


def main():
    fail = 0
    for cmd, mode in PROBES:
        if shutil.which(cmd[0]) is None:
            print("%-30s 未安装，跳过" % cmd[0])
            continue
        try:
            if mode == "pipe":
                r = subprocess.run(cmd, capture_output=True, timeout=20)
                status = r.returncode
            else:
                r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                status = r.returncode
            err = "-"
        except OSError as exc:
            status, err = "OSError", type(exc).__name__
        except subprocess.TimeoutExpired:
            status, err = "timeout", "-"
        if status != 0:
            fail += 1
        hexv = ("0x%X" % (status & 0xFFFFFFFF)) if isinstance(status, int) and status else "-"
        print("%-22s stdio=%-8s status=%-12s %-10s err=%s" % (cmd[0], mode, status, hexv, err))
    print()
    print("全部通过：进程创建正常" if fail == 0 else "%d 项失败：进程创建被环境拦截" % fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())