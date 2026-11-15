"""把卡组导出成一个**可以 file:// 直接打开**的静态站点。

为什么坚持 file://：目标用户是学生，不是 DevOps。
「装个 Python、再 cd、再跑 serve」足以让一半人放弃；而 `recall web` 之后
双击 index.html 就能复习，且数据不出本机。

代价是浏览器对 file:// 的 fetch 限制——所以卡组不是 JSON 文件，
而是写进 `deck.js` 的 `window.RECALL_DECK`。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import __version__
from .scheduler import golden_vectors
from .store import export_payload

ASSETS = Path(__file__).resolve().parent / "assets"


def _js_assign(name: str, payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 防止卡片正文里出现 </script> 提前闭合标签
    text = text.replace("</", "<\\/")
    return "window.{} = {};\n".format(name, text)


def render_site(
    conn,
    out_dir: str,
    status: Optional[str] = "approved",
    title: str = "Recall",
) -> Dict[str, object]:
    payload = export_payload(conn, status=status)
    payload["app_version"] = __version__
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name in ("index.html", "styles.css", "lib.js", "app.js", "selftest.html", "selftest.js"):
        source = ASSETS / name
        if not source.is_file():
            raise FileNotFoundError("缺少前端资源：{}".format(source))
        shutil.copyfile(str(source), str(out / name))

    (out / "deck.js").write_text(_js_assign("RECALL_DECK", payload), encoding="utf-8")
    (out / "vectors.js").write_text(_js_assign("RECALL_VECTORS", golden_vectors()), encoding="utf-8")

    index = out / "index.html"
    html = index.read_text(encoding="utf-8")
    html = html.replace("<title>Recall</title>", "<title>{}</title>".format(title))
    index.write_text(html, encoding="utf-8")

    return {
        "out": str(out),
        "cards": len(payload["cards"]),
        "status": status or "all",
        "index": str(index),
    }


def default_site_dir(base: str = ".") -> str:
    return os.path.join(base, "site")
