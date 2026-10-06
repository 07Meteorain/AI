"""测试大文件下载：单连接 vs 多连接分段，判定瓶颈是带宽还是单连接限速。

用于在受限网络环境下选择最优下载策略。
"""
import concurrent.futures as cf
import sys
import time
import urllib.request

URL = "https://ollama.com/download/OllamaSetup.exe"
UA = {"User-Agent": "Mozilla/5.0"}


def resolve() -> str:
    req = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.url


def grab(url: str, start: int, end: int) -> int:
    """下载 [start, end] 区间，返回实际收到的字节数。"""
    req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r:
        while True:
            b = r.read(1 << 18)
            if not b:
                break
            got += len(b)
    return got


def main() -> None:
    url = resolve()
    print("resolved host:", url.split("/")[2])

    # 1) 单连接基准
    t0 = time.time()
    one = grab(url, 0, 8 << 20)  # 8MB
    t1 = time.time() - t0
    print(f"single : {one/1e6:.1f}MB in {t1:.1f}s = {one/t1/1e6:.2f} MB/s")

    # 2) 多连接并行
    for n in (8, 16):
        chunk = 8 << 20
        spans = [(i * chunk, i * chunk + chunk - 1) for i in range(n)]
        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=n) as ex:
            total = sum(ex.map(lambda s: grab(url, s[0], s[1]), spans))
        dt = time.time() - t0
        print(f"par-{n:<2}: {total/1e6:.1f}MB in {dt:.1f}s = {total/dt/1e6:.2f} MB/s")


if __name__ == "__main__":
    main()