#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV/JSON → app/js/core/data.js（浏览器与 Node 共用的数据包）。

为什么要有这一步：app 要能双击 index.html 就跑，不能 fetch 本地 CSV（file:// 下会被
CORS 拦掉）。所以把数据编译成一个 JS 文件。代价是"数据可能忘了重新编译"，所以：
  * 本脚本带 --check，CI 里比对内容哈希；
  * tests/data.test.js 会重新读 CSV 算一遍，和 data.js 里的值对账。

用法：
    python tools/gen_data_js.py
    python tools/gen_data_js.py --check
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HEADER = """// 本文件由 tools/gen_data_js.py 生成，请勿手改。
// 源数据：数据/title_rubric.json、数据/titles_scored.csv、数据/projection_params.csv、数据/repo_facts.csv
// 改了任何一个 CSV/JSON 都要重跑：python tools/gen_data_js.py
"""

NUMERIC_TEST_FIELDS = ("files", "kb", "commits", "tests_computed", "tests_py", "tests_js", "declared_tests")
NUMERIC_TITLE_FIELDS = ("chars", "hook", "specificity", "searchability", "platformFit", "credibility", "total")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_num(value: str):
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except ValueError:
        return value
    return int(f) if f.is_integer() else f


def build(root: Path) -> dict:
    rubric = json.loads((root / "数据" / "title_rubric.json").read_text(encoding="utf-8"))
    titles = []
    for row in read_csv(root / "数据" / "titles_scored.csv"):
        item = {k: v for k, v in row.items() if k != "reasons"}
        for k in NUMERIC_TITLE_FIELDS:
            if k in item:
                item[k] = to_num(item[k])
        titles.append(item)

    params_raw = read_csv(root / "数据" / "projection_params.csv")
    channels = [h for h in (params_raw[0].keys() if params_raw else []) if h not in ("metric", "note")]
    params = {ch: {} for ch in channels}
    for row in params_raw:
        for ch in channels:
            if row[ch] not in (None, ""):
                params[ch][row["metric"]] = to_num(row[ch])

    facts = []
    for row in read_csv(root / "数据" / "repo_facts.csv"):
        item = dict(row)
        for k in NUMERIC_TEST_FIELDS:
            if k in item:
                item[k] = to_num(item[k])
        item.pop("test_files", None)
        facts.append(item)

    meta_path = root / "数据" / "repo_facts.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    return {
        "meta": {
            "as_of_commit": meta.get("as_of_commit", ""),
            "as_of_date": meta.get("as_of_date", ""),
            "total_commits": meta.get("total_commits"),
            "total_files": meta.get("total_files"),
            "total_tests": meta.get("total_tests"),
            "generator": "tools/gen_data_js.py",
        },
        "rubric": rubric,
        "titles": titles,
        "params": params,
        "channels": channels,
        "facts": facts,
    }


def render(payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return HEADER + "(function (root) {\n  var DATA = " + body + ";\n" + (
        "  if (typeof module === 'object' && module.exports) module.exports = DATA;\n"
        "  else root.C7DATA = DATA;\n"
        "})(typeof self !== 'undefined' ? self : this);\n"
    )


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="生成 app 数据包")
    ap.add_argument("--root", default=str(here))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    text = render(build(root))
    target = root / "app" / "js" / "core" / "data.js"

    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print("[stale] app/js/core/data.js 与 CSV 不一致，请重跑 tools/gen_data_js.py", file=sys.stderr)
            return 1
        print("[ok] data.js 与源数据一致")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="")
    payload = build(root)
    print(f"[ok] data.js  ({target.stat().st_size // 1024} KB) — "
          f"{len(payload['titles'])} 条标题 / {len(payload['channels'])} 个渠道 / {len(payload['facts'])} 个目录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
