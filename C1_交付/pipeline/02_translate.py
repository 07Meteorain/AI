"""
02_translate.py — 翻译阶段：Segment → 中文译文。

三种 provider，可通过 config.json 的 translate.provider 切换：
  · cache：只读cache/translations/*.json（默认）。零网络、零成本、完全可复跑。
  · llm：调用 LLM API（OpenAI 兼容接口）。缓存未命中的才走 API，命中的直接复用。
  · echo：把原文原样写入（仅用于跑通流程/做对照基线，不算译文）。

核心设计——为什么要缓存：
  翻译是这套管线里唯一「贵」且「不确定」的环节。把译文按原文 sha1 落盘成缓存后，
  ① 重新跑 QC / 建站时零成本；② 译文一旦人工校对过就成为「黄金版本」，不会被重跑覆盖；
  ③ 换源复用时，只有新增内容才会产生 API 花费。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from common import (
    Glossary, count_words, ensure_dir, load_config, log, ok, read_jsonl, sha1,
    warn, write_jsonl, PIPELINE_DIR,
)

# ------------------------------------------------------------------ prompt

SYSTEM_PROMPT = """你是一位资深技术译者，正在把斯坦福 CS146S（AI 辅助编程）课程的英文资料翻译成简体中文。

## 硬性要求（违反即视为不合格）
1. **术语一致**：严格使用下方术语表的译法。同一概念全文只能有一种译法。
2. **保留专有名词**：产品名、公司名、协议名、编程语言名、命令、代码标识符、文件路径一律保留英文原样，不音译不意译。
   - 例：Claude Code、Codex、MCP、OAuth、Kubernetes、npm、git commit 全部原样保留。
3. **代码不译**：` ``` ` 代码块、行内代码 `like this`、命令行输出、文件路径、日志片段原样保留。
   代码块里的注释如果是英文，可以翻译成中文注释，但代码本身绝不能改。
4. **Markdown 格式保持**：输入的 Markdown 结构（# 层级、- 列表、> 引用、``` 代码块围栏、表格分隔行 | --- |）必须原样输出，块数与层级不变。
5. **不增不减**：不要总结、不要扩写、不要跳过段落、不要添加原文没有的解释。段落数必须与输入一致。
6. **地道中文**：用中文技术写作的语感，不要翻译腔。句子要通顺，避免"被"、"进行一个"这类欧化表达。
   - 原文 "This means the model is doing X" → "这意味着模型在 X"，不要写成"这意味着模型正在被用来进行 X"。
7. **保留语气**：原文是教学口吻就译成教学口吻，原文有幽默感就保留幽默感。

## 输出格式
只输出译文本身，不要输出任何解释、不要输出"以下是翻译"、不要用 ``` 包裹整个输出。
译文前后不要加任何额外内容。

## 术语表（英文 → 规范中文译法）
{glossary}
"""


def build_prompt(segment: dict, glossary: Glossary) -> tuple[str, str]:
    """只注入该Segment 里实际出现的术语，避免 171 条全量注入稀释注意力。"""
    text = segment["text"]
    low = text.lower()
    hit = []
    for t in glossary.terms:
        keys = [t.en.lower()] + [a.lower() for a in t.aliases]
        if any(k and k in low for k in keys):
            hit.append(t.en)
    block = glossary.glossary_prompt_block(hit) if hit else "（本段无特殊术语，按通用规则翻译）"
    sys_p = SYSTEM_PROMPT.replace("{glossary}", block)
    return sys_p, text


# ------------------------------------------------------------- providers

class CacheProvider:
    """读缓存；未命中返回 None。"""

    name = "cache"

    def __init__(self, cache_dir: Path):
        self.dir = cache_dir
        ensure_dir(self.dir)

    def path_for(self, fp: str) -> Path:
        return self.dir / f"{fp}.json"

    def get(self, segment: dict) -> str | None:
        p = self.path_for(segment["fingerprint"])
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))["zh"]
            except Exception:
                return None
        return None

    def put(self, segment: dict, zh: str, meta: dict | None = None) -> None:
        p = self.path_for(segment["fingerprint"])
        p.write_text(json.dumps({
            "seg_id": segment["seg_id"], "doc_id": segment["doc_id"],
            "fingerprint": segment["fingerprint"], "zh": zh,
            "meta": meta or {},
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    def translate_many(self, segments: list[dict], **kw) -> dict[str, str]:
        return {}


class LLMProvider(CacheProvider):
    """调用 OpenAI 兼容 API 翻译，命中缓存的直接复用。"""

    name = "llm"

    def __init__(self, cache_dir: Path, cfg: dict, glossary: Glossary):
        super().__init__(cache_dir)
        self.cfg = cfg
        self.glossary = glossary
        self.api_key = os.environ.get(cfg.get("api_key_env", "OPENAI_API_KEY"), "")
        self.model = cfg.get("model", "gpt-4o-mini")
        self.api_base = cfg.get("api_base", "https://api.openai.com/v1").rstrip("/")
        self.retries = int(cfg.get("max_retries", 3))

    def _call(self, sys_p: str, user_p: str) -> str:
        import urllib.request
        payload = json.dumps({
            "model": self.model, "temperature": 0.2,
            "messages": [{"role": "system", "content": sys_p},
                         {"role": "user", "content": user_p}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def translate_many(self, segments: list[dict], **kw) -> dict[str, str]:
        todo = [s for s in segments if s["kind"] != "code" and self.get(s) is None]
        if not todo:
            return {}
        if not self.api_key:
            warn("LLM provider 未配置 API key，本次全部跳过（结果等价于 cache provider）")
            return {}
        done = 0
        t0 = time.time()
        for s in todo:
            sys_p, user_p = build_prompt(s, self.glossary)
            for attempt in range(self.retries):
                try:
                    zh = self._call(sys_p, user_p)
                    self.put(s, zh, {"provider": "llm", "model": self.model})
                    done += 1
                    if done % 10 == 0:
                        log("translate", f"API 进度 {done}/{len(todo)}  {time.time()-t0:.0f}s")
                    break
                except Exception as e:
                    if attempt == self.retries - 1:
                        err(f"{s['seg_id']} 翻译失败：{e}")
                    else:
                        time.sleep(2 ** attempt)
        return {}


class EchoProvider(CacheProvider):
    """原样透传（跑通流程用，不算译文）。"""
    name = "echo"

    def translate_many(self, segments: list[dict], **kw) -> dict[str, str]:
        out = {}
        for s in segments:
            if s["kind"] == "code":
                continue
            if self.get(s) is None:
                zh = s["text"]
                self.put(s, zh, {"provider": "echo"})
                out[s["seg_id"]] = zh
        return out


PROVIDERS = {"cache": CacheProvider, "llm": LLMProvider, "echo": EchoProvider}

# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PIPELINE_DIR / "config.json"))
    ap.add_argument("--provider", choices=list(PROVIDERS), help="覆盖配置里的 provider")
    ap.add_argument("--limit", type=int, help="只处理前N 个 Segment（调试用）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    proj = cfg["project"]
    glossary = Glossary.load(proj["glossary"])

    segments = read_jsonl(proj["work_dir"] / "segments.jsonl")
    if args.limit:
        segments = segments[: args.limit]
    log("translate", f"载入{len(segments)} 个 Segment，术语表 {len(glossary)} 条")

    pname = args.provider or cfg["translate"].get("provider", "cache")
    cache_dir = ensure_dir(proj["cache_dir"])
    if pname == "llm":
        provider = LLMProvider(cache_dir, cfg["translate"], glossary)
    elif pname == "echo":
        provider = EchoProvider(cache_dir)
    else:
        provider = CacheProvider(cache_dir)

    # 1) 让provider 填充缓存中缺失的部分
    provider.translate_many(segments)

    # 2) 组装译文（缓存未命中的标记为 pending）
    out_rows, hit, miss, pending_words = [], 0, 0, 0
    for s in segments:
        if s["kind"] == "code":
            zh, status = s["text"], "passthrough_code"
        else:
            zh = provider.get(s)
            if zh:
                status, hit = "translated", hit + 1
            else:
                status, miss = "pending", miss + 1
                pending_words += s["word_count"]
        out_rows.append({**s, "zh": zh, "status": status,
                         "zh_word_count": count_words(zh) if zh else 0})

    n = write_jsonl(proj["work_dir"] / "translations.jsonl", out_rows)
    total_pending = miss
    log("translate", f"provider={pname}  已译 {hit} / 待译 {miss} / 代码透传 {sum(1 for r in out_rows if r['status']=='passthrough_code')}")
    if miss:
        warn(f"待译 {miss} 个 Segment（约 {pending_words} 词）。"
             f"配置 API key 后设 provider=llm 可自动补齐；否则用 AI 逐段翻译后写入 cache/translations/")
    ok(f"→ work/translations.jsonl（{n} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
