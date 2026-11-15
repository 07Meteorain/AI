// 最重要的一条测试：JS 与 Python 两套实现必须给同一个分数。
// fixture 由 tools/title_score.py 生成（Python 侧），这里跑 JS 侧对账。
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const DATA = require("../app/js/core/data.js");
const TS = require("../app/js/core/titlescore.js");
const fixture = require("./fixtures/title_scores.json");

const SCORE_KEYS = ["hook", "specificity", "searchability", "platformFit", "credibility", "total"];

test("32 条候选：JS 与 Python 的分数逐条相同", () => {
  assert.strictEqual(fixture.length, 32, "fixture 应该覆盖 32 条候选");
  for (const expected of fixture) {
    const got = TS.scoreTitle(expected.title, DATA.rubric);
    for (const key of SCORE_KEYS) {
      assert.strictEqual(got[key], expected[key], `${expected.id}.${key}: JS=${got[key]} Python=${expected[key]}`);
    }
    assert.strictEqual(got.grade, expected.grade, `${expected.id}.grade`);
  }
});

test("每条候选在 data.js 里也带着同样的分数（三处对齐）", () => {
  for (const row of DATA.titles) {
    const got = TS.scoreTitle(row.title, DATA.rubric);
    assert.strictEqual(got.total, row.total, `${row.id}.total`);
    assert.strictEqual(got.grade, row.grade, `${row.id}.grade`);
  }
});

test("有效长度：空白不计入（这是标题长度评分的前提）", () => {
  assert.strictEqual(TS.effectiveLength("6 个 AI 挑战"), 6);  // 6 个 A I 挑 战 -> 6
  assert.strictEqual(TS.effectiveLength("  中文  标题\n"), 4);
});

test("标题党一票否决：总分封顶 40，且评级强制为弃用", () => {
  const r = TS.scoreTitle("震惊！这套 AI 验收方法绝对完美必看 99% 有效", DATA.rubric);
  assert.ok(r.vetoed, "应触发否决");
  assert.ok(r.total <= DATA.rubric.veto.cap, `总分应 <= ${DATA.rubric.veto.cap}，实际 ${r.total}`);
  assert.strictEqual(r.grade, "弃用");
});

test("维度分不会越界（每条规则都带 cap，最后还要 clamp）", () => {
  const longNumeric = "131 个测试 63 次提交 446 项 12 条 32 种 7 天 24 小时 860 次曝光 962 阅读 3531 样本";
  for (const t of [longNumeric, "？", "AI 验收", ""]) {
    const r = TS.scoreTitle(t, DATA.rubric);
    for (const d of DATA.rubric.dimensions) {
      assert.ok(r[d.id] >= 0 && r[d.id] <= d.max, `${d.id} 越界：${r[d.id]}`);
    }
    assert.ok(r.total >= 0 && r.total <= 100, `total 越界：${r.total}`);
  }
});

test("同分排序：具体性优先，其次钩子，最后 ID", () => {
  const rows = [
    { id: "B", total: 70, specificity: 10, hook: 12 },
    { id: "A", total: 70, specificity: 12, hook: 8 },
    { id: "C", total: 70, specificity: 10, hook: 12 },
    { id: "D", total: 72, specificity: 6, hook: 6 },
  ];
  assert.deepStrictEqual(
    TS.rank(rows).map((r) => r.id),
    ["D", "A", "B", "C"]
  );
});

test("rank 不修改入参（纯函数）", () => {
  const rows = [{ id: "A", total: 1, specificity: 1, hook: 1 }, { id: "B", total: 2, specificity: 1, hook: 1 }];
  const copy = JSON.stringify(rows);
  TS.rank(rows);
  assert.strictEqual(JSON.stringify(rows), copy);
});
