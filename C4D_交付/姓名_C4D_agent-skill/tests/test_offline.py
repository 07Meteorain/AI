"""离线单元测试：不依赖 Ollama 服务，验证核心逻辑正确性。

运行：python -m pytest tests/ -v
或直接：python tests/test_offline.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sias_local_agent.knowledge import (  # noqa: E402
    KNOWLEDGE_BASE,
    SIAS_CENTER,
    get_by_id,
    knowledge_catalog,
    search_knowledge,
)
from sias_local_agent.llm import OllamaClient, OllamaError, _extract_json  # noqa: E402
from sias_local_agent.map_view import (  # noqa: E402
    build_map_html,
    normalize_locations,
)
from sias_local_agent.memory import MemoryStore, memory_prompt_block  # noqa: E402
from sias_local_agent.tools import (  # noqa: E402
    build_registry,
    tool_validate_coords,
)


# ---------- JSON 提取 ----------


def test_extract_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_fence():
    text = '```json\n{"a": [1, 2, 3]}\n```'
    assert _extract_json(text) == {"a": [1, 2, 3]}


def test_extract_with_surrounding_prose():
    text = '好的，结果如下：\n{"locations": [{"name": "x"}]}\n希望有帮助。'
    assert _extract_json(text)["locations"][0]["name"] == "x"


def test_extract_nested_braces():
    text = 'noise {"a": {"b": "} not end"}, "c": [1, {"d": 2}]} trailing'
    out = _extract_json(text)
    assert out["a"]["b"] == "} not end"
    assert out["c"][1]["d"] == 2


def test_extract_top_level_array():
    """地图任务输出通常是顶层数组，必须优先按数组解析。"""
    out = _extract_json('[{"a": 1}, {"b": 2}]')
    assert isinstance(out, list) and len(out) == 2


def test_extract_array_with_objects():
    text = '[{"name":"A","lat":1.0,"lng":2.0},{"name":"B","lat":3.0,"lng":4.0}]'
    out = _extract_json(text)
    assert isinstance(out, list)
    assert out[1]["name"] == "B"


def test_extract_rejects_truncated_output():
    """被截断的 JSON 不应被当作完整结果接受。

    这是真实运行中发现的问题：小模型达到长度上限后输出不完整 JSON。
    截断的顶层数组 [...] 尚未闭合，但内部对象是平衡的，
    早期实现会静默返回第一个对象，导致下游拿到不完整数据。
    修正后：只有当顶层结构平衡时才接受。
    """
    truncated = (
        '[{"name":"A","lat":1.0,"lng":2.0},'
        '{"name":"B","description":"campus\'s image'
    )
    try:
        result = _extract_json(truncated)
    except OllamaError:
        return  # 期望路径：明确报错
    # 若未报错，必须至少是完整数组而非残缺子对象
    assert isinstance(result, list), f"截断输出返回了 {type(result).__name__}，应为list"


def test_extract_rejects_trailing_garbage():
    """片段后还有同类结构时，必须取更完整的那个，而不是第一个子对象。"""
    text = '{"a":1} 还有别的 {"b": {"c": 2}} 内容'
    out = _extract_json(text)
    assert out == {"b": {"c": 2}}


def test_extract_accepts_trailing_whitespace():
    assert _extract_json('{"a": 1}  \n  ') == {"a": 1}


# ---------- 知识库 ----------


def test_knowledge_all_coords_valid():
    """所有知识条目坐标必须在合理范围内（防止数据录入错误）。"""
    for e in KNOWLEDGE_BASE:
        assert 34.0 < e["lat"] < 35.0, f"{e['id']} lat 越界"
        assert 113.0 < e["lng"] < 114.5, f"{e['id']} lng 越界"
        assert e["desc_zh"] and e["desc_en"], f"{e['id']} 缺少描述"


def test_knowledge_has_sias():
    assert any(e["id"] == "sias_main" for e in KNOWLEDGE_BASE)
    assert SIAS_CENTER["lat"] == 34.4016


def test_search_by_chinese_alias():
    hits = search_knowledge("图书馆")
    assert hits and hits[0]["id"] == "sias_library"


def test_search_by_english_alias():
    hits = search_knowledge("library")
    assert hits and hits[0]["id"] == "sias_library"


def test_search_empty_returns_all():
    """空查询返回全部条目（受 limit 约束）。"""
    assert len(search_knowledge("")) == min(10, len(KNOWLEDGE_BASE))
    assert len(search_knowledge("", limit=100)) == len(KNOWLEDGE_BASE)


def test_search_category_filter():
    hits = search_knowledge("", categories=["culture"])
    assert all(h["category"] == "culture" for h in hits)
    assert len(hits) >= 2


def test_catalog_shape():
    cat = knowledge_catalog()
    assert len(cat) == len(KNOWLEDGE_BASE)
    for c in cat:
        assert {"id", "name_zh", "name", "lat", "lng"} <= set(c)


def test_get_by_id():
    assert get_by_id("sias_main") is not None
    assert get_by_id("nope") is None


# ---------- 工具 ----------


def test_validate_coords_inside():
    r = tool_validate_coords(34.4016, 113.7361)
    assert r["in_expected_region"] is True
    assert r["distance_from_sias_km"] < 0.01


def test_validate_coords_outside():
    r = tool_validate_coords(39.9, 116.4)  # 北京，不应通过
    assert r["in_expected_region"] is False
    assert "幻觉" in r["verdict"]


def test_registry_schemas_valid():
    reg = build_registry()
    assert len(reg) >= 5
    for name, tool in reg.items():
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == name
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert params["properties"], f"{name} 无参数定义"
        for req in params.get("required", []):
            assert req in params["properties"], f"{name}.{req} 未定义"


def test_tool_invoke_roundtrip():
    reg = build_registry()
    out = reg["get_reference"].invoke({"name": "图书馆"})
    data = json.loads(out)
    assert data["results"][0]["id"] == "sias_library"


def test_plan_route_sorts_by_distance():
    reg = build_registry()
    out = json.loads(
        reg["plan_route"].invoke({"stops": "湿地, 图书馆, 博物馆", "mode": "walking"})
    )
    assert out["stop_count"] == 3
    assert len(out["route"]) == 3
    # 图书馆离校园最近，应排在首位
    assert "图书馆" in out["route"][0]


def test_plan_route_empty_raises():
    reg = build_registry()
    try:
        reg["plan_route"].invoke({"stops": ""})
    except Exception as exc:  # ToolError
        assert "empty" in str(exc).lower() or "空" in str(exc)
    else:
        raise AssertionError("空 stops 应当报错")


# ---------- 记忆 ----------


def test_memory_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "m.db"
        mem = MemoryStore(db, session_id="s1")
        mem.add_turn("user", "你好")
        mem.add_turn("assistant", "你好，有什么可以帮你")
        mem.remember("偏好语言", "中文")
        assert mem.recall("偏好")[0]["value"] == "中文"

        # 重新打开验证持久化
        mem.close()
        mem2 = MemoryStore(db, session_id="s1")
        assert len(mem2.history()) == 2
        assert mem2.recall()[0]["key"] == "偏好语言"
        assert mem2.stats().turns == 2
        mem2.close()


def test_memory_session_isolation():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "m.db"
        a = MemoryStore(db, session_id="a")
        b = MemoryStore(db, session_id="b")
        a.remember("k", "A的值")
        b.remember("k", "B的值")
        assert a.recall()[0]["value"] == "A的值"
        assert b.recall()[0]["value"] == "B的值"
        a.close()
        b.close()


def test_memory_upsert():
    with tempfile.TemporaryDirectory() as td:
        mem = MemoryStore(Path(td) / "m.db", session_id="s")
        mem.remember("k", "v1")
        mem.remember("k", "v2")
        assert len(mem.recall()) == 1
        assert mem.recall()[0]["value"] == "v2"
        assert mem.forget("k") is True
        assert mem.recall() == []
        mem.close()


def test_memory_prompt_trim():
    with tempfile.TemporaryDirectory() as td:
        mem = MemoryStore(Path(td) / "m.db", session_id="s")
        for i in range(30):
            mem.add_turn("user", "问题" * 200)
            mem.add_turn("assistant", "回答" * 200)
        msgs, stats = mem.build_messages("系统提示")
        assert msgs[0]["role"] == "system"
        assert stats.trimmed_turns > 0
        assert len(msgs) < 62  # 被裁剪过
        mem.close()


def test_memory_prompt_block():
    assert memory_prompt_block([]) == ""
    txt = memory_prompt_block([{"key": "k", "value": "v"}])
    assert "k: v" in txt


# ---------- 地图输出归一化 ----------


def test_normalize_variants():
    parsed = {
        "locations": [
            {"name": "Lib", "name_zh": "图书馆", "lat": 34.4,
             "lng": 113.7, "category": "campus"},
        ]
    }
    out = normalize_locations(parsed)
    assert len(out) == 1
    assert out[0]["name_zh"] == "图书馆"
    assert out[0]["lat"] == 34.4


def test_normalize_bare_list():
    out = normalize_locations([{"name": "A", "latitude": 1.0, "longitude": 2.0}])
    assert out[0]["lat"] == 1.0 and out[0]["lng"] == 2.0


def test_normalize_drops_bad_rows():
    out = normalize_locations(
        {"locations": [
            {"name": "ok", "lat": 34.4, "lng": 113.7},
            {"name": "bad", "lat": "not-a-number", "lng": 113.7},
            {"lat": 34.4, "lng": 113.7},          # 缺名称
            "not a dict",
        ]}
    )
    assert len(out) == 1
    assert out[0]["name_zh"] == "ok"


def test_normalize_unknown_category_defaults():
    out = normalize_locations([{"name": "X", "lat": 1.0, "lng": 2.0,
                                 "category": "unknown_cat"}])
    assert out[0]["category"] == "campus"


def test_normalize_empty_input():
    assert normalize_locations(None) == []
    assert normalize_locations({}) == []


# ---------- 地图 HTML ----------


def test_map_html_contains_required():
    locs = normalize_locations(
        {"locations": [
            {"name": "SIAS", "name_zh": "西亚斯学院", "latitude": 34.4016,
             "longitude": 113.7361, "category": "campus",
             "description": "主校区", "description_en": "Main campus"},
        ]}
    )
    html = build_map_html(locs, model_info={"model": "gemma4:e4b",
                                             "tok_per_second": 12.3})
    assert "腾讯地图" in html or "map.qq.com" in html
    assert "TMap.Map" in html
    assert "34.4016" in html
    assert "西亚斯学院" in html
    assert "gemma4:e4b" in html
    assert "12.3" in html
    # 不得出现境外地图源
    for banned in ("openstreetmap", "mapbox", "google.com/maps", "googleapis"):
        assert banned not in html.lower(), f"含不合规地图源: {banned}"


def test_map_html_escapes_xss():
    locs = normalize_locations(
        [{"name": "<img src=x onerror=alert(1)>", "name_zh": "<script>bad</script>",
          "lat": 34.4, "lng": 113.7}]
    )
    html = build_map_html(locs)
    assert "<script>bad</script>" not in html
    assert "&lt;script&gt;" in html


def test_map_html_empty_safe():
    html = build_map_html([])
    assert "TMap.Map" in html  # 仍能渲染，只是无标记


# ---------- 客户端离线行为 ----------


def test_client_unavailable_graceful():
    """Ollama 未启动时，is_available 返回 False 而不是抛异常。"""
    c = OllamaClient(base_url="http://127.0.0.1:59999", timeout=1)
    assert c.is_available() is False


def test_tok_per_second_zero_safe():
    from sias_local_agent.llm import LLMResponse

    r = LLMResponse(content="x", eval_count=100, eval_duration_ns=0)
    assert r.tokens_per_second == 0.0
    assert "tok/s=0.00" in r.usage_line()


def _run_all() -> int:
    """无 pytest 时的直接执行入口。"""
    fns = [
        (k, v) for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failed = []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())