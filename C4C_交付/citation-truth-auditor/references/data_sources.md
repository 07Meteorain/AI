# Data Sources — 数据源与 API 细节

> 供扩展或调试 `citation_auditor.py` 时查阅。
> 三个源均为**免费、无需 API key**、允许非商业使用。
> 传递 `User-Agent`（含邮箱）是学术 API 的通行礼仪，也降低限流概率。

---

## 1. Crossref — DOI 权威注册机构

**用途：** DOI 精确查询（置信度最高的一条路径）。
**基址：** `https://api.crossref.org`

### 按 DOI 查

```
GET https://api.crossref.org/works/{doi}?mailto={email}
```

实测响应（`10.1038/nature14539`）字段：

```jsonc
{
  "message": {
    "DOI": "10.1038/nature14539",
    "title": ["Highly accurate protein structure prediction with AlphaFold"],
    "author": [ { "given": "John", "family": "Jumper" }, ... ],
    "container-title": ["Nature"],
    "issued":  { "date-parts": [[2021, 8]] },
    "is-referenced-by-count": 23000
  }
}
```

审计器读取：`title`、`issued.date-parts[0][0]`→年份、`author[].family/given`、
`container-title`→venue、`is-referenced-by-count`→引用量。

### 按标题搜

```
GET https://api.crossref.org/works?query.bibliographic={title}&rows=3&mailto={email}
```

- `query.bibliographic` 比 `query.title` 更宽松，适合标题较长的情形。
- 必须限制 `rows`，取回全部再本地打分会引入大量噪声。
- 附带 `_sim` 字段 = 本地标题相似度（脚本计算，非API 返回）。

### 已知限制

| 情况 | 表现 |
|---|---|
| 书籍、学位论文、技术报告 | 多数无DOI，检索不到 |
| 无 DOI 的会议论文 | 检索不到（Crossref 只覆盖已注册 DOI 的出版物） |
| CS/数学预印本 | 通常无 DOI，需走 arXiv |
| `10.5555/...`（ACM）前缀 | **Crossref 返回 404**，但该 DOI 在出版社侧有效 → 见"版本漂移" |
| `10.48550/arxiv.*`（arXiv/DataCite）前缀 | **Crossref 查不到** → 脚本已改为直接路由到 arXiv 精确查询 |
| 单条请求偶发 5xx | 脚本指数退避重试 |

> **关键规律**：**DOI 前缀决定了该查哪个库。** Crossref 只覆盖 Crossref 注册的
> 前缀；arXiv 自己的 `10.48550` 前缀、ACM 的 `10.5555` 前缀都不在其中。
> 把所有 DOI 都丢给 Crossref 会产生系统性漏检。

---

## 2. arXiv — 预印本精确查询

**用途：** 预印本 ID 直查，是命中率最高、最干净的路径。
**基址：** `https://export.arxiv.org/api/query`

```
GET https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1
```

**必须带 `User-Agent`**，否则返回 **HTTP 403**（实测：curl 默认 UA 被拒，
带 UA 的请求正常返回 200）。

返回 Atom XML，审计器用 `xml.etree` 解析：

```xml
<entry>
  <title>Attention Is All You Need</title>
  <published>2017-06-12T00:00:00Z</published>
  <author><name>Ashish Vaswani</name></author>
  ...
</entry>
```

注意：arXiv 的 `<title>` 常含换行，脚本用 `.replace("\n", " ")` + `strip()` 清理。
作者为 `First Last` 形式（与 BibTeX 的 `Last, First` 相反），由`_surname()` 统一处理。

### arXiv ID 格式

`YYMM.NNNNN`（2007 年至今5 位）或旧式 `math.GT/0309136`。
脚本从 `eprint`、`archivePrefix`、`url`、`note` 字段以及原始文本中提取。

---

## 3. OpenAlex — 覆盖面最广的开放图谱

**用途：** Crossref 查不到时的兜底，覆盖期刊/预印本/图书/学位论文。
**基址：** `https://api.openalex.org`

```
GET https://api.openalex.org/works?filter=title.search:{title}&per-page=3&mailto={email}
```

实测响应的关键字段（注意层级很深）：

```jsonc
{
  "results": [{
    "title": "Attention Is All You Need",
    "publication_year": 2025,          // ← 可能是重印/重新索引的年份
    "cited_by_count": 26826,
    "doi": "https://doi.org/10.65215/2q58a426",   // ← 需去掉 https://doi.org/ 前缀
    "authorships": [ { "author": { "display_name": "Ashish Vaswani" } }, ... ],
    "primary_location": {
      "source": { "display_name": "arXiv" },       // ← 可能为 null
      "landing_page_url": "https://..."
    }
  }]
}
```

### OpenAlex 的坑

1. **`publication_year` 未必是首发年份。** 实测检索 "Attention Is All You Need"
   返回的首条记录 `publication_year` 为 **2025**，而论文实际发表于 2017。
   原因：OpenAlex 会合并同一著作的多个版本（预印本 + 会议版 + 修订版），
   主记录的年份可能来自任一版本。
   → 审计器把 bib 中的年份作为**先验**参与候选排序，正是为了压制这个问题。

2. **`primary_location.source` 可能为 `null`**，取值时必须容错。

3. **`doi` 字段带 URL 前缀**，需 `replace("https://doi.org/", "")`。

4. **覆盖极广**，常见标题可返回数百条结果（实测 254），因此必须限制
   `per-page` 并在本地排序。

---

## 4. 未收录的文献类型（重要）

Crossref / arXiv / OpenAlex 是**学术**三库。下列类型**查不到是预期行为**，
不是引用不存在，脚本已将此类判为 `UNCHECKED` 而非 `FABRICATED`：

| 类型 | 识别关键词 |
|---|---|
| 软件参考手册 / 用户指南 | `reference manual`, `user guide`, `handbook` |
| 技术文档 / 教程 | `documentation`, `getting started`, `教程`, `手册` |
| 内部标准 / 规范 | `standard`, `specification` |
| 技术报告 | `technical report` |
| 中文期刊 | 三库对中文文献收录都很少 |
| 学位论文、会议幻灯、讲座录像 | 通常无持久标识符 |

> 实测：本技能审计 C2 交付的 17 条已核验文献时，唯一一条 `UNCHECKED`
> 是《The Coq Proof Assistant Reference Manual》——软件手册，
> 三个库都不收录。**判 `UNCHECKED` 是正确处理，判 `FABRICATED` 是误伤。**

---

## 5. 未采用的源：Semantic Scholar

代码中**保留**了对 Semantic Scholar 的调用位置，但默认不在查询链中。

实测：匿名请求返回
```json
{"message": "Too Many Requests. Please wait and try again or apply for a key...",
 "code": "429"}
```
无API key 时限流严重，且配额因IP 而异。

**若要启用：** 申请免费 key，在请求头加 `x-api-key`，
并显著降低并发（建议 `--jobs 1`）以免触发限流。
其优势是覆盖面好且提供 `externalIds`（同时含DOI 与 arXiv ID），适合做交叉验证。

---

## 6. 查询链路与降级

审计器按**快速路径优先**的顺序执行，任一路径成功即短路：

```
1. bib 中有 DOI？  → Crossref /works/{doi}
        │失败
        ▼
2. bib 中有 arXiv ID？ → arXiv /query?id_list=
        │失败 或 相似度不足
        ▼
3. 标题检索 → Crossref + OpenAlex 并发
        │
        ▼
   候选集为空 → 依据幻觉指纹定FABRICATED / UNCHECKED
```

**网络容错**（`http_get`）：

| 情况 | 行为 |
|---|---|
| HTTP 429 / 5xx | 指数退避重试（1.5s、3s），最多 2 次 |
| HTTP 4xx（除429） | 立即放弃该源，不重试 |
| 超时 / 连接错误 | 退避后重试 |
| 全部源失败 | 降级为指纹判定，**绝不臆造**结论 |

**限流礼仪**：`--jobs` 默认 4。条目很多（>50）时建议降到 2，避免被限流。

---

## 7. 扩展：新增一个数据源

实现一个返回候选 dict 的函数，并在 `audit_entry` 中加入 `candidates`：

```python
def query_mysource_by_title(title, timeout, rows=3):
    """返回候选列表，每项须包含：source/title/year/authors/venue/doi/url，
    并附带本地算出的 _sim 字段。返回 None 表示该源不可用。"""
    url = f"https://example.org/search?title={q(title)}"
    data = http_get(url, timeout)
    if not data:
        return None
    try:
        items = json.loads(data).get("items", [])
    except Exception:
        return None
    out = []
    for m in items:
        t = m.get("name") or ""
        if not t:
            continue
        out.append({
            "source": "MySource", "title": t, "year": m.get("yr"),
            "authors": m.get("authors", [])[:12],
            "venue": m.get("venue", ""), "doi": m.get("doi", ""),
            "url": m.get("link", ""), "cited_by": m.get("cites"),
            "_sim": title_sim(title, t),      # ← 必须，排序依赖它
        })
    return out
```

**候选 dict 字段约定：**

| 字段 | 必需 | 说明 |
|---|---|---|
| `source` | ✅ | 数据源名，会打印在报告里 |
| `title` | ✅ | 用于相似度计算 |
| `authors` | ✅ | 字符串列表，用于姓氏匹配 |
| `_sim` | ✅ | 与 bib 标题的相似度 0~1 |
| `year` / `venue` / `doi` / `url` / `cited_by` | 可选 | 缺失时降级处理 |

接入后无需改动排序与判定逻辑——`rank()` 与判定阈值只依赖上述字段。