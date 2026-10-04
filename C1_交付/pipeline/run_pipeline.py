"""
run_pipeline.py — 一键跑通全流程。

    python run_pipeline.py                 # 抽取 → 翻译 → 质检 → 构建
    python run_pipeline.py --from qc       # 只从质检开始
    python run_pipeline.py --provider llm  # 用 API 补齐缺失译文
    python run_pipeline.py --strict        # 质检不达标时以非零码退出（适合 CI）

这就是「换一门课也能复跑」的入口：改 config.json 的 sources，其余什么都不用动。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from common import c, load_config, PIPELINE_DIR, ROOT

STAGES = [
    ("extract",  "01_extract.py",   "抽取正文（HTML/PDF → Segment）"),
    ("translate", "02_translate.py", "翻译（缓存优先，缺失时按 provider 补齐）"),
    ("qc",       "03_qc.py",        "质量抽检（覆盖率 / 术语 / 漏译 / 格式）"),
    ("build",    "04_build.py",     "构建 Markdown 资料包与静态文档站"),
]


def run(script: str, extra: list[str]) -> int:
    py = sys.executable
    r = subprocess.run([py, str(PIPELINE_DIR / script)] + extra,
                       cwd=str(PIPELINE_DIR))
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="extract",
                    choices=[s[0] for s in STAGES])
    ap.add_argument("--only", choices=[s[0] for s in STAGES])
    ap.add_argument("--provider", choices=["cache", "llm", "echo"])
    ap.add_argument("--strict", action="store_true", help="质检未达标则退出码非零")
    args = ap.parse_args()

    cfg = load_config()
    print(c(f"\n▶ {cfg['project']['name']}", "bold"))
    print(c(f"  源目录: {cfg['project']['source_root']}", "dim"))
    print(c(f"  术语表: {cfg['project']['glossary']} ({len(cfg['sources'])} 篇资料)\n", "dim"))

    t0 = time.time()
    for i, (name, script, desc) in enumerate(STAGES):
        if args.only and name != args.only:
            continue
        if not args.only and STAGES.index((name, script, desc)) < [s[0] for s in STAGES].index(args.start):
            continue
        print(c(f"\n━━ [{i+1}/{len(STAGES)}] {name} — {desc}", "blue"))
        extra = ["--provider", args.provider] if (args.provider and name == "translate") else []
        rc = run(script, extra)
        if rc != 0 and name in ("extract", "translate"):
            print(c(f"\n✗ {name} 阶段失败，流水线中止", "red"))
            return rc

    dt = time.time() - t0
    print(c(f"\n✔ 全流程完成，用时 {dt:.1f}s", "green"))
    print(c(f"  报告:{ROOT / 'reports'}", "dim"))
    print(c(f"  资料: {ROOT / 'translations'}", "dim"))
    print(c(f"  站点: {ROOT / 'docs' / 'index.html'}", "dim"))

    if args.strict:
        import json
        qc = ROOT / "reports" / "02_qc.json"
        if qc.exists():
            v = json.loads(qc.read_text(encoding="utf-8"))["verdicts"]
            failed = [x for x in v if not x["pass"]]
            if failed:
                print(c(f"\n✗ 质检未通过 {len(failed)} 项：", "red"))
                for x in failed:
                    print(f"    - {x['check']}: {x['value']}（阈值 {x['threshold']}）")
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
