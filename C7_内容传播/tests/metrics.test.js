// 指标公式的测试：数字必须和 tools/chartgen.py 算出来的一致，
// 否则 app 里看到的漏斗/曲线和截图对不上——这正是"两套实现"最容易出事的地方。
const test = require("node:test");
const assert = require("node:assert");

const DATA = require("../app/js/core/data.js");
const M = require("../app/js/core/metrics.js");

const WECHAT = DATA.params["公众号"];

test("漏斗：公众号首篇的五个阶段", () => {
  const f = M.funnel(WECHAT);
  assert.deepStrictEqual(f.map((s) => s.label), ["曝光", "进入正文", "读完", "互动", "领取清单"]);
  assert.strictEqual(f[0].value, 860);
  assert.ok(Math.abs(f[1].value - 77.4) < 1e-9, `进入正文 = 860*0.09 = 77.4，实际 ${f[1].value}`);
  assert.ok(Math.abs(f[2].value - 32.508) < 1e-9);
  assert.ok(Math.abs(f[4].value - 1.2384) < 1e-9);
});

test("漏斗单调递减（互动率低于转化率会让漏斗「倒挂」，必须测出来）", () => {
  for (const ch of DATA.channels) {
    const f = M.funnel(DATA.params[ch]);
    for (let i = 1; i < f.length; i++) {
      assert.ok(f[i].value <= f[i - 1].value, `${ch}: ${f[i].label}(${f[i].value}) 大于 ${f[i - 1].label}(${f[i - 1].value})`);
    }
  }
});

test("七日累积：单调不减，且 D7 等于总阅读量", () => {
  for (const ch of DATA.channels) {
    const p = DATA.params[ch];
    const g = M.growth(p);
    const total = p.exposure * p.open_rate * p.click_rate;
    assert.strictEqual(g.length, 7);
    for (let i = 1; i < g.length; i++) assert.ok(g[i] >= g[i - 1], `${ch} D${i + 1} 回退了`);
    assert.ok(Math.abs(g[6] - total) < 1e-6, `${ch}: D7=${g[6]} 应等于 ${total}`);
  }
});

test("七日权重之和为 1（参数表写错会让曲线悄悄缩放）", () => {
  for (const ch of DATA.channels) {
    const p = DATA.params[ch];
    let sum = 0;
    for (let i = 1; i <= 7; i++) sum += p["day" + i + "_weight"];
    assert.ok(Math.abs(sum - 1) < 1e-9, `${ch} 的 day 权重和 = ${sum}`);
  }
});

test("A/B 所需样本：9% vs 11% 需要每臂 3,531", () => {
  assert.strictEqual(M.abRequired(0.09, 0.11), 3531);
  // 差异越小，样本越多（单调性）
  assert.ok(M.abRequired(0.09, 0.1) > M.abRequired(0.09, 0.11));
  assert.ok(M.abRequired(0.05, 0.2) < M.abRequired(0.09, 0.11));
  // 功效要求越高，样本越多
  assert.ok(M.abRequired(0.09, 0.11, 0.9) > M.abRequired(0.09, 0.11, 0.8));
});

test("功效曲线：在所需样本量处应达到 80%", () => {
  const need = M.abRequired(0.09, 0.11);
  const power = M.powerAt(need, 0.09, 0.11);
  assert.ok(power >= 0.79 && power <= 0.82, `功效 = ${power}`);
  assert.ok(M.powerAt(100, 0.09, 0.11) < 0.2, "样本太小时功效应该很低");
  assert.ok(M.powerAt(50000, 0.09, 0.11) > 0.99);
});

test("本次可用的 430/臂 远不够：功效 < 30%（这就是「不可判定」的量化依据）", () => {
  const p = M.powerAt(430, 0.09, 0.11);
  assert.ok(p < 0.3, `功效 = ${p}`);
});

test("fmtCount：大数加千分位，小数留一位", () => {
  assert.strictEqual(M.fmtCount(9860), "9,860");
  assert.strictEqual(M.fmtCount(2.7), "2.7");
  assert.strictEqual(M.fmtCount(0.5), "0.5");
});
