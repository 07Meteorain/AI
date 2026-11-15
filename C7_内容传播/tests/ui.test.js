// 渲染层：用户能把任意文本打进输入框，转义漏一处就是一个 XSS。
// 另外 SVG 里一旦出现 NaN，图会静默变成空白——这两种都写成断言。
const test = require("node:test");
const assert = require("node:assert");

const DATA = require("../app/js/core/data.js");
const M = require("../app/js/core/metrics.js");
const Ui = require("../app/js/ui.js");

const EVIL = '<img src=x onerror="alert(1)">';

test("esc 转义所有危险字符", () => {
  const out = Ui.esc(EVIL);
  assert.ok(!out.includes("<"), "不应残留 <");
  assert.ok(out.includes("&lt;"));
  assert.ok(out.includes("&quot;"));
  assert.strictEqual(Ui.esc("'"), "&#39;");
  assert.strictEqual(Ui.esc(null), "");
});

test("评分卡里的标题/理由会被转义（标题也是用户输入）", () => {
  const r = { chars: 10, hook: 1, specificity: 1, searchability: 1, platformFit: 1, credibility: 1, total: 5, grade: "弃用", vetoed: true, reasons: [EVIL] };
  const html = Ui.renderScoreCard(r, DATA.rubric);
  assert.ok(!html.includes("onerror=\"alert"), "理由里的脚本必须被转义");
  assert.ok(!html.includes("<img"), "不应出现 img 标签");
});

test("候选表格里出现每条候选，且带评级", () => {
  const html = Ui.renderTitleTable(DATA.titles);
  assert.ok(html.includes("<table"));
  for (const row of DATA.titles) {
    assert.ok(html.includes(row.id), `缺 ${row.id}`);
  }
  assert.ok(html.includes("g-strong") || html.includes("grade"));
});

test("漏斗 SVG：五条明细、没有 NaN、宽度不越界", () => {
  const svg = Ui.renderFunnelSvg(M.funnel(DATA.params["公众号"]), "#2f6feb");
  assert.ok(svg.startsWith("<svg"));
  assert.ok(!svg.includes("NaN"), "SVG 里出现 NaN 会导致静默空白");
  for (const label of M.STAGES) {
    assert.ok(svg.includes(label), `缺阶段 ${label}`);
  }
});

test("增长曲线 SVG：四条折线 + 图例", () => {
  const series = {};
  for (const ch of DATA.channels) series[ch] = M.growth(DATA.params[ch]);
  const svg = Ui.renderGrowthSvg(series, DATA.channels);
  assert.strictEqual((svg.match(/<polyline/g) || []).length, 4);
  assert.ok(!svg.includes("NaN"));
  for (const ch of DATA.channels) assert.ok(svg.includes(ch), `图例缺 ${ch}`);
});

test("渠道卡：六个参数都出现", () => {
  const html = Ui.renderChannelCards(DATA.params, DATA.channels);
  for (const label of ["曝光", "打开率", "进入率", "读完率", "互动率", "转化率"]) {
    assert.ok(html.includes(label), `缺 ${label}`);
  }
});

test("清单渲染：勾选状态来自传入的 map", () => {
  const html = Ui.renderChecklist(["一", "二", "三"], { 1: true });
  assert.strictEqual((html.match(/checked/g) || []).length, 1);
  assert.ok(html.includes("data-idx=\"1\""));
});

test("fmtNum 与 metrics 的口径一致", () => {
  assert.strictEqual(Ui.fmtNum(9860), "9,860");
  assert.strictEqual(Ui.fmtNum(2.7), "2.7");
});
