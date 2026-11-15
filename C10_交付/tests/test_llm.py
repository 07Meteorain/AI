"""模型适配层：JSON 解析、非法工具过滤、降级、离线 provider。

没有真 API 也能测的部分全测了：模型返回什么形状、返回垃圾怎么办、
降级有没有留痕。这比"能不能连上 OpenAI"重要得多。
"""

from __future__ import annotations

import unittest

from support import BrainCase

from brain.llm.provider import (
    BaseProvider,
    LLMPlanner,
    OfflineProvider,
    OpenAICompatProvider,
    _extract_json,
    build_provider,
    tool_help,
)
from brain.loop.planner import Intent


class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, plan=None, answer=None, classify=None):
        self._plan = plan
        self._answer = answer
        self._classify = classify
        self.last_error = ""

    def classify_intent(self, text, tool_help):
        return self._classify

    def plan_steps(self, intent, text, tool_help, max_steps):
        return self._plan

    def answer(self, question, evidence):
        return self._answer


class TestJsonExtraction(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        raw = '```json\n{"a": 2}\n```'
        self.assertEqual(_extract_json(raw), {"a": 2})

    def test_prose_around(self):
        raw = '好的，这是计划：{"a": 3} 希望有帮助'
        self.assertEqual(_extract_json(raw), {"a": 3})

    def test_garbage(self):
        self.assertIsNone(_extract_json("完全不是 JSON"))
        self.assertIsNone(_extract_json(""))
        self.assertIsNone(_extract_json(None))

    def test_json_array_is_not_accepted(self):
        self.assertIsNone(_extract_json("[1, 2]"))


class TestOfflineProvider(unittest.TestCase):
    def test_info(self):
        info = OfflineProvider().info()
        self.assertTrue(info.available)
        self.assertEqual(info.name, "offline")

    def test_returns_none(self):
        p = OfflineProvider()
        self.assertIsNone(p.classify_intent("x", ""))
        self.assertIsNone(p.plan_steps("chat", "x", "", 3))
        self.assertIsNone(p.answer("q", "e"))

    def test_build_provider_default_is_offline(self):
        class Cfg:
            llm_provider = "offline"

        self.assertIsInstance(build_provider(Cfg()), OfflineProvider)


class TestOpenAICompat(unittest.TestCase):
    def test_without_key_never_calls_network(self):
        p = OpenAICompatProvider("http://127.0.0.1:1/v1", "", "m")
        self.assertIsNone(p.classify_intent("x", ""))

    def test_info_reports_missing_key(self):
        p = OpenAICompatProvider("http://127.0.0.1:1/v1", "", "m")
        self.assertFalse(p.info().available)

    def test_network_error_is_swallowed(self):
        p = OpenAICompatProvider("http://127.0.0.1:1/v1", "fake-key", "m", timeout=0.5)
        self.assertIsNone(p.classify_intent("x", ""))
        self.assertTrue(p.last_error)


class TestLLMPlanner(BrainCase):
    def _help(self):
        return tool_help(self.app.tools)

    def test_valid_plan_used(self):
        provider = FakeProvider(
            classify={"intent": "recall", "confidence": 0.9, "steps": [{"tool": "memory.search", "args": {"query": "复盘"}}]}
        )
        planner = LLMPlanner(provider, self._help())
        intent = planner.classify("帮我想想那个事")
        self.assertEqual(intent.kind, "recall")
        steps = planner.plan(intent, "帮我想想那个事")
        self.assertEqual(steps[0].tool, "memory.search")
        self.assertEqual(steps[0].args["query"], "复盘")

    def test_unknown_tool_discarded_and_fallback(self):
        provider = FakeProvider(classify={"intent": "chat", "steps": [{"tool": "shell.run", "args": {}}]})
        planner = LLMPlanner(provider, self._help())
        intent = planner.classify("你好")
        steps = planner.plan(intent, "你好")
        # 非法工具被丢弃 → 回落到规则（chat = time.now + memory.search）
        self.assertEqual([s.tool for s in steps], ["time.now", "memory.search"])
        self.assertTrue(planner.fallback)
        self.assertTrue(any("不存在的工具" in r for r in planner.degraded_reasons))

    def test_unknown_intent_falls_back(self):
        provider = FakeProvider(classify={"intent": "删除一切", "steps": []})
        planner = LLMPlanner(provider, self._help())
        intent = planner.classify("随便")
        self.assertIn(intent.kind, ("chat", "recall", "capture", "task", "skill", "review"))
        self.assertTrue(planner.degraded_reasons)

    def test_no_response_falls_back(self):
        planner = LLMPlanner(OfflineProvider(), self._help())
        intent = planner.classify("记一下 笔记")
        self.assertEqual(intent.kind, "capture")
        self.assertTrue(planner.fallback)

    def test_too_many_steps_truncated(self):
        steps = [{"tool": "memory.search", "args": {"query": "x"}}] * 10
        provider = FakeProvider(classify={"intent": "recall", "steps": steps})
        planner = LLMPlanner(provider, self._help(), max_steps=3)
        intent = planner.classify("x")
        self.assertEqual(len(planner.plan(intent, "x")), 3)


class TestEngineInLLMMode(BrainCase):
    def test_generated_answer_is_used(self):
        provider = FakeProvider(
            classify={"intent": "chat", "confidence": 0.8, "steps": [{"tool": "memory.search", "args": {"query": "你好"}}]},
            answer="这是模型生成的回答。\n来源：k-1",
        )
        app = self.app
        app.mode = "llm"
        app.provider = provider
        from brain.llm.provider import LLMPlanner

        app.loop.planner = LLMPlanner(provider, tool_help(app.tools))
        app.loop.provider = provider
        app.loop.mode = "llm"
        result = app.loop.run("你好")
        self.assertIn("模型生成的回答", result.answer)
        self.assertIn("LLM 模式", result.answer)

    def test_empty_generation_keeps_extracted_answer(self):
        provider = FakeProvider(classify={"intent": "chat", "steps": [{"tool": "time.now", "args": {}}]}, answer=None)
        app = self.app
        from brain.llm.provider import LLMPlanner

        app.loop.planner = LLMPlanner(provider, tool_help(app.tools))
        app.loop.provider = provider
        app.loop.mode = "llm"
        result = app.loop.run("你好")
        self.assertNotIn("模型生成的回答", result.answer)
        self.assertTrue(result.trace.meta.get("fallback"))

    def test_fallback_flag_recorded(self):
        provider = FakeProvider(classify=None)
        app = self.app
        from brain.llm.provider import LLMPlanner

        app.loop.planner = LLMPlanner(provider, tool_help(app.tools))
        app.loop.mode = "llm"
        result = app.loop.run("你好")
        self.assertTrue(result.trace.meta.get("fallback"))
        self.assertTrue(result.trace.degraded)


if __name__ == "__main__":
    unittest.main()
