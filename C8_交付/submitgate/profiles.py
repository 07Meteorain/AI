"""评分维度 → 可观察证据的映射表。

两张表，职责分开：

1. ``DIMENSION_PROFILES``：平台每个维度 id 归到哪一类证据；
2. ``PROFILE_SPECS``：每一类证据由哪几个「文件存在性」判定项组成。

为什么不把 5 个通用维度写死：平台的维度 id 是**每个挑战各自定义的**。
C3 有 ``participationQuality``/``substance``/``collaboration``，
C5 有 ``repoQuality``/``community``，C10 有 ``systemArchitecture``/``memorySystem``。
写死五个 id 的结果是：遇到不认识的维度就静默 0 分 —— 这不是「没做好」，是工具说谎。
"""

from __future__ import annotations

from dataclasses import dataclass

from .challenge import RubricDimension


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    patterns: tuple[str, ...]


PROFILE_SPECS: dict[str, tuple[EvidenceItem, ...]] = {
    "repo": (
        EvidenceItem("README", ("README*",)),
        EvidenceItem("LICENSE", ("LICENSE*",)),
        EvidenceItem("测试目录", ("tests/*", "test/*")),
        EvidenceItem("CI 工作流", (".github/workflows/*",)),
        EvidenceItem("文档目录", ("docs/*",)),
    ),
    "community": (
        EvidenceItem("Issue 模板", (".github/ISSUE_TEMPLATE/*",)),
        EvidenceItem("PR 模板", (".github/PULL_REQUEST_TEMPLATE.md",)),
        EvidenceItem("贡献指南", ("CONTRIBUTING*",)),
        EvidenceItem("行为准则", ("CODE_OF_CONDUCT*",)),
        EvidenceItem("安全策略", ("SECURITY*",)),
        EvidenceItem("变更日志", ("CHANGELOG*",)),
    ),
    "engineering": (
        EvidenceItem("测试", ("tests/*", "test/*")),
        EvidenceItem("入口或依赖清单", ("pyproject.toml", "package.json", "__main__.py", "setup.py", "requirements.txt")),
        EvidenceItem("文档", ("docs/*", "README*")),
        EvidenceItem("CI 工作流", (".github/workflows/*",)),
    ),
    "product": (
        EvidenceItem("应用入口", ("app/index.html", "index.html", "*.html")),
        EvidenceItem("在线链接", ("app链接*", "*链接*", "*url*")),
        EvidenceItem("演示材料", ("demo/*",)),
        EvidenceItem("截图", ("demo/截图/*", "*.png", "*.jpg", "*.webp")),
    ),
    "data": (
        EvidenceItem("数据文件", ("data/*", "*.csv", "*.json", "*.xlsx")),
        EvidenceItem("分析报告", ("*报告*", "*分析*", "reports/*")),
        EvidenceItem("看板或图表", ("*.html", "*仪表盘*", "*图表*", "*dashboard*")),
    ),
    "content": (
        EvidenceItem("正文", ("*.md", "*.html")),
        EvidenceItem("选题或标题", ("*标题*", "*选题*")),
        EvidenceItem("数据截图", ("*截图*", "*.png", "*.jpg")),
    ),
    "collab": (
        EvidenceItem("协作记录", ("*协作*", "*合并记录*")),
        EvidenceItem("互评或评审", ("*评审*", "*互评*", "*review*")),
        EvidenceItem("迁移或教学笔记", ("*迁移*", "notes/*")),
    ),
    "transfer": (
        EvidenceItem("迁移笔记", ("*迁移*", "*transfer*")),
        EvidenceItem("互教或教学记录", ("*教学*", "*互教*")),
        EvidenceItem("评审或互检", ("*评审*", "*互评*")),
    ),
    "gitpractice": (
        EvidenceItem("实战记录", ("*git*", "*分支*", "*pr*")),
        EvidenceItem("证据文件", ("证据/*", "*证据*", "*log*")),
    ),
}


DIMENSION_PROFILES: dict[str, str] = {
    # 通用三件套
    "artifactCompleteness": "artifact",
    "aiUsage": "ai",
    "reflectionQuality": "reflection",
    # C8 / C9
    "delivery": "delivery",
    "problemSolving": "problem",
    "initiative": "docs",
    # C3
    "participationQuality": "docs",
    "substance": "docs",
    "collaboration": "collab",
    # C3C
    "skillTransfer": "transfer",
    # C5 / C5A
    "repoQuality": "repo",
    "community": "community",
    "fundamentals": "gitpractice",
    "technicalExecution": "engineering",
    # C6 / C6A / C7
    "productQuality": "product",
    "dataInsight": "data",
    "visualization": "data",
    "contentQuality": "content",
    "distribution": "content",
    # C10 / C10H
    "systemArchitecture": "docs",
    "memorySystem": "docs",
    "mastery": "docs",
    "integration": "docs",
}

_FALLBACK_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("完整性", "artifact"),
    ("产物", "artifact"),
    ("复盘", "reflection"),
    ("反思", "reflection"),
    ("ai", "ai"),
    ("交付", "delivery"),
    ("问题", "problem"),
    ("测试", "engineering"),
    ("技术", "engineering"),
    ("仓库", "repo"),
    ("社区", "community"),
    ("协作", "collab"),
    ("传播", "content"),
    ("内容", "content"),
    ("数据", "data"),
    ("可视化", "data"),
    ("产品", "product"),
    ("架构", "docs"),
    ("记忆", "docs"),
    ("驾驭", "docs"),
    ("集成", "docs"),
    ("基础", "gitpractice"),
    ("自驱", "docs"),
    ("参与", "docs"),
)


def profile_for(dimension: RubricDimension) -> str:
    """先查表，再用标签/描述里的关键词兜底，最后落到 ``docs``（需人工）。"""

    known = DIMENSION_PROFILES.get(dimension.id)
    if known:
        return known
    haystack = f"{dimension.label} {dimension.description}".casefold()
    for keyword, profile in _FALLBACK_KEYWORDS:
        if keyword in haystack:
            return profile
    return "docs"
