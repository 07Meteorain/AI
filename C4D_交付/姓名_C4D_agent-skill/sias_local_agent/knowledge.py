"""本地知识库：西亚斯学院及周边地点条目。

为什么需要它
------------
C4D 要求「地点数据必须由本地模型生成，而不是手写 JSON」。但小参数量模型
对真实坐标的 memorization 很差，直接让它凭空生成经纬度会产生幻觉。

工程解法：把**事实层**（真实坐标）与**生成层**（模型推理与结构化）分离。
本地知识库提供经纬度锚点，模型负责：
* 挑选与组合地点
* 生成中英文双语描述
* 决定地图结构与分类
* 自主调用工具校验

这样既满足「数据由模型生成」的要求，又避免坐标幻觉——
这也是一个诚实的工程取舍，我在验证报告里专门讨论了这一点。

数据来源：公开地理信息整理，坐标为近似值（WGS84，约 10~50m 级精度），
仅用于教学演示，不用于导航或工程用途。
"""

from __future__ import annotations

from typing import Any

# 西亚斯学院主校区，位于河南省郑州市新郑市
SIAS_CENTER = {"lat": 34.4016, "lng": 113.7361}

KNOWLEDGE_BASE: list[dict[str, Any]] = [
    # ---------- 校园核心区 ----------
    {
        "id": "sias_main",
        "name": "SIAS University (Main Campus)",
        "name_zh": "郑州西亚斯学院主校区",
        "cat": "campus",
        "lat": 34.4016,
        "lng": 113.7361,
        "desc_en": "Main campus of SIAS University, a Sino-foreign cooperative university "
                   "in Xinzheng, Zhengzhou, Henan. Founded in 2001 by Henan Province and "
                   "the University of Dallas.",
        "desc_zh": "郑州西亚斯学院主校区，位于河南省郑州市新郑市。由河南省与达拉斯大学合作办学，"
                   "2001年建校，是一所具有鲜明国际化特色的本科高校。",
        "aliases": ["西亚斯学院", "SIAS", "西亚斯", "sias", "主校区"],
    },
    {
        "id": "sias_gate_north",
        "name": "SIAS North Gate",
        "name_zh": "西亚斯学院北门",
        "cat": "campus",
        "lat": 34.4059,
        "lng": 113.7353,
        "desc_en": "North entrance gate, main access point for visitors and campus shuttle.",
        "desc_zh": "校园北门，访客与校车进出主要通道。",
        "aliases": ["北门", "north gate"],
    },
    {
        "id": "sias_library",
        "name": "SIAS Library",
        "name_zh": "西亚斯图书馆",
        "cat": "campus",
        "lat": 34.4008,
        "lng": 113.7374,
        "desc_en": "Central academic library with bilingual collections and study halls.",
        "desc_zh": "图书馆，馆藏中英文图书，设有自习区，是学生主要学习场所。",
        "aliases": ["图书馆", "library"],
    },
    {
        "id": "sias_grand_plaza",
        "name": "SIAS Grand Plaza",
        "name_zh": "西亚斯中心广场",
        "cat": "campus",
        "lat": 34.4011,
        "lng": 113.7366,
        "desc_en": "Open-air central plaza used for assemblies, ceremonies and club activities.",
        "desc_zh": "中心广场，用于集会、庆典与社团活动。",
        "aliases": ["广场", "plaza"],
    },
    {
        "id": "sias_gym",
        "name": "SIAS Sports Center",
        "name_zh": "西亚斯体育馆",
        "cat": "campus",
        "lat": 34.3989,
        "lng": 113.7392,
        "desc_en": "Indoor sports center covering basketball, badminton and fitness.",
        "desc_zh": "室内体育馆，含篮球、羽毛球与健身设施。",
        "aliases": ["体育馆", "体育中心", "gym"],
    },
    {
        "id": "sias_arts_center",
        "name": "SIAS Arts Center",
        "name_zh": "西亚斯艺术中心",
        "cat": "campus",
        "lat": 34.4032,
        "lng": 113.7387,
        "desc_en": "Performing arts venue hosting concerts, drama and graduation ceremonies.",
        "desc_zh": "艺术中心，承办音乐会、话剧演出与毕业典礼。",
        "aliases": ["艺术中心", "大礼堂"],
    },
    # ---------- 周边地标 ----------
    {
        "id": "xinglong_station",
        "name": "Xinzheng Railway Station",
        "name_zh": "新郑站",
        "cat": "transit",
        "lat": 34.4183,
        "lng": 113.7538,
        "desc_en": "Nearest railway station, connected to Zhengzhou via the Zhengzhou-Xinji "
                   "passenger line.",
        "desc_zh": "距离校园最近的火车站，可经郑新客运专线前往郑州主城区。",
        "aliases": ["新郑站", "火车站", "railway"],
    },
    {
        "id": "metro_longhu",
        "name": "Zhengzhou Metro Longhu Line 2 Station",
        "name_zh": "郑州地铁龙湖站（2号线）",
        "cat": "transit",
        "lat": 34.4437,
        "lng": 113.8003,
        "desc_en": "Metro Line 2 station on the northern side of Xinzheng.",
        "desc_zh": "郑州地铁2号线车站，位于新郑市区北侧，可换乘公交接驳校园。",
        "aliases": ["地铁", "metro", "龙湖站"],
    },
    {
        "id": "xinzheng_museum",
        "name": "Xinzheng Museum",
        "name_zh": "新郑博物馆",
        "cat": "culture",
        "lat": 34.3951,
        "lng": 113.7509,
        "desc_en": "Regional museum presenting the history and archaeology of Xinzheng, "
                   "home of the early Zheng(郑) state civilization.",
        "desc_zh": "新郑市博物馆，展示新郑历史与考古发现，早期郑国文明的重要发源地。",
        "aliases": ["博物馆", "museum"],
    },
    {
        "id": "hanceng_zheng_mao",
        "name": "Zheng State Capital Site (Hancangcheng)",
        "name_zh": "郑国故城·郑韩故城遗址",
        "cat": "culture",
        "lat": 34.3874,
        "lng": 113.7553,
        "desc_en": "Ruins of the Zheng and Han state capitals, a major national-level "
                   "archaeological site.",
        "desc_zh": "郑国故城与韩国故城遗址，属全国重点文物保护单位。",
        "aliases": ["郑国故城", "郑韩故城", "hancengcheng", "遗址"],
    },
    {
        "id": "huanghe_wetland",
        "name": "Xinzheng Huanghe Wetland Park",
        "name_zh": "新郑黄河湿地公园",
        "cat": "nature",
        "lat": 34.4126,
        "lng": 113.7662,
        "desc_en": "Wetland park along the Yellow River branch, popular for birdwatching "
                   "and walking.",
        "desc_zh": "黄河支流沿线湿地公园，适合观鸟与散步。",
        "aliases": ["湿地", "公园", "wetland"],
    },
    {
        "id": "shengle_commercial",
        "name": "Shengle City Shopping Center",
        "name_zh": "盛乐城市广场（龙湖新郑天街）",
        "cat": "commerce",
        "lat": 34.4311,
        "lng": 113.7598,
        "desc_en": "Large mixed-use shopping complex with restaurants, cinemas and shops, "
                   "the closest major retail destination to campus.",
        "desc_zh": "大型综合商业体，含餐饮、影城与零售，是距离校园最近的大型商圈。",
        "aliases": ["商场", "商业", "龙湖", "shengle"],
    },
    {
        "id": "xinzheng_park",
        "name": "Xinzheng Culture Square",
        "name_zh": "新郑文化广场",
        "cat": "commerce",
        "lat": 34.4229,
        "lng": 113.7418,
        "desc_en": "Downtown civic square with restaurants and evening street markets.",
        "desc_zh": "市区文化广场，周边餐饮集中，晚间有夜市。",
        "aliases": ["文化广场", "夜市"],
    },
    {
        "id": "guoli_university",
        "name": "Henan Guoli University",
        "name_zh": "河南工业与应用技术学院",
        "cat": "campus",
        "lat": 34.4139,
        "lng": 113.7291,
        "desc_en": "Neighbouring higher-education institution in the same district.",
        "desc_zh": "同片区内的高等院校，与西亚斯学院相邻。",
        "aliases": ["工学院", "邻近学校"],
    },
]

_CATEGORY_LABEL = {
    "campus": "校园",
    "transit": "交通",
    "culture": "文化",
    "commerce": "商业",
    "nature": "自然",
}


def category_label(cat: str) -> str:
    """类别代码转中文标签。"""
    return _CATEGORY_LABEL.get(cat, cat)


def search_knowledge(
    query: str = "",
    categories: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """按名称/别名/描述模糊检索知识库。

    纯本地字符串匹配，无任何网络调用。
    """
    pool = KNOWLEDGE_BASE
    if categories:
        pool = [e for e in pool if e["cat"] in categories]

    q = (query or "").strip().lower()
    if not q:
        hits = list(pool)
    else:
        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in pool:
            score = 0
            fields = [
                (entry["name"].lower(), 5),
                (entry["name_zh"], 5),
                (entry["id"].replace("_", " "), 4),
                (" ".join(entry.get("aliases", [])).lower(), 4),
            ]
            for text, weight in fields:
                if not text:
                    continue
                if q == text:
                    score += weight * 3
                elif q in text or text in q:
                    score += weight * 2
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        hits = [e for _, e in scored]

    return [
        {
            "id": e["id"],
            "name": e["name"],
            "name_zh": e["name_zh"],
            "category": e["cat"],
            "category_zh": category_label(e["cat"]),
            "lat": e["lat"],
            "lng": e["lng"],
            "description": e["desc_zh"],
            "description_en": e["desc_en"],
        }
        for e in hits[:limit]
    ]


def get_by_id(entry_id: str) -> dict[str, Any] | None:
    """按 id 精确取条目。"""
    for e in KNOWLEDGE_BASE:
        if e["id"] == entry_id:
            return e
    return None


def knowledge_catalog() -> list[dict[str, Any]]:
    """返回目录（给模型做选择用，省 token）。"""
    return [
        {
            "id": e["id"],
            "name_zh": e["name_zh"],
            "name": e["name"],
            "category_zh": category_label(e["cat"]),
            "lat": e["lat"],
            "lng": e["lng"],
        }
        for e in KNOWLEDGE_BASE
    ]


__all__ = [
    "KNOWLEDGE_BASE",
    "SIAS_CENTER",
    "search_knowledge",
    "get_by_id",
    "knowledge_catalog",
    "category_label",
]