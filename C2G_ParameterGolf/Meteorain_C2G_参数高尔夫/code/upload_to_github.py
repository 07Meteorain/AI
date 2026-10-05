"""把 C2G 交付物上传到 GitHub 仓库 07Meteorain/AI。

用 GitHub REST API（Contents API）逐文件提交，理由：
  * 目标仓库已存在且有内容（25MB），完整 clone 在本网络代理下会失败
    （fatal: fetch-pack: invalid index-pack output），而小仓库 clone 正常，
    说明是 pack 传输被代理截断，与仓库权限无关。
  * Contents API 只上传增量文件，不触碰仓库已有内容，风险最小。
  * 失败可精确定位到单个文件，便于重试。

认证：复用系统 Git Credential Manager 里已存的 GitHub 凭据
（git-credential-manager get，username=07Meteorain），不落盘、不打印token。

用法：
  python upload_to_github.py --dir <C2G目录> --path C2G_ParameterGolf/Meteorain_C2G_参数高尔夫
  python upload_to_github.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "07Meteorain/AI"
BRANCH = "master"
API = f"https://api.github.com/repos/{REPO}"

# 不上传的内容：实验中间产物、体积大且可复现的文件
SKIP_NAMES = {"final_model.pt", "final_model.int8.ptz"}
SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints"}
SKIP_SUFFIX = {".pyc", ".pt", ".ptz", ".bin", ".npz"}
# 冒烟日志内嵌整份源码（~280KB）且结论无价值，正式实验日志已覆盖同类信息
SKIP_STEMS = ("SMOKE",)


def get_token() -> str:
    """从系统 Git Credential Manager 取已存凭据。不打印、不落盘。"""
    gcm = r"C:\Users\Administrator\.workbuddy\binaries\PortableGit\versions\1.2.0\mingw64\bin\git-credential-manager.exe"
    payload = "protocol=https\nhost=github.com\n\n"
    proc = subprocess.run([gcm, "get"], input=payload, capture_output=True, text=True, timeout=90)
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("未找到 GitHub 凭据。请先执行一次 git push 完成登录。")


def api(method: str, url: str, token: str, body: dict | None = None, retries: int = 3):
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "User-Agent": "python-c2g-upload",
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }
    if data:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            if e.code in (502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def get_sha(token: str, path: str) -> str | None:
    """取远端文件当前 sha（不存在返回 None）。"""
    try:
        r = api("GET", f"{API}/contents/{urllib.parse.quote(path)}?ref={BRANCH}", token)
        return r.get("sha")
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise


def collect_files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_NAMES or p.suffix in SKIP_SUFFIX:
            continue
        if any(p.name.startswith(s) for s in SKIP_STEMS):
            continue
        out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="要上传的本地目录")
    ap.add_argument("--path", required=True, help="远端目标路径（仓库内）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--message", default="C2G: 参数高尔夫 交付物")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print("目录不存在:", root)
        sys.exit(1)

    files = collect_files(root)
    total = sum(p.stat().st_size for p in files)
    print(f"待上传 {len(files)} 个文件，共 {total / 1024:.1f} KiB")
    print(f"目标: {REPO} @ {BRANCH} / {args.path}")
    print("-" * 70)
    for p in files:
        rel = p.relative_to(root).as_posix()
        print(f"  {rel}  ({p.stat().st_size:,} B)")

    if args.dry_run:
        print("\n[dry-run] 未实际上传")
        return

    token = get_token()
    print("\n[auth] 凭据已获取，开始上传…")

    ok = fail = skip = 0
    for p in files:
        rel = p.relative_to(root).as_posix()
        remote_path = f"{args.path.rstrip('/')}/{rel}"
        content = base64.b64encode(p.read_bytes()).decode()
        sha = get_sha(token, remote_path)
        body = {
            "message": f"{args.message}: {rel}",
            "content": content,
            "branch": BRANCH,
        }
        if sha:
            body["sha"] = sha
        try:
            api("PUT", f"{API}/contents/{urllib.parse.quote(remote_path)}", token, body)
            verb = "更新" if sha else "新增"
            print(f"  [OK] {verb} {remote_path}")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {remote_path}: {str(e)[:160]}")
            fail += 1
        time.sleep(0.25)  # 尊重 API 速率限制

    print("-" * 70)
    print(f"完成：成功 {ok}，失败 {fail}，共 {len(files)}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (放在末尾避免影响 --help)
    main()
