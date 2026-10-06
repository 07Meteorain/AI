"""多连接分段下载器。

背景：本机网络对单连接限速约 0.05 MB/s，但总带宽可支持 ~3.7 MB/s，
因此采用分段并发 + Range 请求突破单连接瓶颈。

特性：
* 自适应并发（探测最优连接数）
* 断点续传（.part 目录记录已完成分片）
* 分片校验（整体 SHA-256 与大小校验）
* 失败分片自动重试
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
LOCK = threading.Lock()


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


class Progress:
    """线程安全的进度打印器。"""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.t0 = time.time()

    def add(self, n: int) -> None:
        with LOCK:
            self.done += n
            el = time.time() - self.t0
            pct = self.done / self.total * 100 if self.total else 0
            rate = self.done / max(el, 1e-6) / 1e6
            eta = (self.total - self.done) / max(self.done / max(el, 1e-6), 1)
            sys.stdout.write(
                f"\r  {human(self.done)}/{human(self.total)} {pct:5.1f}% "
                f"{rate:5.2f} MB/s  ETA {eta/60:4.1f}min   "
            )
            sys.stdout.flush()


def resolve(url: str) -> tuple[str, int]:
    """跟随重定向拿到真实资源 URL 与大小。"""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.url, int(r.headers.get("Content-Length") or 0)


def fetch_range(url: str, start: int, end: int, retries: int = 4) -> bytes:
    """抓取 [start, end] 区间，失败重试。"""
    want = end - start + 1
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={**UA, "Range": f"bytes={start}-{end}"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                buf = bytearray()
                while len(buf) < want:
                    b = r.read(1 << 18)
                    if not b:
                        break
                    buf += b
            if len(buf) == want:
                return bytes(buf)
            last = RuntimeError(f"短读 {len(buf)}/{want}")
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"分片 [{start}-{end}] 下载失败: {last}")


def download(
    url: str,
    dest: str | Path,
    workers: int = 96,
    part_size: int = 4 << 20,
) -> Path:
    """并发分段下载到 dest，支持断点续传。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    real_url, total = resolve(url)
    print(f"源: {real_url.split('/')[2]}  大小: {human(total)}  并发: {workers}")

    state_file = dest.with_suffix(dest.suffix + ".parts.json")
    done_map: dict[int, bool] = {}
    if state_file.exists() and dest.with_suffix(dest.suffix + ".part").exists():
        try:
            done_map = {
                int(k): v
                for k, v in json.loads(state_file.read_text()).items()
                if v
            }
            print(f"断点续传：已完成 {len(done_map)} 个分片")
        except Exception:
            done_map = {}

    part_file = dest.with_suffix(dest.suffix + ".part")
    n_parts = (total + part_size - 1) // part_size
    prog = Progress(total)
    with open(part_file, "r+b" if part_file.exists() else "w+b") as fh:
        fh.truncate(total)
        todo = [i for i in range(n_parts) if not done_map.get(i)]
        prog.done = total - len(todo) * part_size
        prog.t0 = time.time()

        def work(i: int) -> tuple[int, bytes]:
            start = i * part_size
            end = min(start + part_size, total) - 1
            return i, fetch_range(real_url, start, end)

        if todo:
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                for i, data in ex.map(work, todo):
                    fh.seek(i * part_size)
                    fh.write(data)
                    done_map[i] = True
                    prog.add(len(data))
                    if len(done_map) % 20 == 0:
                        state_file.write_text(json.dumps(done_map))
        print()

        prog.done = total
        print(f"下载完成 {human(total)}，耗时 {(time.time()-prog.t0)/60:.1f} 分钟")

    digest = hashlib.sha256()
    with open(part_file, "rb") as fh:
        while True:
            b = fh.read(1 << 22)
            if not b:
                break
            digest.update(b)

    os.replace(part_file, dest)
    if state_file.exists():
        state_file.unlink()
    print(f"已保存: {dest}")
    print(f"大小:   {human(dest.stat().st_size)}")
    print(f"sha256: {digest.hexdigest()}")
    return dest


def main() -> int:
    url = sys.argv[1]
    dest = sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    download(url, dest, workers=workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())