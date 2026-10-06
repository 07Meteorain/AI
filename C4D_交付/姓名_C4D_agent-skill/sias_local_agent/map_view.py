"""交互式地图渲染：把 Agent 生成的地点数据渲染为 HTML。

地图合规说明
------------
按国内地图服务合规要求，本项目使用**腾讯地图GL JS**，
不使用 Google Maps / OpenStreetMap / Mapbox 等境外或未备案的瓦片源。
坐标系统一为 GCJ-02（火星坐标系）。

密钥策略
--------
默认走腾讯地图官方 `_TMapSecurityConfig` 密钥代理模式：
SDK 从官方 CDN 加载且**不带 key 参数**，请求经本地代理转发，
密钥保存在后端，前端不暴露任何密钥。

若需在自己的域名/环境使用自有密钥，请把下方 `KEY_PLACEHOLDER`
替换为你在腾讯位置服务控制台申请的密钥，并配置 Referer 白名单。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

# 自有密钥占位符（非默认场景使用；默认场景留空，走代理模式）
KEY_PLACEHOLDER = ""

# 类别配色（浅色主题下的对比色）
CATEGORY_STYLE: dict[str, dict[str, Any]] = {
    "campus": {"color": "#1a73e8", "zh": "校园", "icon": "🏫"},
    "transit": {"color": "#0b8043", "zh": "交通", "icon": "🚇"},
    "culture": {"color": "#a142f4", "zh": "文化", "icon": "🏛️"},
    "commerce": {"color": "#e8710a", "zh": "商业", "icon": "🛍️"},
    "nature": {"color": "#00838f", "zh": "自然", "icon": "🌳"},
}
DEFAULT_STYLE = {"color": "#5f6368", "zh": "其他", "icon": "📍"}

# 模型可能输出中文类别名，这里统一映射到内部代码
_CATEGORY_ALIAS = {
    "校园": "campus", "campus": "campus", "教育": "campus", "学校": "campus",
    "交通": "transit", "transit": "transit", "出行": "transit",
    "文化": "culture", "culture": "culture", "古迹": "culture", "历史": "culture",
    "商业": "commerce", "commerce": "commerce", "购物": "commerce",
    "自然": "nature", "nature": "nature", "公园": "nature", "景点": "nature",
}

CENTER = {"lat": 34.4016, "lng": 113.7361}


def _esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def _norm_categories(items: list[dict[str, Any]]) -> list[str]:
    return [str(i.get("category") or "campus") for i in items]


def normalize_locations(parsed: Any) -> list[dict[str, Any]]:
    """把模型输出整理成统一的地点结构。

    兼容多种模型输出形态：
      * {"locations": [...]} / {"pois": [...]} / {"places": [...]}
      * 直接是列表
      * 字段名可能是 latitude/lat、longitude/lng 等变体
    这个归一化层是必要的：4B 级别模型的字段命名不稳定，
    但数据结构本身是可靠的。
    """
    if isinstance(parsed, dict):
        for key in ("locations", "pois", "places", "items", "data", "results"):
            if isinstance(parsed.get(key), list):
                items = parsed[key]
                break
        else:
            # 形如 {"1": {...}, "2": {...}} 的字典
            vals = list(parsed.values())
            items = vals if vals and all(isinstance(v, dict) for v in vals) else []
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        lat = it.get("latitude", it.get("lat", it.get("Lat", it.get("y"))))
        lng = it.get("longitude", it.get("lng", it.get("lon", it.get("Lng", it.get("x")))))
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            continue
        cat = str(it.get("category") or it.get("cat") or "campus").strip()
        cat = _CATEGORY_ALIAS.get(cat.lower(), _CATEGORY_ALIAS.get(cat, "campus"))
        if cat not in CATEGORY_STYLE:
            cat = "campus"
        name_zh = it.get("name_zh") or it.get("nameZh") or it.get("chinese_name") or ""
        name_en = it.get("name_en") or it.get("nameEn") or it.get("name") or ""
        if not name_zh and not name_en:
            continue
        out.append(
            {
                "name_zh": _esc(name_zh or name_en),
                "name_en": _esc(name_en or name_zh),
                "description_zh": _esc(it.get("description_zh") or it.get("description") or ""),
                "description_en": _esc(it.get("description_en") or it.get("descriptionEn") or ""),
                "lat": lat,
                "lng": lng,
                "category": cat,
            }
        )
    return out


def build_map_html(
    locations: list[dict[str, Any]],
    title: str = "郑州西亚斯学院及周边 · 本地大模型 Agent 生成",
    subtitle: str = "",
    model_info: dict[str, Any] | None = None,
    run_info: dict[str, Any] | None = None,
) -> str:
    """生成自包含的交互式地图 HTML（腾讯地图 GL JS）。"""
    locs = locations or []
    cats = _norm_categories(locs)

    markers_js = json.dumps(
        [
            {
                "id": f"p{i+1}",
                "zh": l["name_zh"],
                "en": l["name_en"],
                "dz": l["description_zh"],
                "de": l["description_en"],
                "lat": l["lat"],
                "lng": l["lng"],
                "cat": l["category"],
                "icon": CATEGORY_STYLE.get(l["category"], DEFAULT_STYLE)["icon"],
                "color": CATEGORY_STYLE.get(l["category"], DEFAULT_STYLE)["color"],
            }
            for i, l in enumerate(locs)
        ],
        ensure_ascii=False,
    )

    legend_items = []
    used = sorted({c for c in cats if c in CATEGORY_STYLE})
    for c in used:
        st = CATEGORY_STYLE[c]
        n = sum(1 for x in cats if x == c)
        legend_items.append(
            f'<span class="lg"><i style="background:{st["color"]}"></i>'
            f'{st["icon"]} {st["zh"]} <b>{n}</b></span>'
        )
    legend_html = "".join(legend_items) or '<span class="lg">暂无数据</span>'

    # 证据条：满足挑战「截图需显示模型名/工具/设备/tok/s」的要求
    ev = model_info or {}
    chips = []
    if ev.get("model"):
        chips.append(("模型", ev["model"]))
    if ev.get("runtime"):
        chips.append(("运行方式", ev["runtime"]))
    if ev.get("device"):
        chips.append(("设备", ev["device"]))
    if ev.get("tok_per_second"):
        chips.append(("推理速度", f"{ev['tok_per_second']} tok/s"))
    if ev.get("tool_calls") is not None:
        chips.append(("工具调用", f"{ev['tool_calls']} 次"))
    if ev.get("generated_at"):
        chips.append(("生成时间", ev["generated_at"]))
    chips_html = "".join(
        f'<span class="chip"><label>{_esc(k)}</label>{_esc(v)}</span>'
        for k, v in chips
    )

    run = run_info or {}
    run_html = ""
    if run:
        run_html = (
            '<details class="run"><summary>Agent 执行轨迹'
            f"（{_esc(run.get('tool_calls', 0))} 次工具调用 / "
            f"{_esc(run.get('total_tokens', 0))} tokens / "
            f"{_esc(run.get('total_seconds', 0))}s）</summary>"
            f"<pre>{_esc(run.get('trace', ''))}</pre>"
            '<p class="tip">所有数据均由本地模型生成，轨迹可完整复现；'
            "坐标取自随技能分发的本地知识库以避免幻觉。</p></details>"
        )

    key_cfg = ""
    if KEY_PLACEHOLDER:
        key_cfg = (
            '<script type="text/javascript">'
            "window._TMapSecurityConfig = {"
            f'serviceHost: "{KEY_PLACEHOLDER}"'
            "};</script>"
        )
    else:
        # 默认场景：官方密钥代理模式，SDK 不带 key 参数
        key_cfg = (
            '<script type="text/javascript">'
            "window._TMapSecurityConfig = {"
            "serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__'"
            "};</script>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; padding:0; height:100%; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", sans-serif;
    color:#1f2328; background:#f6f7f9;
  }}
  #map {{ position:absolute; inset:0; }}
  .panel {{
    position:absolute; z-index:500; background:rgba(255,255,255,.96);
    border:1px solid #e3e5e8; border-radius:12px;
    box-shadow:0 6px 24px rgba(16,24,40,.10);
  }}
  #head {{ top:16px; left:16px; right:16px; max-width:520px; padding:14px 16px; }}
  #head h1 {{ margin:0 0 4px; font-size:17px; line-height:1.35; }}
  #head .sub {{ margin:0 0 10px; font-size:12px; color:#5f6368; line-height:1.5; }}
  #legend {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }}
  .lg {{ font-size:12px; color:#3c4043;
        background:#f1f3f4; padding:3px 9px; border-radius:999px; }}
  .lg i {{ display:inline-block; width:9px; height:9px; border-radius:50%;
          margin-right:6px; vertical-align:middle; }}
  #chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .chip {{ font-size:11px; background:#e8f0fe; color:#174ea6;
          padding:3px 8px; border-radius:6px; white-space:nowrap; }}
  .chip label {{ color:#5f6368; margin-right:5px; }}
  #side {{ top:calc(16px + var(--headh, 150px)); left:16px; width:300px;
          max-height:44vh; overflow:auto; padding:12px 14px; }}
  #side h2 {{ margin:0 0 8px; font-size:13px; color:#5f6368;
             text-transform:uppercase; letter-spacing:.4px; }}
  .item {{ padding:8px 0; border-bottom:1px solid #eceef0; cursor:pointer; }}
  .item:last-child {{ border-bottom:0; }}
  .item:hover .nm {{ color:#1a73e8; }}
  .item .nm {{ font-size:13px; font-weight:600; }}
  .item .nm span {{ font-weight:400; color:#5f6368; font-size:11px;
                   margin-left:6px; }}
  .item .ds {{ font-size:11.5px; color:#5f6368; margin-top:3px;
              line-height:1.5; }}
  .item .co {{ font-size:10.5px; color:#80868b; margin-top:3px;
             font-family:ui-monospace,Menlo,Consolas,monospace; }}
  .run {{ padding:12px 14px; bottom:16px; left:16px; right:16px;
         max-width:640px; max-height:34vh; overflow:auto; font-size:12px; }}
  .run summary {{ cursor:pointer; font-weight:600; color:#174ea6; }}
  .run pre {{ white-space:pre-wrap; font-size:11px; color:#3c4043;
             background:#f8f9fa; padding:10px; border-radius:8px;
             overflow:auto; margin:8px 0 0; }}
  .tip {{ font-size:11px; color:#80868b; margin:6px 0 0; }}
  .fallback {{ padding:20px; font-size:13px; }}
  @media (max-width:720px) {{
    #head {{ right:16px; }} #side {{ display:none; }}
  }}
</style>
{key_cfg}
<script src="https://map.qq.com/api/gljs?v=1.exp&libraries=service"></script>
</head>
<body>
<div id="map"></div>

<div class="panel" id="head">
  <h1>{_esc(title)}</h1>
  <p class="sub">{_esc(subtitle or '数据由本地运行的 Gemma 4 模型经工具调用与结构化输出生成，未调用任何云端 LLM API。')}</p>
  <div id="legend">{legend_html}</div>
  <div id="chips">{chips_html}</div>
</div>

<div class="panel" id="side">
  <h2>地点清单（{len(locs)}）</h2>
  <div id="list"></div>
</div>

{run_html}

<script>
const LOCS = {markers_js};
const CENTER = {json.dumps(CENTER)};
const STYLES = {json.dumps(CATEGORY_STYLE, ensure_ascii=False)};

function esc(s){{ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function fail(msg){{
  document.getElementById('map').innerHTML =
    '<div class="fallback"><b>地图底图加载失败</b><p>' + esc(msg) + '</p>' +
    '<p>标记数据仍可在下方清单查看。若在 WorkBuddy 预览面板中打开，' +
    '请确保已启用腾讯地图密钥代理；否则请在 <code>map_view.py</code> 中' +
    '配置自有密钥后重新生成。</p></div>';
}}

// ---------- 侧边清单 ----------
const list = document.getElementById('list');
list.innerHTML = LOCS.map((p, i) => `
  <div class="item" data-i="${{i}}">
    <div class="nm">${{p.icon}} ${{esc(p.zh)}}<span>${{esc(p.en)}}</span></div>
    <div class="ds">${{esc(p.dz)}}</div>
    <div class="co">${{p.lat.toFixed(6)}}, ${{p.lng.toFixed(6)}}</div>
  </div>`).join('');

// ---------- 地图初始化 ----------
if (typeof TMap === 'undefined') {{
  fail('腾讯地图 GL JS SDK 未加载成功（可能是网络限制）。');
}} else {{
  try {{
    const map = new TMap.Map('map', {{
      center: new TMap.LatLng(CENTER.lat, CENTER.lng),
      zoom: 14,
      pitch: 0
    }});

    const styles = {{}};
    LOCS.forEach(p => {{
      styles[p.id] = new TMap.MarkerStyle({{
        width: 26, height: 34,
        anchor: {{x: 13, y: 34}},
        color: '#ffffff',
        src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
          '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="34">' +
          '<path d="M13 0C5.8 0 0 5.6 0 12.5 0 21.5 13 34 13 34s13-12.5 13-21.5C26 5.6 20.2 0 13 0z" ' +
          'fill="' + p.color + '" stroke="#fff" stroke-width="1.5"/>' +
          '<text x="13" y="18" font-size="12" text-anchor="middle" fill="#fff">' +
          '${{p.icon}}</text></svg>')
      }});
    }});

    const markers = new TMap.MultiMarker({{
      map: map,
      styles: styles,
      geometries: LOCS.map((p, i) => ({{
        id: p.id, styleId: p.id,
        position: new TMap.LatLng(p.lat, p.lng),
        properties: {{ title: p.zh, index: i }}
      }}))
    }});

    markers.on('click', (evt) => {{
      const p = LOCS.find(x => x.id === evt.geometry.id);
      if (!p) return;
      const info = new TMap.InfoWindow({{
        position: new TMap.LatLng(p.lat, p.lng),
        content: '<div style="padding:10px 12px;max-width:280px;font-size:13px">' +
          '<b>' + p.icon + ' ' + esc(p.zh) + '</b><br>' +
          '<span style="color:#5f6368;font-size:11.5px">' + esc(p.en) + '</span><br>' +
          '<span style="font-size:11.5px">' + esc(p.dz) + '</span>' +
          (p.de ? '<br><span style="font-size:11px;color:#5f6368;font-style:italic">' +
                 esc(p.de) + '</span>' : '') +
          '<br><span style="font-size:10.5px;color:#80868b;font-family:monospace">' +
          p.lat.toFixed(6) + ', ' + p.lng.toFixed(6) + '</span></div>'
      }});
      map.setInfoWindow(info);
    }});

    // 视野自适应到所有标记
    const bounds = new TMap.LatLngBounds();
    LOCS.forEach(p => bounds.extend(new TMap.LatLng(p.lat, p.lng)));
    map.fitBounds(bounds, {{ padding: 90 }});

    // 清单点击联动
    list.addEventListener('click', (e) => {{
      const item = e.target.closest('.item');
      if (!item) return;
      const p = LOCS[+item.dataset.i];
      map.setCenter(new TMap.LatLng(p.lat, p.lng));
      map.setZoom(16);
      const info = new TMap.InfoWindow({{
        position: new TMap.LatLng(p.lat, p.lng),
        content: '<div style="padding:10px 12px;max-width:280px;font-size:13px">' +
          '<b>' + p.icon + ' ' + esc(p.zh) + '</b><br>' +
          '<span style="color:#5f6368;font-size:11.5px">' + esc(p.en) + '</span><br>' +
          '<span style="font-size:11.5px">' + esc(p.dz) + '</span></div>'
      }});
      map.setInfoWindow(info);
    }});

    window.__mapReady = true;
  }} catch (err) {{
    fail(String(err));
  }}
}}
</script>
</body>
</html>
"""


def save_map(html_text: str, out_path: str | Path) -> Path:
    """写出地图 HTML 文件（UTF-8，无 BOM）。"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_text, encoding="utf-8")
    return p


__all__ = [
    "build_map_html",
    "normalize_locations",
    "save_map",
    "CATEGORY_STYLE",
    "CENTER",
    "KEY_PLACEHOLDER",
]