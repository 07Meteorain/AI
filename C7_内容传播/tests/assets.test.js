// 产物存在性 + 引用完整性。
// 线上 404 是最难在本地复现的故障，所以"index.html 引用的每个脚本都存在"要变成测试。
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const APP = path.join(ROOT, "app");
const SHOTS = path.join(ROOT, "数据", "screenshots");

const SHOT_FILES = [
  "01_标题评分.png",
  "02_渠道漏斗.png",
  "03_七日增长.png",
  "04_AB显著性.png",
  "05_正文结构.png",
  "06_仓库事实.png",
];

test("app/index.html 引用的每个 js/css 都存在", () => {
  const html = fs.readFileSync(path.join(APP, "index.html"), "utf8");
  const refs = [...html.matchAll(/(?:src|href)="([^"#][^"]*)"/g)]
    .map((m) => m[1])
    .filter((u) => !/^https?:/.test(u) && !u.startsWith("#"));
  assert.ok(refs.length >= 7, `引用数偏少：${refs.length}`);
  for (const ref of refs) {
    const file = path.join(APP, ref.split("?")[0]);
    assert.ok(fs.existsSync(file), `引用了不存在的文件：${ref}`);
  }
});

test("正文与清单的 HTML 都已生成，且不是空壳", () => {
  for (const name of ["article.html", "checklist.html"]) {
    const p = path.join(APP, name);
    assert.ok(fs.existsSync(p), `${name} 缺失（跑 python tools/build_article.py）`);
    const size = fs.statSync(p).size;
    assert.ok(size > 8000, `${name} 只有 ${size} 字节，疑似渲染失败`);
  }
  const article = fs.readFileSync(path.join(APP, "article.html"), "utf8");
  assert.ok(article.includes("验收"), "正文里应该有「验收」二字");
  assert.ok(article.includes("AI 挑战"), "标题应该出现在正文 HTML 里");
});

test("正文目录条目数 = 小标题数（C4B 的目录会漏第一个，已在构建时补齐）", () => {
  const article = fs.readFileSync(path.join(APP, "article.html"), "utf8");
  const h2 = (article.match(/<h2/g) || []).length;
  const tocBlock = article.slice(article.indexOf("本文目录"), article.indexOf("</section>", article.indexOf("本文目录")));
  const tocItems = (tocBlock.match(/<p style=/g) || []).length; // 目录条目本身（"本文目录"标题在 marker 之前）
  assert.ok(h2 >= 5, `小标题太少：${h2}`);
  assert.strictEqual(tocItems, h2, `目录 ${tocItems} 条 vs 小标题 ${h2} 个`);
});

test("6 张数据截图都在，且 manifest 有对应记录", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(SHOTS, "manifest.json"), "utf8"));
  for (const f of SHOT_FILES) {
    const p = path.join(SHOTS, f);
    assert.ok(fs.existsSync(p), `缺截图 ${f}`);
    assert.ok(fs.statSync(p).size > 20000, `${f} 太小，疑似生成失败`);
    assert.ok(manifest.charts[f], `manifest 里没有 ${f}`);
    assert.match(manifest.charts[f].data_sha256, /^[0-9a-f]{64}$/);
  }
});

test("app/assets/shots 与 数据/screenshots 逐字节一致（副本不能漂移）", () => {
  for (const f of SHOT_FILES) {
    const a = fs.readFileSync(path.join(SHOTS, f));
    const b = fs.readFileSync(path.join(APP, "assets", "shots", f));
    assert.ok(a.equals(b), `app/assets/shots/${f} 与 数据/screenshots/${f} 不一致`);
  }
});

test("README 与 提交说明 里引用的关键交付物都在", () => {
  const need = [
    "README.md",
    "提交说明.md",
    "AI日志.md",
    "AAR复盘.md",
    "拿来说明.md",
    "文章/正文.md",
    "文章/标题库.md",
    "文章/微信版.html",
    "文章/多平台改编.md",
    "文章/验收清单.html",
    "数据/指标口径.md",
    "数据/titles.csv",
    "数据/titles_scored.csv",
    "数据/标题评分表.md",
    "数据/repo_facts.csv",
    "数据/projection_params.csv",
  ];
  for (const rel of need) {
    assert.ok(fs.existsSync(path.join(ROOT, rel)), `缺交付物 ${rel}`);
  }
});
