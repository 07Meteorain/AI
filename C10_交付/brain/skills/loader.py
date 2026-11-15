"""技能发现与加载。

发现规则：``skills/*/SKILL.md``，以及草稿区 ``skills/_drafts/*/SKILL.md``。
草稿是 ``brain evolve`` 自动生成的，``status=draft``，能跑但会在回执里标明"草稿"——
一个自动生成的东西如果装得跟人工打磨的一样，那才是真的危险。
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from .model import Skill, parse_front_matter

REQUIRED_FIELDS = ("name", "description")


def _as_list(value: object) -> list[str]:
    """容忍三种写法：YAML 列表、逗号分隔字符串、空。

    front matter 是人手写的，写成 ``tags: a, b`` 和写成分行列表都属于"正常人类行为"，
    解析器没理由因此把字段丢掉——丢了以后症状是"技能在清单里但没有标签"，
    极难查。
    """

    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [p.strip() for p in value.replace("，", ",").split(",") if p.strip()]
    return []


class SkillLoader:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self._cache: dict[str, Skill] = {}
        self.warnings: list[str] = []

    # -- 发现 ----------------------------------------------------------
    def paths(self) -> list[Path]:
        roots = [self.config.skills_dir, self.config.drafts_dir]
        found: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                skill_md = child / "SKILL.md"
                if child.is_dir() and skill_md.is_file() and not child.name.startswith("."):
                    found.append(skill_md)
        return found

    def load_all(self, *, force: bool = False) -> list[Skill]:
        if self._cache and not force:
            return sorted(self._cache.values(), key=lambda s: s.name)
        self._cache = {}
        self.warnings = []
        for path in self.paths():
            skill = self._load_one(path)
            if skill is None:
                continue
            if skill.name in self._cache:
                self.warnings.append(f"技能名重复：{skill.name}（{path}）被忽略")
                continue
            self._cache[skill.name] = skill
        return sorted(self._cache.values(), key=lambda s: s.name)

    def _load_one(self, path: Path, *, with_body: bool = False) -> Skill | None:
        try:
            raw = path.read_text(encoding="utf-8")
            meta, body = parse_front_matter(raw)
        except (OSError, ValueError) as exc:
            self.warnings.append(f"{path} 解析失败：{exc}")
            return None

        missing = [f for f in REQUIRED_FIELDS if not str(meta.get(f, "")).strip()]
        if missing:
            self.warnings.append(f"{path} 缺少必填字段：{'、'.join(missing)}")
            return None

        name = str(meta["name"]).strip()
        is_draft = "_drafts" in path.parts
        handler = str(meta.get("handler") or meta.get("run") or "").strip()
        if not handler and (path.parent / "handler.py").is_file():
            handler = "handler.py"

        inputs = meta.get("inputs") or {}
        if not isinstance(inputs, dict):
            inputs = {str(k): str(v) for k, v in inputs} if isinstance(inputs, list) else {}

        skill = Skill(
            name=name,
            description=str(meta.get("description", "")).strip(),
            path=path,
            version=str(meta.get("version", "1.0")),
            when=str(meta.get("when", "")).strip(),
            inputs={str(k): str(v) for k, v in inputs.items()},
            tools=_as_list(meta.get("tools")),
            handler=handler,
            body=body if with_body else "",
            tags=_as_list(meta.get("tags")),
            status="draft" if is_draft else "ready",
        )
        if handler and not (path.parent / handler).is_file():
            skill.status = "broken"
            skill.error = f"声明了 handler={handler} 但文件不存在"
        return skill

    # -- 访问 ----------------------------------------------------------
    def get(self, name: str) -> Skill | None:
        self.load_all()
        return self._cache.get(name.strip())

    def require(self, name: str) -> Skill:
        skill = self.get(name)
        if skill is None:
            known = "、".join(s.name for s in self.load_all()) or "（无）"
            raise KeyError(f"没有技能 {name!r}；已有：{known}")
        return skill

    def catalog(self) -> str:
        """清单只列 name + 一句话描述 —— 这就是"常驻成本"。"""

        skills = self.load_all()
        if not skills:
            return "（还没有技能）"
        width = max(len(s.name) for s in skills)
        lines = [f"{'名称'.ljust(width)}  状态   描述"]
        for s in skills:
            lines.append(f"{s.name.ljust(width)}  {s.status:<6} {s.description}")
        return "\n".join(lines)

    def show(self, name: str) -> str:
        skill = self.require(name)
        if not skill.body:
            full = self._load_one(skill.path, with_body=True)
            skill = full or skill
        head = [
            f"# {skill.name}  v{skill.version}  [{skill.status}]",
            f"{skill.description}",
            "",
            f"- 何时用：{skill.when or '（未声明）'}",
            f"- 输入：{'、'.join(skill.inputs) or '（无）'}",
            f"- 依赖工具：{'、'.join(skill.tools) or '（无）'}",
            f"- 实现：{skill.handler or '（纯说明，无 handler）'}",
            f"- 路径：{skill.path}",
            "",
            "---",
            "",
        ]
        return "\n".join(head) + (skill.body or "（正文为空）")

    def resolve_path(self, path: str | Path) -> Path:
        path = Path(path)
        return path if path.is_absolute() else self.config.skills_dir / path
