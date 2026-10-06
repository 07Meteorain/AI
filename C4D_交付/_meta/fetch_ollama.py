"""下载 Ollama Windows 安装包（绕过 curl 的 TLS/代理问题，使用 urllib）。"""
import hashlib
import os
import sys
import time
import urllib.request

DEST = sys.argv[1] if len(sys.argv) > 1 else "OllamaSetup.exe"
URL = "https://ollama.com/download/OllamaSetup.exe"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        print(f"HTTP {resp.status}  size={human(total)}", flush=True)

        tmp = DEST + ".part"
        digest = hashlib.sha256()
        done = 0
        t0 = time.time()
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                pct = (done / total * 100) if total else 0
                rate = done / max(time.time() - t0, 1e-6) / 1024 / 1024
                sys.stdout.write(
                    f"\r  {human(done)}/{human(total)}  {pct:5.1f}%  "
                    f"{rate:5.2f} MB/s"
                )
                sys.stdout.flush()
        print()

    os.replace(tmp, DEST)
    print(f"saved: {DEST}")
    print(f"size:  {human(os.path.getsize(DEST))}")
    print(f"sha256: {digest.hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())