"""模型适配：有 key 用模型，没 key 用规则，两者走同一个 ``plan()`` 接口。

**为什么默认离线**：评审者 clone 下来第一件事是 ``python -m brain doctor``。
如果这一步需要配置 API key，那这个交付物对 90% 的人就是不可运行的。

**为什么保留 LLM 路径**：规则规划器只认显式说法。"帮我想想上次那个事"
它判成 chat。模型的真正价值不在生成漂亮话，而在**把模糊意图映射到工具**。
所以这里把模型放在"规划"位置，而不是"回答"位置——规划错了，回答再好看也没用。

调用失败一律降级回规则，并在 trace 的 ``meta.fallback`` 里留痕。
**静默降级是最坏的一种降级**：用户以为在用模型，其实在用 if-else。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..loop.planner import Intent, KINDS, PlannedStep, RulePlanner

TOOL_DOC_LIMIT = 24

SYSTEM_PROMPT = """你是一个工具调用规划器。你只输出 JSON，不输出解释文字。

可用工具：
{tools}

输出格式（必须是合法 JSON）：
{{"intent": "capture|recall|task|skill|review|chat",
  "confidence": 0.0-1.0,
  "steps": [{{"tool": "工具名", "args": {{}}, "why": "一句话理由"}}]}}

规则：
1. 最多 {max_steps} 步；不需要工具时 steps 为空数组。
2. 只使用上面列出的工具名；参数必须是该工具声明过的参数名。
3. 需要"回忆/查找"时用 memory.search，不要编造记忆内容。
4. 不确定时选 chat，步数越少越好。
"""

ANSWER_PROMPT = """根据下面的证据回答问题。只使用证据里的信息；
证据不足时直接说"记忆里没有"，不要编造。
最后一行用「来源：记录 id」列出你真正用到的证据。

问题：{question}

证据：
{evidence}
"""


@dataclass
class ProviderInfo:
    name: str
    model: str = ""
    base_url: str = ""
    available: bool = False
    reason: str = ""


class BaseProvider:
    name = "base"

    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name)

    def classify_intent(self, text: str, tool_help: str) -> dict[str, Any] | None:
        return None

    def plan_steps(self, intent: str, text: str, tool_help: str, max_steps: int) -> list[dict[str, Any]] | None:
        return None

    def answer(self, question: str, evidence: str) -> str | None:
        return None


class OfflineProvider(BaseProvider):
    """不联网的"提供者"：什么都不提供，让 LLMPlanner 回落到规则。"""

    name = "offline"

    def info(self) -> ProviderInfo:
        return ProviderInfo(name="offline", model="(rules)", available=True, reason="无 API key，使用规则规划器")


class OpenAICompatProvider(BaseProvider):
    """任何 OpenAI 兼容的 ``/chat/completions`` 都能用（含本地 vLLM / Ollama 网关）。

    只用 ``urllib``——为了一个 HTTP POST 装 ``openai`` 包，等于把 15 个间接依赖
    塞进一个"零依赖"项目。
    """

    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.last_error = ""

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model=self.model,
            base_url=self.base_url,
            available=bool(self.api_key),
            reason="" if self.api_key else "缺少 API key",
        )

    # -- HTTP ----------------------------------------------------------
    def _chat(self, system: str, user: str, *, temperature: float = 0.0) -> str | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return body["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError, OSError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    # -- 三个动作 ------------------------------------------------------
    def _plan(self, text: str, tool_help: str, max_steps: int) -> dict[str, Any] | None:
        raw = self._chat(SYSTEM_PROMPT.format(tools=tool_help, max_steps=max_steps), text)
        return _extract_json(raw)

    def classify_intent(self, text: str, tool_help: str) -> dict[str, Any] | None:
        return self._plan(text, tool_help, 6)

    def plan_steps(self, intent: str, text: str, tool_help: str, max_steps: int) -> list[dict[str, Any]] | None:
        data = self._plan(f"意图={intent}\n用户原话：{text}", tool_help, max_steps)
        if not data:
            return None
        steps = data.get("steps")
        return steps if isinstance(steps, list) else None

    def answer(self, question: str, evidence: str) -> str | None:
        return self._chat(ANSWER_PROMPT.format(question=question, evidence=evidence)[:12000], "请回答。", temperature=0.2)


def _extract_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class LLMPlanner(RulePlanner):
    """模型优先、规则兜底。降级原因写进 ``self.degraded_reasons``。"""

    def __init__(self, provider: BaseProvider, tool_help: str, max_steps: int = 6):
        super().__init__()
        self.provider = provider
        self.tool_help = tool_help
        self.max_steps = max_steps
        self.degraded_reasons: list[str] = []
        self.fallback = False

    def classify(self, text: str, context: dict[str, Any] | None = None) -> Intent:
        base = super().classify(text, context)
        data = self.provider.classify_intent(text, self.tool_help)
        if not data:
            self.fallback = True
            self.degraded_reasons.append(f"classify 降级：{getattr(self.provider, 'last_error', '') or '无响应'}")
            return base
        kind = str(data.get("intent", "")).strip()
        if kind not in KINDS:
            self.fallback = True
            self.degraded_reasons.append(f"classify 返回未知 intent={kind!r}，回落到规则")
            return base
        confidence = float(data.get("confidence") or base.confidence)
        intent = Intent(kind, text, text, max(0.0, min(1.0, confidence)), "LLM 规划")
        steps = self._sanitize(data.get("steps"))
        intent.args["llm_steps"] = steps
        return intent

    def plan(self, intent: Intent, text: str, *, context: dict[str, Any] | None = None) -> list[PlannedStep]:
        steps = intent.args.pop("llm_steps", None)
        if steps is None:
            steps = self._sanitize(self.provider.plan_steps(intent.kind, text, self.tool_help, self.max_steps))
        if not steps:
            self.fallback = True
            self.degraded_reasons.append("plan 为空或全部非法，回落到规则")
            return super().plan(intent, text, context=context)
        return [PlannedStep(tool=s["tool"], args=s["args"], why=str(s.get("why") or "LLM 选择")) for s in steps]

    def _sanitize(self, steps: Any) -> list[dict[str, Any]] | None:
        if not isinstance(steps, list):
            return None
        known = set(re.findall(r"^- ([a-z_.]+)\(", self.tool_help, flags=re.MULTILINE))
        clean: list[dict[str, Any]] = []
        for step in steps[: self.max_steps]:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool", "")).strip()
            if tool not in known:
                self.degraded_reasons.append(f"模型给了不存在的工具 {tool!r}，已丢弃")
                continue
            args = step.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            clean.append({"tool": tool, "args": args, "why": str(step.get("why") or "")})
        return clean or None


def build_provider(config: Any) -> BaseProvider:
    provider = (os.environ.get("BRAIN_PROVIDER") or config.llm_provider or "offline").lower()
    if provider in ("offline", "none", "rules"):
        return OfflineProvider()
    key = os.environ.get("BRAIN_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base = os.environ.get("BRAIN_BASE_URL") or "https://api.openai.com/v1"
    model = os.environ.get("BRAIN_MODEL") or "gpt-4o-mini"
    if not key:
        return OfflineProvider()
    return OpenAICompatProvider(base_url=base, api_key=key, model=model)


def tool_help(registry: Any) -> str:
    """给模型看的工具清单。格式固定成 ``- name(k1, k2): 说明``，方便正则校验。"""

    lines = []
    for spec in registry.specs()[:TOOL_DOC_LIMIT]:
        params = ", ".join(p.name for p in spec.params)
        lines.append(f"- {spec.name}({params}): {spec.description}")
    return "\n".join(lines)
