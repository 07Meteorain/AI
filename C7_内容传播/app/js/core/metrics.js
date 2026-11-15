// 传播指标计算：漏斗、七日累积、A/B 样本量。
// 与 tools/chartgen.py 里的公式逐行对应，数字必须一致（tests/metrics.test.js 对账）。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Metrics = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var STAGES = ["曝光", "进入正文", "读完", "互动", "领取清单"];

  function funnel(p) {
    var exposure = p.exposure;
    var entered = exposure * p.open_rate * p.click_rate;
    var done = entered * p.read_through;
    var engage = entered * p.engage_rate;
    var convert = entered * p.convert_rate;
    return [
      { label: STAGES[0], value: exposure },
      { label: STAGES[1], value: entered },
      { label: STAGES[2], value: done },
      { label: STAGES[3], value: engage },
      { label: STAGES[4], value: convert },
    ];
  }

  // 累积阅读：day1..day7 权重 × 阅读量
  function growth(p) {
    var reads = p.exposure * p.open_rate * p.click_rate;
    var out = [];
    var acc = 0;
    for (var i = 1; i <= 7; i++) {
      acc += reads * (p["day" + i + "_weight"] || 0);
      out.push(acc);
    }
    return out;
  }

  function normSf(z) {
    // 标准正态上尾概率的近似（Abramowitz & Stegun 7.1.26 的变体误差 ~1e-7，够用）
    var t = 1 / (1 + 0.2316419 * Math.abs(z));
    var d = 0.3989422804014327 * Math.exp((-z * z) / 2);
    var p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return z >= 0 ? p : 1 - p;
  }

  var Z_ALPHA = 1.959963985;
  var Z_BETA_80 = 0.841621234;

  // 双比例检验：每臂所需样本量（向上取整）
  function abRequired(p1, p2, power) {
    var zb = power === 0.9 ? 1.281551566 : Z_BETA_80;
    var pBar = (p1 + p2) / 2;
    var num = Math.pow(
      Z_ALPHA * Math.sqrt(2 * pBar * (1 - pBar)) + zb * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)),
      2
    );
    return Math.ceil(num / Math.pow(p2 - p1, 2));
  }

  // 给定每臂样本量的统计功效
  function powerAt(n, p1, p2) {
    var pBar = (p1 + p2) / 2;
    var se0 = Math.sqrt((2 * pBar * (1 - pBar)) / n);
    var se1 = Math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / n);
    var z = (Math.abs(p2 - p1) - Z_ALPHA * se0) / se1;
    return 1 - normSf(z);
  }

  function totalReads(params, channels) {
    return channels.reduce(function (s, ch) {
      return s + funnel(params[ch])[1].value;
    }, 0);
  }

  function fmtCount(v) {
    var n = Math.abs(v) >= 10 ? Math.round(v) : Math.round(v * 10) / 10;
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  return {
    STAGES: STAGES,
    funnel: funnel,
    growth: growth,
    abRequired: abRequired,
    powerAt: powerAt,
    totalReads: totalReads,
    fmtCount: fmtCount,
  };
});
