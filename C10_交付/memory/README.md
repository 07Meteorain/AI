# memory/ · 记忆库

> 这个目录**既是运行产物，也是交付证据**。
> 里面躺着一次真实演示留下的 35 条记忆、14 条运行记录、1 组同义词、3 条进化事件。
> 评审者不必先跑一遍代码，就能打开看"它到底记了什么、怎么找回来"。

---

## 目录

```text
memory/
├── db/
│   ├── k.jsonl              知识层（4 条）
│   ├── s.jsonl              情境层（15 条）
│   ├── t.jsonl              任务层（1 条）
│   ├── ar.jsonl             行动-反思层（15 条）
│   ├── aliases.json         同义词表（1 组：打分规则 → 检索/索排/排序）
│   ├── evolution.jsonl      进化审计日志（系统改了自己什么）
│   ├── skill_usage.jsonl    技能调用账本
│   └── traces/
│       └── 2026-11-15.jsonl 当天 14 次运行的完整 trace
├── knowledge/               知识层的 Markdown 镜像（人可读、可 diff）
│   ├── INDEX.md             自动生成的目录
│   └── k-*.md               每条 K 记录一个文件
├── reviews/                 周复盘报告（weekly-review 技能产出）
│   └── 2026-W46.md
└── README.md                本文件
```

---

## 怎么读

```bash
# 人读：知识层镜像
cat memory/knowledge/INDEX.md

# 人读：一次运行的完整 trace（想看懂"它为什么这么答"就看这个）
python -m brain trace -n 3
python -m json.tool < /dev/null  # 或者直接看 jsonl 的一行

# 机读：任何一行都是独立 JSON
head -c 400 memory/db/ar.jsonl

# 看它改了自己什么
cat memory/db/evolution.jsonl
```

一行记录长这样（`ar.jsonl`）：

```json
{"id":"ar-20261115-7c3f2a","layer":"AR","title":"review：周复盘",
 "text":"意图 review（命令行 review）｜输入：周复盘｜执行 3 步（成功 3）｜结果：…",
 "created":"2026-11-15T16:09:24+08:00","updated":"…","tags":["review","ok"],
 "source":"run-20261115-…","importance":0.55,"status":"ok","hits":6,
 "meta":{"intent":"review","workflow":"memory.search>skill.run>memory.promote",
         "steps":["memory.search","skill.run","memory.promote"],"ok":true,"echo":false}}
```

关键字段：

- `workflow` —— 工具调用序列，**技能固化只认它**；
- `echo` —— 是否"问句回声"（`recall`/`chat` 的存档，默认不参与检索）；
- `source` —— 溯源：哪次运行 / 哪个技能 / 哪个人写的；
- `hits` —— 被找回过的次数（沉淀与归档的依据）。

---

## 怎么重建

```bash
cd C10_交付
python demo/run_demo.py        # 会清空 db/knowledge/reviews 与 skills/_drafts 后重放
```

演示脚本可复现的保证：清库 → 固定顺序执行 14 个场景 → 写 `demo/终端实录.txt`。
因为 id 里带时间和随机尾巴，**重建后的 id 会变**，但结构、条数、分数关系一致。

---

## 注意

1. **`knowledge/*.md` 是单向镜像**：程序只读 JSONL；手改 md 不会回写。
   要改记忆，用 `python -m brain capture` 或直接改 `db/*.jsonl`（改完重启即重建索引）。
2. **不要在两个进程里同时写**：追加安全、更新会互相覆盖。
3. **本目录不含任何隐私数据**：演示内容是项目自身的结论与流程。
4. **删掉也能跑**：`rm -rf memory/db memory/knowledge memory/reviews` 之后
   `python -m brain doctor` 依然全绿——它会在空库上重新长出来。
