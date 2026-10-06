# Meteorain_C4B_教学说明.md

> 怎么安装、怎么用这个技能。目标：**你读完就能自己生成一篇公众号文章。**

---

## 一、三分钟安装

### 第1 步：拿到技能

解压 `meteorain-wechat-publisher.zip`，你会看到：

```
meteorain-wechat-publisher/
├── SKILL.md                        ← 技能主文件
├── scripts/
│   ├── wechat_publisher.py         ← 转换器（你要跑的）
│   ├── eval_wechat_publisher.py    ← 37 条自检
│   └── starter_baseline.py         ← 原始版本（仅供对照）
├── references/
│   ├── wechat_restrictions.md      ← 公众号限制规则
│   └── starter_baseline_styles.md  ← 原始配色
└── examples/
    ├── sample_article.md           ← 官方示例
    └── demo_feature.md             ← 全功能演示
```

### 第 2 步：装依赖

```bash
pip install markdown beautifulsoup4 python-docx lxml
```

> 偷懒办法：**不用装。** 脚本第一次运行会自动安装缺失的包。

### 第 3 步：验证

```bash
python scripts/eval_wechat_publisher.py
```

期望看到最后一行：

```
passed 37 / 37
```

看到这行，说明环境没问题。如果不是 37，先看上面哪条 `[FAIL]`。

---

## 二、最短使用路径

```bash
python scripts/wechat_publisher.py article.md article.html
```

四步发布：

1. 浏览器打开 `article.html` 预览
2. 选中正文 → 复制
3. 打开 mp.weixin.qq.com → 新建图文 → 粘贴
4. 手机预览 → 发布

---

## 三、写文章：front matter

在 `.md` 文件开头写这段，标题/作者/摘要/日期会自动变成一个漂亮的元数据块：

```markdown
---
title: 我的文章标题
author:你的名字
date: 2026-10-06
abstract: 一句话摘要，会显示在标题下方的浅色框里。
---

# 正文开始
```

**注意**：写完 front matter 后，正文里不必再写一遍 `# 一级标题`。
元数据块已经承担了标题的作用。

不想用 front matter 也可以走命令行：

```bash
python scripts/wechat_publisher.py a.md a.html \
  --title "标题" --author "作者" --date "2026-10-06" --abstract "摘要"
```

---

## 四、Callout 高亮框（重点）

这是公众号排版最实用的功能。在引用块首行写标记：

```markdown
> [!NOTE] 可选标题
> 正文内容。

> [!WARNING] 注意
> 另一条提示。
```

支持的 8 种：

| 标记 | 图标 | 默认标题 | 典型用途 |
|------|------|---------|---------|
| `[!NOTE]` | 📖 | 笔记 | 补充说明 |
| `[!TIP]` | 💡 | 提示 | 实用技巧 |
| `[!INFO]` | ℹ️ | 信息 | 背景知识 |
| `[!WARNING]` | ⚠️ | 注意 | 容易出错的地方 |
| `[!IMPORTANT]` | ❗ | 重要 | 核心结论 |
| `[!CAUTION]` | 🚑 | 警告 | 有后果的操作 |
| `[!SUCCESS]` | ✅ | 完成 | 成果展示 |
| `[!QUOTE]` | 🗣️ | 引用 | 金句 |

**两个要点：**

1. `[!XXX]` 后面跟标题是可选的。不写就用默认标题（表格第3 列）。
2. **两个 callout 之间要空一行 `>`**，否则 Markdown 会把它们合并成一个引用块。
   （转换器会自动再拆开，但源码显式分隔更易读。）

### 对照示例

普通引用（无标记）保持原样：

```markdown
> 这里的 **加粗** 和 `代码` 都会保留。
```

→渲染为灰色引用条，**加粗和代码高亮都在**。

---

## 五、全部命令行参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--theme NAME` | `default` | 配色，见下表 |
| `--toc` | 关 | 自动生成目录（≥3 个标题才生成） |
| `--title` / `--author` / `--date` / `--abstract` | — | 覆盖 front matter |
| `--footer-copyright TEXT` | 自动 | 自定义页脚文字 |
| `--no-footer` | 关 | 不加页脚 |
| `--no-zh-spacing` | 关 | 关闭中英文自动空格 |
| `--batch` | 关 | 输入目录，批量转换所有 `.md` |
| `--fragment` | 关 | 只输出可粘贴的正文片段 |
| `--fragment-out PATH` | — | 额外导出一份纯片段 |

### 五套主题

| 名称 | 风格 | 适合 |
|------|------|------|
| `default` | 经典灰 | 通用，最稳妥 |
| `accent` | 学术蓝 | 技术教程、学术内容 |
| `minimal` | 极简黑 | 观点文章、随笔 |
| `solo` |暖橙 | 生活分享、轻松话题 |
| `dark` | 夜间黑 | 代码heavy的技术文章 |

```bash
python scripts/wechat_publisher.py a.md a.html --theme accent --toc
```

---

## 六、实战配方

### 技术教程（带代码）

```bash
python scripts/wechat_publisher.py tutorial.md out.html \
  --theme accent --toc --title "深度教程" --author "你的名字"
```

### 长文（需要目录）

```bash
python scripts/wechat_publisher.py long.md out.html --theme minimal --toc
```

### 一批文章一次转完

```bash
# posts/ 目录下所有 .md → out/
python scripts/wechat_publisher.py posts/ out/ --batch --theme accent
```

### 只要能粘贴的片段

```bash
# 同时得到预览页 + 纯片段
python scripts/wechat_publisher.py a.md preview.html --fragment-out paste.html
```

### 关闭中英文自动空格

```bash
python scripts/wechat_publisher.py a.md a.html --no-zh-spacing
```

---

## 七、输入格式支持

|格式 | 支持情况 |
|------|---------|
| `.md` | 完整支持：front matter、callout、代码块、表格、引用 |
| `.docx` | 支持：标题层级、段落、加粗/斜体、**表格** |
| `.html` | 重新清洗并套用样式 |
| 目录 | 配合 `--batch` |

**docx 说明**：Word 里第一个「标题 1」会被当作文章标题（不重复输出）。

---

## 八、常见问题

**Q：粘贴到公众号后样式乱了吗？**
A：先确认没贴错。预览页里的 `<body>` 外壳不要复制，只复制正文。
用 `--fragment` 导出的 `paste.html` 可以避免这个问题。

**Q：代码块显示成一堆挤在一起？**
A：这是 HTML 折叠换行的典型症状。用本技能的输出就不会有这个问题——
如果你遇到了，说明用的是旧版脚本。跑一下 eval 确认。

**Q：表格太宽，手机上显示溢出？**
A：公众号不支持横向滚动。把宽表格拆成两张窄表。

**Q：图片没显示？**
A：本地图片需要先上传到公众号素材库，再把 CDN 链接填回 `src`。
`data:image/png;base64` 可以直接用；SVG 会在保存后消失。

**Q：eval 报「themes produce distinct output」失败？**
A：说明有主题的配色写重复了。检查 `THEMES` 里每个主题的 token 是否有差异。

**Q：中文之间被加了空格，代码里也有？**
A：代码块和行内代码不受影响（脚本显式跳过了它们）。
如果正文里不想要，加 `--no-zh-spacing`。

---

## 九、扩展：加一套自己的主题

打开 `scripts/wechat_publisher.py`，找到 `THEMES`，复制一段改颜色：

```python
"mysite": {
    "label": "我的站点",
    "accent":     "#7c3aed",
    "heading":     "#5b21b6",
    "heading_bar": "#7c3aed",
    "text":        "#2d2d2d",
    "muted":       "#9a9a9a",
    "code_bg":     "#f5f3ff",
    "code_fg":     "#6d28d9",
    "quote_bar":   "#7c3aed",
    "quote_bg":    "#f5f3ff",
    "th_bg":       "#ede9fe",
    "link":        "#7c3aed",
    "divider":     "#ddd6fe",
},
```

**必须保留全部 12 个 key**，否则会在转换时抛 `KeyError`。

加完跑一次 eval，确认 5 主题那条断言仍然通过（你的新主题不会让它失败，
但如果你改动了现有主题，就会）。

---

## 十、给二次开发者的三条提示

如果你要在这个技能上继续改，这三个坑是我踩过的：

1. **处理顺序是有意义的。** `sanitize()` 里callout 转换**必须**在 blockquote
   转换之前，否则 `[!KIND]` 标记会被抹掉。

2. **不要用 `BeautifulSoup("<br/>")` 造标签。** lxml 会把它包成
   `<html><body>...`，你会往文章里塞进一整个嵌套文档。用 `soup.new_tag("br")`。

3. **不要提前 `html.escape()`。** 追加到 soup 时 parser 会再转义一次，
   `"` 会变成 `&amp;quot;`。追加裸 `NavigableString` 就行。

这三条都写进了 `SKILL.md`，也都有对应的 eval 断言。

---

## 十一、命令速查

```bash
# 最简
python scripts/wechat_publisher.py a.md a.html

# 技术长文
python scripts/wechat_publisher.py a.md a.html --theme accent --toc

# 批量
python scripts/wechat_publisher.py ./posts ./out --batch

# 自检（改代码后必跑）
python scripts/eval_wechat_publisher.py
```

---

*作者：Meteorain ｜ 版本：1.0 ｜ eval 37/37*
*技能包：meteorain-wechat-publisher.zip*