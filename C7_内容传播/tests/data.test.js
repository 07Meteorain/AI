// 数据一致性：data.js 是从 CSV 编译出来的，两边必须对得上。
// 这条测试的存在意义：有人改了 CSV 忘了重跑 gen_data_js.py 时，这里会红，
// 而不是等到评审打开页面发现数字对不上。
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const DATA = require("../app/js/core/data.js");
const Csv = require("../app/js/core/csv.js");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

test("候选标题：条数与字段都来自 数据/titles_scored.csv", () => {
  const rows = Csv.parse(read("数据/titles_scored.csv"));
  assert.strictEqual(DATA.titles.length, rows.length);
  rows.forEach((row, i) => {
    const got = DATA.titles.find((t) => t.id === row.id);
    assert.ok(got, `data.js 缺 ${row.id}`);
    assert.strictEqual(got.title, row.title, `${row.id} 标题不一致`);
    assert.strictEqual(got.total, Number(row.total), `${row.id} 总分不一致`);
    assert.strictEqual(got.grade, row.grade, `${row.id} 评级不一致`);
    assert.strictEqual(got.hook, Number(row.hook));
  });
});

test("渠道参数：每个字段都能在 projection_params.csv 里找到", () => {
  const rows = Csv.parse(read("数据/projection_params.csv"));
  const byMetric = {};
  for (const r of rows) byMetric[r.metric] = r;
  for (const ch of DATA.channels) {
    for (const [metric, value] of Object.entries(DATA.params[ch])) {
      assert.ok(byMetric[metric], `参数表缺 metric=${metric}`);
      assert.strictEqual(Number(byMetric[metric][ch]), value, `${ch}.${metric} 不一致`);
    }
    assert.strictEqual(Object.keys(DATA.params[ch]).length, rows.length, `${ch} 参数数量不对`);
  }
});

test("仓库事实：合计与 meta 对得上", () => {
  const facts = DATA.facts;
  const sumTests = facts.reduce((s, f) => s + (f.tests_computed || 0), 0);
  const sumFiles = facts.reduce((s, f) => s + (f.files || 0), 0);
  assert.strictEqual(sumTests, DATA.meta.total_tests, "测试合计");
  assert.strictEqual(sumFiles, DATA.meta.total_files, "文件合计");
  assert.strictEqual(sumTests, 464);
  assert.strictEqual(DATA.meta.total_commits, 127);
});

test("自报 = 实测：8 个有关口的目录全部一致（有差异就必须红）", () => {
  const declared = facts_ => facts_.filter((f) => f.declared_tests !== null && f.declared_tests !== "");
  const rows = declared(DATA.facts);
  assert.strictEqual(rows.length, 8, "应该有 8 个目录带自报测试数");
  for (const r of rows) {
    assert.strictEqual(r.declared_tests, r.tests_computed, `${r.scope}: 自报 ${r.declared_tests} vs 实测 ${r.tests_computed}`);
  }
});

test("rubric 与 数据/title_rubric.json 完全一致", () => {
  const raw = JSON.parse(read("数据/title_rubric.json"));
  assert.deepStrictEqual(DATA.rubric.dimensions, raw.dimensions);
  assert.deepStrictEqual(DATA.rubric.veto.words, raw.veto.words);
  assert.strictEqual(DATA.rubric.thresholds.strong, raw.thresholds.strong);
});

test("快照 meta 带 as_of_commit（没有截止点的数字等于假话）", () => {
  assert.match(DATA.meta.as_of_commit, /^[0-9a-f]{40}$/);
  assert.match(DATA.meta.as_of_date, /^\d{4}-\d{2}-\d{2}$/);
});

test("正文里引用的数字与快照一致（文章不许说假话）", () => {
  const md = read("文章/正文.md");
  const commits = /([\d,]+)\s*次提交/.exec(md);
  const files = /([\d,]+)\s*个文件/.exec(md);
  const tests = /([\d,]+)\s*项自测/.exec(md);
  const num = (m) => Number(m[1].replace(/,/g, ""));
  assert.ok(commits, "正文应写明提交数");
  assert.ok(files, "正文应写明文件数");
  assert.ok(tests, "正文应写明自测数");
  assert.strictEqual(num(commits), DATA.meta.total_commits, "正文的提交数与快照不一致");
  assert.strictEqual(num(files), DATA.meta.total_files, "正文的文件数与快照不一致");
  assert.strictEqual(num(tests), DATA.meta.total_tests, "正文的测试数与快照不一致");
});

test("正文标题必须来自候选库（发出去的标题不许是临时想的）", () => {
  const md = read("文章/正文.md");
  const m = /^title:\s*(.+)$/m.exec(md);
  assert.ok(m, "正文 front matter 应有 title");
  const title = m[1].trim();
  const hit = DATA.titles.find((r) => r.title === title);
  assert.ok(hit, `正文标题「${title}」不在 32 条候选里`);
});

test("正文里引用的快照 commit 与 meta 一致", () => {
  const md = read("文章/正文.md");
  const m = /master@([0-9a-f]{7,40})/.exec(md);
  assert.ok(m, "正文应写明数据截止的 commit");
  assert.ok(DATA.meta.as_of_commit.startsWith(m[1]), `正文写 ${m[1]}，快照是 ${DATA.meta.as_of_commit.slice(0, 7)}`);
});
