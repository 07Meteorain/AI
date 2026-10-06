# Meteorain_C4B_公众号文章生成技能

> C4B挑战交付物 ｜ 作者：Meteorain ｜ 日期：2026-10-06
> 从 starter kit 改造的个人公众号文章生成技能，eval **37/37** 通过。

---

## 这个文件夹里有什么

```
Meteorain_C4B_公众号文章生成技能/
│
├── meteorain-wechat-publisher/          ← 技能本体
│   ├── SKILL.md                技能主文件
│   ├── scripts/
│   │   ├── wechat_publisher.py         转换器（主程序）
│   │   ├── eval_wechat_publisher.py    37 条自检断言
│   │   └── starter_baseline.py         starter 原版（对照用，未改动）
│   ├── references/
│   │   ├── wechat_restrictions.md      公众号限制规则
│   │   └── starter_baseline_styles.md  starter 原配色
│   └── examples/
│       ├── sample_article.md           官方示例
│       └── demo_feature.md             全功能演示
│
├── meteorain-wechat-publisher.zip       打包好的技能（可直接分发）
│
├── Meteorain_C4B_文章源文件.md          文章 Markdown 原文
├── Meteorain_C4B_output.html            转换后的公众号 HTML（预览版）
├── Meteorain_C4B_粘贴片段.html          纯正文片段（粘贴用）
│
├── Meteorain_C4B_AI日志.md              ★ skill-creator 全流程记录
├── Meteorain_C4B_拿来说明.md            ★拿了什么/改了什么/为什么
├── Meteorain_C4B_教学说明.md            安装与使用手册
├── Meteorain_C4B_文章链接.md            发布状态 + 发布 SOP
└── Meteorain_C4B_AAR复盘.md             行动后复盘（含失败经验）
```

带 ★ 的是挑战指定的必交文件。

---

## 快速开始

```bash
# 1. 装依赖（也可跳过，脚本会自动装）
pip install markdown beautifulsoup4 python-docx lxml

# 2. 自检
cd meteorain-wechat-publisher
python scripts/eval_wechat_publisher.py        # 期望 passed 37 / 37

# 3. 转换
python scripts/wechat_publisher.py 文章.md 输出.html --theme accent --toc
```

浏览器打开 `输出.html` → 复制正文 → 粘贴到 mp.weixin.qq.com → 发布。

详细说明见 **`Meteorain_C4B_教学说明.md`**。

---

## 我做了什么

### 修了 starter kit 的两个真 bug

两个都是跑出来的，不是读代码看出来的。

| Bug | 现象 | 根因 |
|-----|------|------|
| BUG-1 | 代码块渲染成一行，缩进消失 | `p.string = code_text` 把 `\n` 写进 `<p>`，HTML 会折叠它 |
| BUG-2 | 引用块里的加粗/行内代码变纯文本 | `p.string = bq.get_text()` 拍平了整棵子树 |

### 新增 7 项能力

主题系统（5 套）· Callout 框（8 种）· 自动目录 · 文章元数据 ·
页脚版权 · 中文排版优化 · 批量转换

挑战只要求 2 项。

### 加了 37 条断言

```
passed 37 / 37
```

**第一次跑是 30/37。** 那 6 个失败里有 3 个是我以为早就修好的。

---

## 三个值得记住的坑

1. **`BeautifulSoup("<br/>")` 会返回 `<html><body><br/></body></html>`**——
   lxml 把裸片段包了一层，塞进文章里就是嵌套文档。用 `soup.new_tag("br")`。

2. **先 `html.escape()` 再 append 会二次转义**——`"` 变成 `&amp;quot;`。
   追加裸 `NavigableString`，让 parser 转义一次。

3. **测试失败时先判断谁错了。** 有一次是断言错了（找普通空格，
   但正确方案必须用 U+00A0）。让测试变绿不是目标，代码正确才是。

---

## 验证状态

| 项目 | 状态 |
|------|------|
| eval 断言 | ✅ 37 / 37 |
| starter 基线仍可运行 | ✅ 有专门断言 |
| 公众号合规（无 script/style/div/class/h1） | ✅ 已验证 |
| skill-creator validator | ✅ 通过 |
| 文章转换 | ✅ 30 KB 输出 |
| 公众号账号发布 | ⏳ **未完成**（无账号，见 `文章链接.md`） |

最后一项是已知缺口，不隐瞒。

---

## 必读文件

| 文件 | 什么时候看 |
|------|-----------|
| `Meteorain_C4B_拿来说明.md` | 想知道我改了什么、为什么 |
| `Meteorain_C4B_AI日志.md` | 想知道 skill-creator 怎么用的、踩了哪些坑 |
| `Meteorain_C4B_AAR复盘.md` | 想看含失败经验的复盘 |
| `Meteorain_C4B_教学说明.md` | 想自己用这个技能 |

---

*所有技术结论可用 `scripts/starter_baseline.py` 复现。*
*作者：Meteorain ｜ 技能包：meteorain-wechat-publisher.zip*