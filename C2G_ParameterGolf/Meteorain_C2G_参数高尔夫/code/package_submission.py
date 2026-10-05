"""打包 C2G 提交物。

产出 `submission/Meteorain_C2G_submission.tar.gz`，内含：
  * train_gpt.py（代码字节计入 16MB artifact 预算）
  * submission.json（BPB、训练时间、硬件、seed、全部开关状态）
  * 训练日志（3 个独立 seed）
  * README + requirements

并自动校验 artifact 大小 <= 16,000,000 字节（十进制硬约束）。

用法：
  python package_submission.py --run-id E6_all_combined_seed1337
  python package_submission.py --all# 打包全部已完成实验
"""

from __future__ import annotations

import argparse
import json
import os
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOGS = ROOT / "logs"
RESULTS = ROOT / "results"
SUB = ROOT / "submission"

SIZE_CAP = 16_000_000  # 十进制 16MB，官方明确不是 16MiB

CODE_FILES = ["Meteorain_C2G_train_gpt.py", "run_experiments.py", "package_submission.py"]
DOC_FILES = [
    "README.md",
    "requirements.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/Meteorain_C2G_方案草案.md",
    "docs/Meteorain_C2G_方案设计.md",
    "docs/Meteorain_C2G_ablation.md",
    "docs/Meteorain_C2G_leaderboard.md",
    "docs/Meteorain_C2G_AI日志.md",
    "docs/Meteorain_C2G_拿来说明.md",
    "docs/Meteorain_C2G_AAR复盘.md",
]


def human(n: int) -> str:
    return f"{n:,} ({n / 1e6:.3f} MB)"


def audit_artifact_size(code_bytes: int, model_bytes: int) -> dict:
    """复核 artifact 大小。代码 + 压缩后权重 = 榜单计费口径。"""
    total = code_bytes + model_bytes
    return {
        "bytes_code": code_bytes,
        "bytes_model_int8_zlib": model_bytes,
        "bytes_total": total,
        "cap": SIZE_CAP,
        "ok": total <= SIZE_CAP,
        "headroom": SIZE_CAP - total,
    }


def collect(run_ids: list[str]) -> list[dict]:
    """把各实验的 submission.json 汇总成一个正式提交元数据。"""
    entries = []
    for rid in run_ids:
        p = LOGS / f"{rid}_submission.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                entries.append(json.load(f))
    return entries


def build(run_ids: list[str], out_name: str) -> Path:
    SUB.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    arcname = f"{out_name}_{stamp}"
    tar_path = SUB / f"{arcname}.tar.gz"

    entries = collect(run_ids)

    # 汇总元数据：官方 submission.json 的字段 + 我需要的可追溯信息
    #优先把 E7（实测筛出的有效组合，3 seed）作为主提交
    primary = None
    for e in entries:
        if e.get("name", "").startswith("E7"):
            primary = e
            break
    primary = primary or (entries[-1] if entries else None)

    meta = {
        "author": "07Meteorain",
        "github_id": "07Meteorain",
        "name": out_name,
        "blurb": (
            "Baseline + sliding-window eval + fp16 embedding passthrough + "
            "parallel residuals + QK-gain + tuned LR warmdown. All five changes "
            "are independently ablatable via environment flags."
        ),
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "val_bpb": primary.get("val_bpb") if primary else None,
        "val_loss": primary.get("val_loss") if primary else None,
        "eval_mode": primary.get("eval_mode") if primary else None,
        "seed": primary.get("seed") if primary else None,
        "steps": primary.get("steps") if primary else None,
        "total_train_tokens": primary.get("total_train_tokens") if primary else None,
        "train_time_ms": primary.get("train_time_ms") if primary else None,
        "eval_time_ms": primary.get("eval_time_ms") if primary else None,
        "artifact_bytes_total": primary.get("artifact_bytes_total") if primary else None,
        "artifact_bytes_code": primary.get("artifact_bytes_code") if primary else None,
        "artifact_bytes_model": primary.get("artifact_bytes_model") if primary else None,
        "config": primary.get("config") if primary else None,
        "hardware": primary.get("hardware") if primary else None,
        # ----诚实性标注：官方 schema 不要求，但对评审至关重要 ----
        "measurement_disclosure": {
            "hardware_actual": (primary.get("hardware") or {}).get("gpu_name") if primary else None,
            "is_official_8xh100_config": False,
            "val_set_is_full_official": primary.get("val_set_is_full_official") if primary else None,
            "val_tokens_used": primary.get("val_tokens_used") if primary else None,
            "note": (
                "Measured on a single NVIDIA RTX 3050 (4GB), NOT the challenge's "
                "8xH100 SXM target. Model is 6 layers x 256 dim, 1000 fixed steps, "
                "trained on ~32.8M tokens (official baseline: 9x512, 13,780 steps, ~7.2B "
                "tokens). Validation used a fixed PREFIX of the official frozen "
                "FineWeb val split (no selection bias) to bound local eval time. "
                "These numbers characterise the RELATIVE effect of each change and "
                "are NOT comparable to the official 8xH100 leaderboard."
            ),
        },
        "all_runs": entries,
    }

    # 大小复核
    code_bytes = sum(
        (HERE / f).stat().st_size for f in CODE_FILES if (HERE / f).exists()
    )
    model_bytes = (primary or {}).get("artifact_bytes_model") or 0
    meta["artifact_audit"] = audit_artifact_size(code_bytes, model_bytes)

    with tarfile.open(tar_path, "w:gz") as tar:
        for f in CODE_FILES:
            p = HERE / f
            if p.exists():
                tar.add(p, arcname=f"{arcname}/{f}")
        for f in DOC_FILES:
            p = ROOT / f
            if p.exists():
                tar.add(p, arcname=f"{arcname}/{f}")
        # 日志与结果
        for rid in run_ids:
            for ext in (".txt", "_submission.json"):
                p = LOGS / f"{rid}{ext}"
                if p.exists():
                    tar.add(p, arcname=f"{arcname}/logs/{rid}{ext}")
        for jf in RESULTS.glob("results_*.json"):
            tar.add(jf, arcname=f"{arcname}/results/{jf.name}")
        # 汇总元数据
        mp = SUB / f"{arcname}_submission.json"
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        tar.add(mp, arcname=f"{arcname}/submission.json")

    print(f"packaged -> {tar_path}")
    print(f"  tarball size      : {human(tar_path.stat().st_size)}")
    print(f"  code bytes        : {human(code_bytes)}")
    print(f"  model int8+zlib   : {human(model_bytes)}")
    print(f"  artifact total    : {human(code_bytes + model_bytes)}")
    verdict = "OK" if meta["artifact_audit"]["ok"] else "VIOLATION"
    print(f"  16MB cap ({SIZE_CAP:,}) -> {verdict}")
    return tar_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", type=str, default=None, help="要打包的 run_id")
    ap.add_argument("--all", action="store_true", help="打包全部已完成实验")
    ap.add_argument("--name", type=str, default="Meteorain_C2G_submission")
    args = ap.parse_args()

    if args.all:
        run_ids = sorted(
            p.name[: -len("_submission.json")]
            for p in LOGS.glob("E*_submission.json")
        )
    elif args.run_id:
        run_ids = [args.run_id]
    else:
        cands = sorted(p.stem.replace("_submission.json", "") for p in LOGS.glob("E*_submission.json"))
        if not cands:
            print("no completed runs found in", LOGS)
            return
        run_ids = [cands[-1]]
        print("using latest run:", run_ids[0])

    if not run_ids:
        print("nothing to package")
        return
    build(run_ids, args.name)


if __name__ == "__main__":
    main()