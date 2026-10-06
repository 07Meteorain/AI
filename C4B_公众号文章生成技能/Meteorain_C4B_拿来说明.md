# Meteorain_C4B_拿来说明.md

> 挑战要求：「从 starter kit 拿了什么、改了什么、为什么改」（评审权重 10%）。

---

## 一、我从 starter kit 拿了什么

starter kit 是一份 15KB 的压缩包，6 个文件，384 行 Python。
我**完整保留了 4 个文件**，只改了 1 个，另写 2 个。

| 文件 | 处理方式 | 理由 |
|------|---------|------|
| `references/wechat_restrictions.md` | **原样保留** | 平台限制是客观事实，没有重写的理由。改了反而会引入错误 |
| `references/wechat_styles.md` | 改名为 `starter_baseline_styles.md` 并保留 | 保留原配色，作为「新旧对比」的证据 |
| `examples/sample_article.md` | **原样保留** | 作为回归测试输入 |
| `scripts/convert_to_wechat.py` | **原样保留**，改名为 `starter_baseline.py` | 见下文，这是最重要的决定 |
| `scripts/convert_to_wechat.py` | 在其基础上新建 `wechat_publisher.py` | 加法而非重写 |
| `SKILL.md` | 完全重写 | 原文是starter 自述，不是我的技能说明 |

### 为什么保留 `starter_baseline.py`

这是我在整个C4B 里做的**最重要的一个决定**。

如果我直接改掉原脚本，那么「你到底修了什么 bug」就变成了一句无法验证的口头声明。
评审只能选择相信或不相信。

保留原脚本之后：

- eval 里有一条断言专门检查它仍可运行
- 文章里可以直接贴出「基线输出 vs 修复后输出」的对照
- 任何人想复核我的结论，跑一遍就行

**成本是多留了 400 行文件，收益是把主观声明变成了客观事实。**

---

## 二、我改了什么

### 2.1 修了两个真bug（不是新增功能，是修错）

这两个 bug 我事先完全不知道，是跑出来的。

#### BUG-1：代码块的换行和缩进会消失

**基线代码：**
```python
p = soup.new_tag("p")
p.string = code_text        # 带 \n 的文本直接塞进 <p>
pre.replace_with(p)
```

**为什么错**：HTML 规范规定 `<p>` 内的换行和连续空格会被**折叠成单个空格**。
换行符确实写进了 HTML 文件——用文本编辑器打开完全正常——但浏览器渲染时会被吃掉。

基线输出：
```html
<p style="background-color: #f6f8fa; ...">def hello():
    print("line1")
    return True
</p>
```

浏览器实际显示：
```
def hello(): print("line1") return True
```

**我的修法**：
```python
for i, line in enumerate(lines):
    if i:
        new_p.append(_br(soup))# <br/> 而非 \n
    stripped = line.lstrip(" ")
    indent = len(line) - len(stripped)
    new_p.append(NavigableString("\u00a0" * indent + stripped))
```

两个细节：
- 换行必须用 `<br/>`，因为它是公众号保留的标签
- 行首空格必须换成 U+00A0（不换行空格），因为普通空格在 HTML 里同样被折叠

顺带补了 `font-family: Menlo, Consolas, monospace` —— 基线**根本没给代码块设置等宽字体**。

#### BUG-2：引用块里的加粗和行内代码会丢失

**基线代码：**
```python
p = soup.new_tag("p")
p.string = bq.get_text()# 只取纯文本
bq.replace_with(p)
```

**为什么错**：`get_text()` 把整棵子树拍平成纯字符串。
输入 `> 引用里也有 **加粗** 和 \`代码\``，加粗标签和行内代码标签在这一步全被销毁。

实测对比：
```
基线：  引用里也有 加粗 和 代码。          ← 文字在，格式没了
修复后：引用里也有 <strong>加粗</strong> 和 <code>代码</code>  ← 都在
```

**我的修法**：
```python
for child in list(bq.children):
    if isinstance(child, NavigableString):
        new_p.append(NavigableString(str(child)))
    else:
        new_p.append(child.extract())    # 原样搬过去
```

**关键区别**：不重建文本，**搬运**节点。

### 2.2 新增七项能力

starter kit 在自己的 SKILL.md 里列了一张「本技能还不能做什么」的清单。
我认真读了这张表，按价值排序后决定做 7 项（挑战只要求 2 项）。

| # | 能力 | 难度 | 为什么值得做 |
|---|------|------|-------------|
| 1 | **主题系统**（5 套配色） | ★★ | 一篇文章一个样貌。`build_styles()` 全部从主题 token 派生，加新主题零成本 |
| 2 | **Callout 框**（8 种） | ★★ | 公众号排版的核心元素。「重点提示」比一大段文字有效得多 |
| 3 | **自动目录** | ★★ | 长文必备。少于 3 个标题时不生成，避免短文硬塞目录 |
| 4 | **文章元数据** | ★ | front matter 写一次，标题/作者/摘要/日期自动成块 |
| 5 | **页脚版权** | ★ | 实际发布必需。分隔线 + 版权声明，可自定义 |
| 6 | **中文排版优化** | ★★★ | 中英文之间自动补空格。这一项的「专业感提升」最明显 |
| 7 | **批量转换** | ★★ | `--batch` 一次处理整个目录，从「工具」变成「流水线」 |

**为什么做 7 项而不是 2 项**：因为 C4 的四条件里有一条是**可复用**——
「别人能直接用你的技能生成自己的文章」。只有两项能力时，别人还得自己补很多事。

### 2.3 顺手修掉的三个「自己挖的坑」

写 callout 时被 BeautifulSoup 咬了三次，这三个坑和starter kit 无关，是我自己的问题：

| 坑 | 错误写法 | 现象 | 正解 |
|----|---------|------|------|
| 分片被包壳 | `BeautifulSoup("<br/>")` | 输出里冒出 `<html><body><br/></body></html>` | `soup.new_tag("br")` |
| 二次转义 | 先 `html.escape()` 再 append | `&quot;` → `&amp;quot;` | 追加裸 `NavigableString`，让 parser 转义一次 |
| `<p>` 套 `<p>` | callout 用 `<p>` 当盒子 | 非法嵌套，公众号渲染错乱 | 盒子改用 `<section>` |

**这三个坑是 eval 抓出来的，不是我想出来的。**

---

## 三、我为什么这么改（决策理由）

### 3.1 加法，不是重写

starter kit 的 `ALLOWED_TAGS`、`FORBIDDEN_TAGS`、h1→h2、div→p 这些规则我**一行没动**。

理由：这些是**平台客观约束**，不是个人偏好。
改它们不会让文章变好看，只会让我引入 bug。

我的所有改动都发生在 `sanitize()` 内部的**顺序**上：

```python
_fix_code_blocks(soup, styles)
_convert_callouts(soup, styles)      # ← 必须在下一行之前
_fix_blockquotes(soup, styles)       # ← 这行会把 blockquote 变成 p
_flatten_inline(soup, styles)
```

**这个顺序是强制的，我第一版就写错了**：先做了 blockquote 转换，
callout 的 `[!KIND]` 标记就再也认不出来了。

### 3.2 让「主题」成为唯一配置源

我没有在代码里散落一堆颜色变量，而是收敛成 12 个 token：

```python
THEMES = {
    "accent": {"accent": "#1a73e8", "heading": "#0b57a4", ...},
}
def build_styles(t):   # 全部样式从 token 派生
```

**收益**：加一套新主题只要往 dict 里加一项，不用碰任何样式逻辑。
eval 里专门有一条断言检查 5 套主题输出**互不相同**——防止主题写了但没生效。

### 3.3 把「我试过了」变成「我保证」

这是我对 starter kit 最大的改造：不改代码，改**验收方式**。

starter kit 没有 eval。我写了 37 条断言，每一条都对应一个我真实踩过的坑：

```python
check("BUG-1 fixed: code block keeps line breaks", "<br/>" in code)
check("BUG-2 fixed: bold survives inside blockquote", ...)
check("no <p> nested directly inside <p>", ...)
```

**第一次跑：30 通过 / 6 失败。**

那 6 个失败里有 3 个是我「以为早就修好了」的。
所以我的结论是：**没有 eval 的「已完成」是不可信的。**

### 3.4 有一次我选择改测试，而不是改代码

eval 报「缩进丢失」，但我验证后发现：**代码是对的，断言是错的。**

代码用 U+00A0 保缩进是正确的（普通空格必然被折叠），
但断言在找 4 个普通空格。

这时候如果直接改代码让测试变绿，就是把技术债换个地方藏。
我的选择是**改断言**，并在 eval 里保留一句注释说明为什么。

> 这是整个C4B 过程里我最想记下来的一点：
> **测试失败时，先判断谁错了。**
> 盲目让测试变绿，和当初盲目相信「跑通了」是同一种错误。

---

## 四、拿来主义的边界

我**没有**拿走的东西，以及原因：

| 没拿 | 原因 |
|---|---|
| 重写整个转换器 | starter 的核心逻辑是对的，重写只会引入新 bug |
| 修改 `wechat_restrictions.md` | 平台限制是事实，改了会误导后来人 |
| 引入 LaTeX 公式渲染 | ★★★★ 难度，且我的文章无公式。加了就是「为炫技而加」 |
| 引入图片 CDN 上传 | 需要公众号 API 凭证，超出「一条命令能跑」的范围 |

**最后两条是主动放弃。** 挑战说「至少新增两项」，我没做的原因不是不会，
而是**做进去会让技能变重、变脆，且我这个场景用不上**。

判断标准是 C4B 自己给的那句话：
> 「你选择新增的能力应当让你的技能更好地满足四条件」

「可执行（一条命令就能跑）」比「功能多」优先级更高。

---

## 五、结果对照

| 维度 | starter kit | 我的版本 |
|------|-------------|---------|
| 代码块换行 | ✗ 渲染成一行 | ✓ `<br/>` 保留 |
| 代码块缩进 | ✗ 消失 | ✓ U+00A0 保留 |
| 代码块等宽字体 | ✗ 没设置 | ✓ Menlo/Consolas |
| 引用块内联格式 | ✗ 全部拍平 | ✓ 子节点搬运 |
| 主题数量 | 1套硬编码 | 5 套，可扩展 |
| Callout 框 | ✗ | 8 种类型 |
| 自动目录 | ✗ | ✓ |
| 元数据头 | ✗ | ✓ front matter 驱动 |
| 页脚版权 | ✗ | ✓ 可自定义 |
| 中文排版| ✗ | ✓ 中英文自动补空格 |
| 批量转换 | ✗ | ✓ `--batch` |
| docx 表格 | ✗ 只读段落 | ✓ 表格完整提取 |
| 自动化测试 | ✗ | 37 条断言 |
| 基线可复现 | — | ✓ 故意保留 |

---

## 六、一句话总结

starter kit 给了我一个**能跑的骨架**，但它有两个藏得很深的 bug，
和一份「本技能还不能做什么」的诚实清单。

我做的事是：**保留骨架、修掉 bug、按清单补齐能力、加一套机器验收。**

最有价值的产出不是那7 项能力，而是那 37 条断言——
因为它把「我觉得我修好了」变成了「每次跑都证明我修好了」。

---

*作者：Meteorain ｜ 日期：2026-10-06*
*所有对照结论均可用 `scripts/starter_baseline.py` 复现。*