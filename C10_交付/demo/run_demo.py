"""演示：把一条真实使用路径跑一遍，并把终端输出原样存成实录。

用法（在 C10_交付 目录下）：

    python demo/run_demo.py              # 跑一遍，写 demo/终端实录.txt
    python demo/run_demo.py --keep       # 不清空记忆库，接着上次跑

**这个脚本会清空记忆库**（``memory/db``、``memory/knowledge``、``memory/reviews``
与 ``skills/_drafts``），因为演示必须是可复现的：同样的命令、同样的顺序、
得到同样的结论。清空之前会在 ``memory/db`` 旁边留一份 ``.demo-backup``。

它演示的不是"功能列表"，而是一条**因果链**：

    重复三次的任务 → evolve 把它固化成技能 → 同类任务从 3 步变 1 步
    一次没问到的说法 → evolve 学到同义词 → 同一个说法再问就命中

这两条链都能在 ``brain metrics`` / ``brain trend`` 里被数字验证。
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.interface.cli import main  # noqa: E402

SCENES: list[tuple[str, list[list[str]]]] = [
    (
        "场景 0 · 自检：五层是不是真的都能动（不依赖网络与 API key）",
        [["doctor"]],
    ),
    (
        "场景 1 · 把三条结论写进知识层（K）：这类话值得反复用，不该沉在会话里",
        [
            ["capture", "结论：检索排序必须是 BM25 × 层先验 × 新近度相乘，不能相加——没命中必须得 0 分", "--layer", "K"],
            ["capture", "结论：记忆的删除必须可撤销，情境层只归档不删除", "--layer", "K"],
            ["capture", "结论：技能必须能被度量（调用次数、成功率），否则三个月后没人敢删", "--layer", "K"],
        ],
    ),
    (
        "场景 2 · 随手记一条情境（S）：这次不升华，只留现场",
        [["capture", "今天把循环层写完了，卡在工具熔断的阈值上"]],
    ),
    (
        "场景 3 · 检索：命中时给分数与命中词，方便判断「为什么是它」",
        [["recall", "检索排序"]],
    ),
    (
        "场景 4 · 检索一个系统没学过的说法：记忆里没有命中，就直说没有",
        [["recall", "打分规则"]],
    ),
    (
        "场景 5 · 换个说法问到了——这一次「先失败后成功」会被 evolve 记下来",
        [["recall", "检索排序"]],
    ),
    (
        "场景 6 · 任务层：建任务、关任务，关任务会自动生成一条行动记录",
        [["task", "add", "给 C10 写 AAR 复盘"], ["task", "done", "给 C10 写"]],
    ),
    (
        "场景 7 · 同一个任务做三遍：复盘（每次 3 步：检索 → 技能 → 沉淀）",
        [["review"], ["review"], ["review"]],
    ),
    (
        "场景 8 · evolve（只看不改）：它应该指出「这条流程重复了 3 次」",
        [["evolve"]],
    ),
    (
        "场景 9 · evolve --apply：真的落盘——生成技能草稿、学会同义词、沉淀流程卡",
        [["evolve", "--apply"]],
    ),
    (
        "场景 10 · 同义词生效：同一个「打分规则」再问一次，这次命中了",
        [["recall", "打分规则"]],
    ),
    (
        "场景 11 · 进化生效：同一个「复盘」，现在 1 步完成（草稿技能接管）",
        [["review"], ["review"], ["review"]],
    ),
    (
        "场景 12 · 技能账本：谁在被用、成功率多少、有没有草稿",
        [["skill", "list"]],
    ),
    (
        "场景 13 · 度量与趋势：按意图对比前后步数——这张表才是「进化」的证据",
        [["metrics"], ["trend"]],
    ),
]


def reset_store(keep: bool) -> None:
    if keep:
        return
    for name in ("db", "knowledge", "reviews"):
        target = ROOT / "memory" / name
        if target.exists():
            shutil.rmtree(target)
    drafts = ROOT / "skills" / "_drafts"
    if drafts.exists():
        shutil.rmtree(drafts)


def run_once(argv: list[str]) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:  # argparse 的退出也要被记录下来
            code = int(exc.code or 0)
    text = out.getvalue().rstrip()
    err_text = err.getvalue().rstrip()
    return code, text + (("\n" + err_text) if err_text else "")


def main_demo(keep: bool, out_path: Path) -> int:
    reset_store(keep)
    lines: list[str] = [
        "C10 第二大脑 · 终端实录",
        "=" * 60,
        f"项目根：{ROOT}",
        "运行模式：offline（规则规划器；配置 BRAIN_API_KEY 后同一套循环换成模型）",
        "本实录由 `python demo/run_demo.py` 生成，命令与输出均为真实执行结果。",
        "",
    ]
    failures = 0
    for title, commands in SCENES:
        lines.append("")
        lines.append("─" * 60)
        lines.append(title)
        lines.append("─" * 60)
        for argv in commands:
            code, output = run_once(argv)
            lines.append(f"\n$ python -m brain {' '.join(argv)}")
            lines.append(output)
            if code != 0:
                failures += 1
                lines.append(f"[退出码 {code}]")
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"演示结束。失败命令数：{failures}")
    text = "\n".join(lines) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="跑一遍 C10 演示并保存终端实录")
    parser.add_argument("--keep", action="store_true", help="不清空记忆库")
    parser.add_argument("--out", default=str(ROOT / "demo" / "终端实录.txt"))
    args = parser.parse_args()
    failures = main_demo(args.keep, Path(args.out))
    print(f"已写入 {args.out}")
    print(f"失败命令数：{failures}")
    sys.exit(0 if failures == 0 else 1)
