"""测试夹具：在临时目录里造「课程记录 + 交付仓库」，不依赖真实仓库。"""

from __future__ import annotations

import json
from pathlib import Path

DIMENSIONS = [
    {"id": "delivery", "label": "交付质量", "description": "面向真实需求的交付完成度", "maxPoints": 25},
    {"id": "problemSolving", "label": "问题解决", "description": "解决真实问题的深度与方式", "maxPoints": 20},
    {"id": "artifactCompleteness", "label": "产物完整性", "description": "交付物是否齐全、可运行", "maxPoints": 15},
    {"id": "aiUsage", "label": "AI使用质量", "description": "AI 工具使用是否恰当、有效、可追溯", "maxPoints": 20},
    {"id": "reflectionQuality", "label": "复盘质量", "description": "AAR 反思是否深入", "maxPoints": 20},
]

# C3 的真实维度组合：含两个无法从文件系统验证的维度（参与质量、内容实质）。
FULL_DIMENSIONS = [
    {"id": "participationQuality", "label": "参与质量", "description": "社群参与是否有推动力（提问/讨论类）", "maxPoints": 25},
    {"id": "substance", "label": "内容实质", "description": "参与的含金量（新信息/新视角/可执行结论）", "maxPoints": 20},
    {"id": "collaboration", "label": "协作贡献", "description": "协作任务中的配合质量与技能迁移", "maxPoints": 15},
    {"id": "aiUsage", "label": "AI使用质量", "description": "AI 工具使用是否恰当、有效、可追溯", "maxPoints": 15},
    {"id": "reflectionQuality", "label": "复盘质量", "description": "AAR 反思是否深入", "maxPoints": 20},
    {"id": "artifactCompleteness", "label": "产物完整性", "description": "交付物是否齐全、可运行", "maxPoints": 5},
]

RED_FLAGS = [
    {"id": "missing_artifacts", "description": "核心交付物缺失", "affectedDimension": "artifactCompleteness", "maxScore": 5},
    {"id": "no_ai_log", "description": "无 AI 使用记录/AAR", "affectedDimension": "reflectionQuality", "maxScore": 5},
    {"id": "one_shot_ai", "description": "一句话指令直接提交", "affectedDimension": "aiUsage", "maxScore": 5},
]

README = (
    "# 示例交付\n\n"
    "## 快速开始\n\n"
    "```bash\npython -m demo --limit 3\n```\n\n"
    "## 使用说明\n\n"
    "跑一次就知道结果。\n"
)

AI_LOG = (
    "# AI 使用日志\n\n"
    "## 第 1 轮：定需求\n\n"
    "> 帮我按挑战文件做一个能跑的工具\n\n"
    "AI 先给了三个方案，我选了第二个。\n\n"
    "## 第 2 轮：写代码\n\n"
    "> 加一个离线自检，不要联网\n\n"
    "第一版跑不起来，失败了一次，日志里保留了报错。\n\n"
    "## 第 3 轮：验收\n\n"
    "> 再跑一遍真实数据\n\n"
    "修正了两处误报。\n\n"
)

AAR = (
    "# AAR 复盘\n\n"
    "## 1. 预期 vs 实际\n\n"
    "预期 3 天，实际 5 天，多花 2 天。\n\n"
    "## 2. 失败经验\n\n"
    "F1 忘记先跑测试，导致 1 小时后才发现接口对不上。\n"
    "原因：没定验收断言；修复方式：先写 3 条断言再写实现。\n\n"
    "## 3. 改进方案\n\n"
    "- 下次先写 3 条验收断言，再写实现\n"
)

PROPOSAL = "# 提案\n\n真实需求：交付前能自查缺口。\n"

FILLER = "补充说明：这一行用于把文档撑到有实际内容的体量。\n" * 120


def make_record(source_id: str = "C9", **overrides) -> dict:
    record = {
        "source_id": source_id,
        "challenge_id": f"ch-{source_id.lower()}-test",
        "title": f"{source_id} 测试挑战",
        "brief": "测试用",
        "objective": "测试用",
        "deadline": "2099-12-31T23:59",
        "required_deliverables": "*proposal*,*AI日志*",
        "rubric_dimensions": json.dumps({"version": 1, "dimensions": DIMENSIONS}, ensure_ascii=False),
        "red_flags": json.dumps({"flags": RED_FLAGS}, ensure_ascii=False),
    }
    record.update(overrides)
    return record


def write_course(root: Path, records: dict[str, dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for source_id, record in records.items():
        folder = root / source_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "challenge.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def write_files(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def make_repo(root: Path, folders: dict[str, dict[str, str]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, files in folders.items():
        write_files(root / name, files)
    return root


def full_delivery() -> dict[str, str]:
    """一份「该有的都有」的最小交付。"""

    return {
        "proposal.md": PROPOSAL + FILLER,
        "AI日志.md": AI_LOG + FILLER,
        "AAR_W.md": AAR + FILLER,
        "README.md": README + FILLER,
        "提交说明.md": "# 提交说明\n\n怎么读这份交付。\n" + FILLER,
        "验收/验收单.md": "# 验收单\n\n| 项 | 结论 |\n| --- | --- |\n| 能跑 | 是 |\n" + FILLER,
        "tests/test_demo.py": "def test_ok():\n    assert True\n",
        "demo/输出.txt": "真实运行输出\n",
    }
