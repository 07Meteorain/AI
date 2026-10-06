---
title: 我用 AI 造了一个公众号排版技能，然后发现 starter kit 有两个致命 Bug
author: Meteorain
date: 2026-10-06
abstract: 拿到 starter kit 跑通只用了几分钟，但真正动手改它的时候才发现：代码块的缩进会消失，引用里的加粗会变 plain text。这篇文章记录这两个 bug 的根因、排查过程，以及最终沉淀下来的那条命令。
---

# 我用 AI 造了一个公众号排版技能，然后发现 starter kit 有两个致命 Bug

先说结论：**能跑通和能交付之间，隔着两个没人告诉你的Bug。**

这个故事的主角是一份 20KB 的开源代码包。我用它转换了一篇文章，浏览器打开，一切正常。看起来可以直接交差。

然后我打开生成的 HTML，一行一行看下去。

## 五分钟跑通，十分钟发现问题

starter kit 的主命令简单到不需要思考：

```bash
python scripts/convert_to_wechat.py article.md output.html
```

我照着跑了一遍，输出正常，提示正常。我甚至准备直接提交。

> [!NOTE] 转折点
> 我在检查输出时顺手看了一眼代码块——那个我以为一定会没问题的部分。
> 四行 Python，变成了一行。

## 坑一：代码块的缩进，会被 HTML 吃掉

先看我造出来的输入：

```python
def hello():
    print("line1")
    print("line2")
    return True
```

starter kit 转出来的 HTML 是这样：

```html
<p style="background-color: #f6f8fa; ...">def hello():
    print("line1")
    print("line2")
    return True
</p>
```

看起来完全正确——换行都在，缩进也在。

但实际渲染出来是这样：

def hello(): print("line1") print("line2") return True

**全部挤成了一行，缩进彻底消失。**

### 为什么会这样

因为 HTML 规范里有一条规则：`<p>` 标签内部的换行和连续空格，会被**折叠成单个空格**。这是 HTML 的正常行为，不是 bug。

而starter kit 生成代码块的代码是这样的：

```python
p = soup.new_tag("p")
p.string = code_text        # ← 把带 \n 的文本直接塞进 <p>
pre.replace_with(p)
```

换行符确实写进 HTML 文件了。但浏览器读到 `<p>` 的时候，二话不说给你折叠掉。

于是代码变成了「一整行看起来有换行的文本」。复制到公众号里，读者看到的就是一坨。

> 这件事的教训是：**转换器最容易出错的不是「少了功能」，而是「看起来能跑，其实悄悄改了语义」。**
> 生成 HTML 成功 ≠ 浏览器里显示正确。

### 我的解法

既然 `<p>` 不肯保留换行，那就别用换行，用 `<br/>`。这个标签在公众号里是被保留的。

```python
new_p.append(_br(soup))          # 换行
new_p.append(NavigableString(line))  # 这一行的内容
```

还有一个细节：**行首空格在 HTML 里也是被折叠的**。所以缩进必须单独处理——我把行首空格换成了不换行空格（U+00A0），这样视觉缩进才能活下来。

## 坑二：引用块里的加粗，会变成普通文字

第二个坑更隐蔽，因为它看起来是正常的。

我输入：

```markdown
> 这里的 **加粗** 和 `代码` 都会保留。
```

starter kit 转出来：

```html
<p style="background-color: #f9f9f9; ...">
引用里也有 加粗 和 代码。
</p>
```

`加粗` 还在，`代码` 还在。但**加粗没了，代码高亮也没了**。

原因在同一个函数习惯上：

```python
p = soup.new_tag("p")
p.string = bq.get_text()     # ← 只取纯文本，子节点全丢
bq.replace_with(p)
```

`get_text()` 会把整个子树拍平成一串纯文字。加粗标签、行内代码标签，在这一步全部被销毁。starter kit 的作者大概是想「换个容器包一下」，但顺手把内容也换掉了。

### 我的解法

不要重新造文本，而是**把原来的子节点搬到新容器里**：

```python
for child in list(bq.children):
    if isinstance(child, NavigableString):
        new_p.append(NavigableString(str(child)))
    else:
        new_p.append(child.extract())    # ← 原样搬过去，格式还在
```

改完之后，`**加粗**` 活下来了，`代码` 的红色背景也活下来了。

## 一个没料到的陷阱：BeautifulSoup 的分片解析

修完上面两个，我开始加 callout 功能。写了第一版，一跑——**callout 一个都没渲染出来**。

我打印了markdown 解析结果，发现两个 callout 居然合并成了一个 `<blockquote>`。我做了分割逻辑，还是不显示。继续打印，发现正则在第一步就匹配失败了：

```python
CALLOUT_RE = re.compile(r"^\[!([A-Za-z]+)\]\s*(.*)$")
```

问题出在 `(.*)$`。多行文本里 `.` 不匹配换行，但 `$` 在没有 `re.M` 的情况下匹配的是**整个字符串的末尾**——所以 `(.*)` 一口气吞掉了后面所有内容，标题和正文全被当成了标题。

改成这样才对：

```python
CALLOUT_RE = re.compile(r"^\[!([A-Za-z]+)\][ \t]*([^\n]*)")
```

用 `[^\n]*` 精确锁定「本行剩余部分」，标题才不会把正文吞掉。

> [!TIP] 一个更隐蔽的坑
> 修好正则之后，输出里出现了这种东西：
> `def demo():<html><body><br/></body></html> print("one")`
>
> 我是用 `BeautifulSoup("<br/>")` 来造换行标签的。
> lxml 解析器会把「一个裸片段」包进 `<html><body>`——于是我往文章里塞了一整个嵌套的 HTML 文档。
>
> 正确做法是 `soup.new_tag("br")`，它永远返回一个干净的裸标签。

顺带还有两个同源问题：

- 先 `html.escape()` 再塞进 soup，会被**二次转义**，`&quot;` 变成 `&amp;quot;`
- `<p>` 里不能再嵌套 `<p>`，所以 callout 这种「盒子」要用 `<section>` 而不是 `<p>`

## 我最后是怎么收口的

说实话，这三个 bug 都不是一开始就想到的。**它们是跑出来的，不是想出来的。**

所以我干了一件事：把所有踩过的坑都写成断言。

```python
check("BUG-1 fixed: code block keeps line breaks", "<br/>" in code)
check("BUG-1 fixed: indentation preserved", "    print" in code)
check("BUG-2 fixed: bold survives inside blockquote", ...)
check("no <p> nested directly inside <p>", ...)
```

第一次跑这个评测：**30 通过，6 失败**。

那6 个失败里，有 3 个是我以为早就修好了的。

## 为什么要写这个评测脚本

因为**「我试过了」和「我保证」是两件事**。

如果我只是手动转换一次、看一眼没问题就提交，这 6 个 bug 会有 5 个跟着我进入交付物。等到别人真正用它做技术文章的时候，代码块乱成一团——那时候再回来改，成本高得多。

> [!SUCCESS] 现在的状态
> 37 个断言，全部通过。
> 每一条都对应一个我真实踩过的坑，或者一项对外承诺的能力。
> 改了转换脚本就跑一遍，这个约束比任何review 都可靠。

## 从「脚本」到「技能」

跑通只花了几分钟。但从脚本变成一个别人能直接用的技能，中间还差几件事：

- 把样式参数抽成**主题**（现在有 5 套配色）
- 让**标题、作者、摘要**能从 front matter 自动读取
- 加**自动目录**（长文必备）
- 加**中文排版优化**（中英文之间自动补空格）
- 加**批量转换**（一次处理一整个文件夹）

这几件事本身都不难，难的是**意识到它们值得做**。

starter kit 的作者其实已经提示了这一点——它在 SKILL.md 里列了一张「本技能还不能做什么」的清单。光是认真读这一张清单，就能知道往哪里加。

## 写在最后

工具的价值不在于它多复杂，而在于它**让多少件麻烦事消失了**。

我在这件事上花的时间分布大概是：读 starter kit 5 分钟，写新增功能 40 分钟，**修 bug 90 分钟**。

比例有点反直觉，但我一点也不意外——因为那些 bug 都藏在「看起来能跑」的地方。

这也是我理解的 AI-First：不追求让 AI 替你干活，而是**让 AI 把重复劳动整个吞掉**，同时你自己守住「它到底对不对」这条线。

第一条命令是 AI 写的。但决定「这六个失败必须全部修完」的人，得是我自己。

---

*本文用 meteorain-wechat-publisher 技能转换而成。这个技能是从 C4B starter kit 改造的，评测脚本 37/37 通过。*