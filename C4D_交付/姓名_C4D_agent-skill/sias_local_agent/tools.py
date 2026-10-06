"""工具层：带 JSON Schema 的可调用工具注册表。

这是 Agent「工具调用」能力的载体。每个工具包含：
* name        —— 模型看到并调用的函数名
* description —— 给模型看的语义说明（直接影响调用准确率）
* parameters  —— JSON Schema，映射到 Ollama function calling
* fn          —— 实际执行体

设计原则：
1. 工具与提示词解耦，模型通过 schema 自行决定调用哪个工具。
2. 所有工具纯本地实现（无网络），保证 C4D 的数据主权约束。
3. 内置输入校验与异常兜底，工具失败不应中断整个 Agent 循环。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# 郑州西亚斯学院（SIAS University）基准坐标，位于河南省郑州市新郑市
SIAS_CENTER = {"lat": 34.4016, "lng": 113.7361, "name": "郑州西亚斯学院"}

# 坐标合理性边界：新郑市及周边（用于校验模型是否产生幻觉坐标）
VALID_LAT = (34.30, 34.55)
VALID_LNG = (113.60, 113.90)


class ToolError(RuntimeError):
    """工具执行失败（会被回灌给模型，让它自行纠正）。"""


@dataclass
class Tool:
    """一个可被模型调用的工具。"""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    # 供日志使用的元信息，不暴露给模型
    calls: int = 0

    def to_schema(self) -> dict[str, Any]:
        """转成 Ollama / OpenAI 兼容的 function calling 定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def invoke(self, args: dict[str, Any]) -> str:
        """执行工具并返回字符串结果（供模型阅读）。"""
        try:
            result = self.fn(**args)
        except TypeError as exc:
            raise ToolError(f"参数不匹配: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - 兜底，错误信息回灌模型
            raise ToolError(f"执行失败: {exc}") from exc
        self.calls += 1
        return json.dumps(result, ensure_ascii=False)


# --------------------------------------------------------------------------
# 内置工具实现
# --------------------------------------------------------------------------


def tool_get_reference(
    name: str = "SIAS University",
    categories: str = "",
) -> dict[str, Any]:
    """返回校园及其周边的本地知识条目（知识库检索工具）。

    这是一个「不联网」的检索工具：数据随技能包分发在 knowledge.py，
    目的是证明 Agent 能在完全离线的环境下定位信息，
    再由模型基于检索结果推理与结构化。
    """
    from .knowledge import search_knowledge

    hits = search_knowledge(query=name, categories=categories or None, limit=10)
    return {
        "query": name,
        "match_count": len(hits),
        "results": hits,
        "note": "数据来源为随技能包分发的本地知识库，未访问任何云端服务。",
    }


def tool_validate_coords(lat: float, lng: float) -> dict[str, Any]:
    """校验一组经纬度是否落在合理区域，返回可读的距离描述。"""
    lat = float(lat)
    lng = float(lng)
    ok = VALID_LAT[0] <= lat <= VALID_LAT[1] and VALID_LNG[0] <= lng <= VALID_LNG[1]
    dlat = (lat - SIAS_CENTER["lat"]) * 111.32
    dlng = (lng - SIAS_CENTER["lng"]) * 111.32 * math.cos(math.radians(lat))
    dist = math.hypot(dlat, dlng)
    return {
        "lat": lat,
        "lng": lng,
        "in_expected_region": ok,
        "distance_from_sias_km": round(dist, 3),
        "verdict": (
            "坐标合理，位于西亚斯学院周边"
            if ok
            else "坐标超出预期区域，可能是模型幻觉，需修正"
        ),
    }


def tool_plan_route(
    stops: str = "",
    mode: str = "walking",
) -> dict[str, Any]:
    """把一组地点串成一条顺序合理的参观路线。

    stops 为模型给出的逗号分隔地名列表。此处用最近邻启发式排序，
    属于「多步推理」的可观测证据：模型给地点，Agent 负责排序计算。
    """
    names = [s.strip() for s in re.split(r"[,，;；\n]", stops) if s.strip()]
    if not names:
        raise ToolError("stops 参数为空，请提供逗号分隔的地点名称列表")

    from .knowledge import search_knowledge

    points: list[dict[str, Any]] = []
    for nm in names:
        hits = search_knowledge(query=nm, limit=1)
        if hits:
            points.append(hits[0])
        else:
            points.append(
                {
                    "name": nm,
                    "name_zh": nm,
                    "lat": None,
                    "lng": None,
                    "description": "本地知识库未收录，坐标待模型补全",
                }
            )

    known = [p for p in points if p.get("lat") is not None]
    # 最近邻排序：每步选离当前位置最近的未访问点
    ordered: list[dict[str, Any]] = []
    pool = list(known)
    cur = (SIAS_CENTER["lat"], SIAS_CENTER["lng"])
    while pool:
        def d(p: dict[str, Any]) -> float:
            return math.hypot((p["lat"] - cur[0]) * 111.32,
                              (p["lng"] - cur[1]) * 111.32 * 0.82)

        nxt = min(pool, key=d)
        pool.remove(nxt)
        ordered.append(nxt)
        cur = (nxt["lat"], nxt["lng"])

    unknown = [p for p in points if p.get("lat") is None]
    legs = []
    prev = "西亚斯学院正门"
    for p in ordered:
        legs.append({"from": prev, "to": p["name_zh"], "approx_km": round(
            math.hypot((p["lat"] - SIAS_CENTER["lat"]) * 111.32,
                       (p["lng"] - SIAS_CENTER["lng"]) * 111.32 * 0.82), 2)})
        prev = p["name_zh"]

    return {
        "mode": mode,
        "stop_count": len(names),
        "route": [p["name_zh"] for p in ordered] + (
            [p["name"] for p in unknown]
        ),
        "legs": legs,
        "unresolved": [p["name"] for p in unknown],
        "strategy": "nearest-neighbour 贪心排序（本地计算，无云端路线 API）",
    }


def tool_classify_poi(category: str = "", description: str = "") -> dict[str, Any]:
    """根据关键词把地点归类，用于结构化输出的一致性校验。"""
    categories = {
        "campus": ["学院", "大学", "校园", "教学楼", "图书馆", "宿舍", "体育馆", "实验室"],
        "transit": ["地铁", "公交", "车站", "机场", "高铁", "口"],
        "culture": ["博物馆", "纪念馆", "遗址", "塔", "寺", "庙", "古", "文化"],
        "commerce": ["商场", "超市", "市场", "商业", "购物", "广场"],
        "nature": ["湖", "公园", "湿地", "山", "河", "绿"],
    }
    blob = f"{category} {description}"
    scored = {
        k: sum(1 for w in words if w in blob) for k, words in categories.items()
    }
    best = max(scored, key=lambda k: scored[k])
    return {
        "input_category": category or "(空)",
        "suggested_category": best if scored[best] > 0 else "culture",
        "confidence": round(
            min(1.0, scored[best] / 3) if scored[best] else 0.3, 2
        ),
        "all_scores": scored,
    }


def tool_estimate_walk(minutes_per_site: int = 45, site_count: int = 8) -> dict[str, Any]:
    """估算参观时长，帮助 Agent 做多步规划。"""
    minutes_per_site = max(10, min(int(minutes_per_site), 180))
    site_count = max(1, min(int(site_count), 50))
    total = minutes_per_site * site_count
    return {
        "site_count": site_count,
        "minutes_per_site": minutes_per_site,
        "total_minutes": total,
        "total_hours": round(total / 60, 1),
        "advice": (
            "建议拆成半天行程" if total <= 240
            else "建议全天行程或分两天完成"
        ),
    }


# --------------------------------------------------------------------------
# 工具集
# --------------------------------------------------------------------------


def build_registry() -> dict[str, Tool]:
    """构造默认工具集。"""
    tools = [
        Tool(
            name="get_reference",
            description=(
                "检索西亚斯学院（SIAS University）及周边的本地知识库，"
                "返回地点的标准名称与真实坐标。"
                "在确定任何地点的经纬度之前，先调用此工具核对坐标。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "地点名称，例如 '图书馆' 或 'SIAS University'",
                    },
                    "categories": {
                        "type": "string",
                        "description": "可选，类别过滤：campus/transit/culture/commerce/nature",
                    },
                },
                "required": ["name"],
            },
            fn=tool_get_reference,
        ),
        Tool(
            name="validate_coords",
            description=(
                "校验一组经纬度是否位于西亚斯学院周边合理区域，"
                "并返回与校园的距离（公里）。生成坐标后应调用此工具自查。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "纬度 latitude"},
                    "lng": {"type": "number", "description": "经度 longitude"},
                },
                "required": ["lat", "lng"],
            },
            fn=tool_validate_coords,
        ),
        Tool(
            name="plan_route",
            description=(
                "把多个地点排成一条合理的参观顺序（最近邻贪心）。"
                "当用户要求规划路线或行程时调用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "stops": {
                        "type": "string",
                        "description": "逗号分隔的地点名称列表",
                    },
                    "mode": {
                        "type": "string",
                        "description": "出行方式：walking / cycling / driving",
                    },
                },
                "required": ["stops"],
            },
            fn=tool_plan_route,
        ),
        Tool(
            name="classify_poi",
            description="根据名称与描述判断地点类别（校园/交通/文化/商业/自然）。",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "模型初步判断的类别"},
                    "description": {"type": "string", "description": "地点描述"},
                },
                "required": ["description"],
            },
            fn=tool_classify_poi,
        ),
        Tool(
            name="estimate_walk",
            description="根据地点数量与单点停留时间，估算总参观时长。",
            parameters={
                "type": "object",
                "properties": {
                    "minutes_per_site": {"type": "integer", "description": "每处停留分钟数"},
                    "site_count": {"type": "integer", "description": "地点数量"},
                },
                "required": ["site_count"],
            },
            fn=tool_estimate_walk,
        ),
    ]
    return {t.name: t for t in tools}


def tool_stats(registry: dict[str, Tool]) -> list[dict[str, Any]]:
    """工具调用统计，写入日志证明「多工具调用」确实发生。"""
    return [
        {"tool": name, "calls": tool.calls} for name, tool in sorted(registry.items())
    ]


__all__ = [
    "Tool",
    "ToolError",
    "build_registry",
    "tool_stats",
    "SIAS_CENTER",
    "VALID_LAT",
    "VALID_LNG",
]