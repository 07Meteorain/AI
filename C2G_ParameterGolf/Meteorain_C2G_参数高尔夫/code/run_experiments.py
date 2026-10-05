"""C2G 消融实验驱动脚本。

用途：按实验矩阵逐个跑配置，收集 val_bpb / artifact bytes / 量化前后差值，
输出结构化结果供 ablation 报告使用。

设计原则（对应方案草案第 3 节）：
  * 等算力：所有配置跑相同步数，差值才能归因到单一变量
  * 三指标必备：val_bpb / artifact_bytes / quant_gap（量化前后差值）
  * 逐个串行：单卡显存有限，且串行能避免GPU 争抢影响计时

用法：
  python run_experiments.py --smoke          # 快速冒烟，验证管线能跑通
  python run_experiments.py --ablation       # 完整消融矩阵
  python run_experiments.py --seeds          # 最佳配置的 3 seed 稳定性验证
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAIN_SCRIPT = HERE / "Meteorain_C2G_train_gpt.py"

DATA_PATH = os.environ.get("C2G_DATA_PATH", r"C:\pg\data\datasets\fineweb10B_sp1024")
TOKENIZER_PATH = os.environ.get("C2G_TOKENIZER_PATH", r"C:\pg\data\tokenizers\fineweb_1024_bpe.model")
RESULTS_DIR = HERE.parent / "results"
LOGS_DIR = HERE.parent / "logs"

# 本机是单张 RTX 3050 (4GB)，不是赛事的 8xH100。
# 因此用「固定步数」而非「固定 wallclock」做对照，保证各配置算力严格相等。
# 这个规模足够验证各改动的相对贡献，但绝对 BPB 不等于 8xH100 口径。
LOCAL_PROFILE = {
    "NUM_LAYERS": "6",
    "MODEL_DIM": "256",
    "NUM_HEADS": "8",
    "NUM_KV_HEADS": "4",
    "MLP_MULT": "2",
    "TRAIN_SEQ_LEN": "512",
    "TRAIN_BATCH_TOKENS": "32768",
    "ITERATIONS": "1000",
    "WARMUP_STEPS": "5",
    "VAL_BATCH_SIZE": "65536",
    "MAX_WALLCLOCK_SECONDS": "0",  # 用步数控制，不靠时间截断
    "EVAL_BATCH_SEQS": "32",
    "EVAL_STRIDE": "64",
    # 官方验证集共 62,021,632 tokens。本地单卡 eager 跑全量滑窗评估约需 20+ 分钟，
    # 超出合理实验预算。取验证集**前缀** 1,000,000 tokens（无选择偏差，
    # 因为官方验证集本身就是冻结的前 50k 文档），并在报告中明确标注。
    # 官方 8xH100 口径提交时必须设 MAX_VAL_TOKENS=0（用全集）。
    "MAX_VAL_TOKENS": "1000000",
    "TRAIN_LOG_EVERY": "250",
    # Windows 本地环境无 Triton，inductor 编译不可用；走 eager。
    # 所有实验用固定步数做等算力对照，因此 eager 慢不影响结论有效性。
    "USE_COMPILE": "0",
}

# 消融矩阵：每个配置只改一个开关，基线配置完全复刻官方 naive baseline 的开关状态
ABLATION_MATRIX = [
    {
        "id": "E0_baseline",
        "desc": "官方 baseline 原样：chunked 评估 + int8 嵌入 + 串行残差 + 默认 LR",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "1.5",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E1_sliding_eval",
        "desc": "仅开启滑窗评估（E0 + A）",
        "env": {
            "SLIDING_WINDOW_EVAL": "1",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "1.5",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E2_fp16_embed",
        "desc": "仅开启 fp16 嵌入直传（E0 + B）",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "1",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "1.5",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E3_parallel_residual",
        "desc": "仅开启并行残差（E0 + C）",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "1",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "1.5",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E7_best_validated",
        "desc": "实测筛出的有效组合 A+B+E（滑窗 + fp16嵌入 + LR调优；剔除实测有害的 D 与 no-op 的 C）",
        "env": {
            "SLIDING_WINDOW_EVAL": "1",
            "FP16_EMBED_PASSTHROUGH": "1",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "1",
            "QK_GAIN_INIT": "1.5",
        },
    },
    {
        "id": "E3b_parallel_residual_fix",
        "desc": "并行残差修正版：起始层 3（本地仅 6 层，原start=7 会导致 0 层启用，等于没开）",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "1",
            "PARALLEL_RESIDUAL_START": "3",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "1.5",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E4_qk_gain",
        "desc": "仅调 QK-gain至 5.25（E0 + D）",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "0",
            "QK_GAIN_INIT": "5.25",
            "WARMDOWN_ITERS": "1200",
            "MATRIX_LR": "0.04",
        },
    },
    {
        "id": "E5_tuned_lr",
        "desc": "仅开启 LR/warmdown 调优（E0 + E）",
        "env": {
            "SLIDING_WINDOW_EVAL": "0",
            "FP16_EMBED_PASSTHROUGH": "0",
            "PARALLEL_RESIDUAL": "0",
            "TUNED_LR": "1",
            "QK_GAIN_INIT": "1.5",
        },
    },
    {
        "id": "E6_all_combined",
        "desc": "全部改动组合（A+B+C+D+E）",
        "env": {
            "SLIDING_WINDOW_EVAL": "1",
            "FP16_EMBED_PASSTHROUGH": "1",
            "PARALLEL_RESIDUAL": "1",
            "TUNED_LR": "1",
            "QK_GAIN_INIT": "5.25",
        },
    },
]

SEEDS = [1337, 42, 314]


def build_env(exp: dict, seed: int, run_id: str) -> dict:
    env = dict(os.environ)
    env.update(
        {
            "DATA_PATH": DATA_PATH,
            "TOKENIZER_PATH": TOKENIZER_PATH,
            "SEED": str(seed),
            "RUN_ID": run_id,
            "OUT_DIR": str(LOGS_DIR),
            "PYTHONUNBUFFERED": "1",
        }
    )
    env.update({k: str(v) for k, v in LOCAL_PROFILE.items()})
    env.update({k: str(v) for k, v in exp["env"].items()})
    return env


def run_one(exp: dict, seed: int, timeout_s: int = 5400) -> dict:
    run_id = f"{exp['id']}_seed{seed}"
    env = build_env(exp, seed, run_id)
    print(f"\n{'=' * 78}\n>>> RUN {run_id}\n>>> {exp['desc']}\n{'=' * 78}", flush=True)

    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(TRAIN_SCRIPT)],
        env=env,
        cwd=str(HERE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    elapsed = time.perf_counter() - t0
    print(f"    exit={proc.returncode} elapsed={elapsed:.1f}s", flush=True)
    if proc.returncode != 0:
        print("--- STDOUT tail ---")
        print("\n".join(proc.stdout.splitlines()[-25:]))
        print("--- STDERR tail ---")
        print("\n".join(proc.stderr.splitlines()[-25:]))
        return {"id": exp["id"], "seed": seed, "status": "failed", "returncode": proc.returncode}

    sub_path = LOGS_DIR / f"{run_id}_submission.json"
    if not sub_path.exists():
        print(f"    !! missing submission json: {sub_path}")
        return {"id": exp["id"], "seed": seed, "status": "no_submission"}

    with open(sub_path, encoding="utf-8") as f:
        sub = json.load(f)

    # 从日志里补捞 chunked 参考分与量化前后差值
    log_path = LOGS_DIR / f"{run_id}.txt"
    quant_gap = None
    chunked_bpb = None
    sliding_gain = None
    pre_quant_bpb = None
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "val_bpb:" in line and "final_int8" not in line and "reference_chunked" not in line:
                m = re.search(r"val_bpb:([0-9.]+)", line)
                if m:
                    pre_quant_bpb = float(m.group(1))
            m = re.search(r"reference_chunked_eval.*?val_bpb:([0-9.]+)", line)
            if m:
                chunked_bpb = float(m.group(1))
            m = re.search(r"sliding_gain_bpb:([0-9.]+)", line)
            if m:
                sliding_gain = float(m.group(1))
        if chunked_bpb is not None:
            quant_gap = chunked_bpb - sub["val_bpb"]

    record = {
        "id": exp["id"],
        "desc": exp["desc"],
        "seed": seed,
        "status": "ok",
        "val_bpb": sub["val_bpb"],
        "val_loss": sub["val_loss"],
        "eval_mode": sub.get("eval_mode"),
        "chunked_bpb": chunked_bpb,
        "sliding_gain_bpb": sliding_gain,
        "pre_quant_bpb": pre_quant_bpb,
        "quant_gap_bpb": quant_gap,
        "artifact_bytes_total": sub.get("artifact_bytes_total"),
        "artifact_bytes_code": sub.get("artifact_bytes_code"),
        "artifact_bytes_model": sub.get("artifact_bytes_model"),
        "steps": sub.get("steps"),
        "total_train_tokens": sub.get("total_train_tokens"),
        "gpu": sub.get("hardware", {}).get("gpu_name"),
        "elapsed_s": round(elapsed, 1),
        "env_overrides": exp["env"],
    }
    print(
        f"    val_bpb={record['val_bpb']:.4f} mode={record['eval_mode']} "
        f"artifact={record['artifact_bytes_total']} quant_gap={quant_gap}",
        flush=True,
    )
    return record


def save_results(records: list[dict], tag: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"results_{tag}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "tag": tag,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "local_profile": LOCAL_PROFILE,
                "hardware_note": (
                    "Single NVIDIA RTX 3050 (4GB). NOT the challenge's 8xH100 SXM target."
                    "Fixed-step equal-compute ablation; absolute BPB is not comparable to "
                    "the official 8xH100 leaderboard numbers."
                ),
                "records": records,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n>>> saved {out}", flush=True)


def print_table(records: list[dict]) -> None:
    ok = [r for r in records if r.get("status") == "ok"]
    if not ok:
        print("no successful runs")
        return
    base = next((r for r in ok if r["id"] == "E0_baseline"), None)
    print("\n" + "=" * 100)
    print(f"{'experiment':<24}{'seed':>6}{'val_bpb':>10}{'delta':>9}{'artifact':>12}{'quant_gap':>11}")
    print("-" * 100)
    for r in ok:
        delta = f"{r['val_bpb'] - base['val_bpb']:+.4f}" if base else "n/a"
        qg = f"{r['quant_gap_bpb']:.4f}" if r.get("quant_gap_bpb") is not None else "n/a"
        print(
            f"{r['id']:<24}{r['seed']:>6}{r['val_bpb']:>10.4f}{delta:>9}"
            f"{r['artifact_bytes_total'] or 0:>12,}{qg:>11}"
        )
    print("=" * 100)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="极短跑，验证管线")
    ap.add_argument("--ablation", action="store_true", help="完整消融矩阵")
    ap.add_argument("--seeds", action="store_true", help="最佳配置 3 seed")
    ap.add_argument("--only", type=str, default=None, help="只跑某个 experiment id")
    args = ap.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.smoke:
        profile = dict(LOCAL_PROFILE)
        profile.update({"ITERATIONS": "30", "TRAIN_LOG_EVERY": "10"})
        globals()["LOCAL_PROFILE"] = profile
        rec = run_one(
            {"id": "SMOKE", "desc": "管线冒烟测试", "env": {"SLIDING_WINDOW_EVAL": "1", "EVAL_STRIDE": "128"}},
            seed=1337,
        )
        save_results([rec], "smoke")
        return

    if args.ablation or args.only:
        matrix = ABLATION_MATRIX
        if args.only:
            matrix = [e for e in ABLATION_MATRIX if e["id"] == args.only]
            if not matrix:
                print(f"unknown experiment id: {args.only}")
                print("available:", [e["id"] for e in ABLATION_MATRIX])
                sys.exit(1)
        records = []
        for exp in matrix:
            records.append(run_one(exp, seed=1337))
            save_results(records, "ablation")
        print_table(records)
        return

    if args.seeds:
        best = next(
            (e for e in ABLATION_MATRIX if e["id"] == "E7_best_validated"),
            ABLATION_MATRIX[0],
        )
        records = []
        for seed in SEEDS:
            records.append(run_one(best, seed=seed))
            save_results(records, "seeds")
        print_table(records)
        vals = [r["val_bpb"] for r in records if r.get("status") == "ok"]
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
            print(f"\nmean={mean:.6f} std={var ** 0.5:.6f} n={len(vals)}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()