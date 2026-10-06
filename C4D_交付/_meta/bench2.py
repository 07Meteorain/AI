"""快速判定：单连接限速 vs 总带宽限速。

用小分片（2MB）+ 有限并发，短时间得出结论。
"""
import concurrent.futures as cf
import time
import urllib.request

URL = "https://ollama.com/download/OllamaSetup.exe"
UA = {"User-Agent": "Mozilla/5.0"}
CHUNK = 2 << 20  # 2MB


def resolve() -> str:
    req = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.url


def grab(url: str, start: int, end: int) -> int:
    req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
    got = 0
    with urllib.request.urlopen(req, timeout=30) as r:
        while True:
            b = r.read(1 << 17)
            if not b:
                break
            got += len(b)
    return got


def trial(url: str, n: int) -> tuple[float, float]:
    spans = [(i * CHUNK, i * CHUNK + CHUNK - 1) for i in range(n)]
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        total = sum(ex.map(lambda s: grab(url, s[0], s[1]), spans))
    dt = time.time() - t0
    return total / 1e6, total / dt / 1e6


def main() -> None:
    url = resolve()
    print("host:", url.split("/")[2], flush=True)
    mb, spd = trial(url, 1)
    print(f"n=1  : {mb:6.1f}MB  {spd:6.3f} MB/s", flush=True)
    for n in (8, 24):
        mb, spd = trial(url, n)
        print(f"n={n:<2}: {mb:6.1f}MB  {spd:6.3f} MB/s", flush=True)


if __name__ == "__main__":
    main()