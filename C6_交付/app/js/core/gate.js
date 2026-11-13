/*!
 * PromptGate · core/gate
 * 把「一堆发现」收敛成一个可执行结论：通过 / 拦下，以及 0~100 的健康分。
 *
 * 设计取舍：
 * 1. 门禁只看级别，不做加权求和 —— 一条 error 就是不能上线，不该被 30 条 info 稀释。
 * 2. 健康分是「阅读指标」不是门禁指标，两者分离展示，避免用分数掩盖致命项。
 * 3. 基线忽略按「规则 + 消息」指纹，不含行号 —— 否则每次调整格式都会让历史问题复活。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.gate = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var WEIGHT = { error: 14, warning: 4, info: 1 };
  var LEVEL_RANK = { info: 1, warning: 2, error: 3 };

  function fingerprint(finding) {
    return finding.ruleId + '|' + String(finding.message || '').replace(/\s+/g, ' ').trim();
  }

  /**
   * @param {object[]} findings 规则命中
   * @param {object} options {failOn:'error'|'warning'|'none', disabled:[ruleId], baseline:[fingerprint]}
   */
  function evaluate(findings, options) {
    var opts = options || {};
    var disabled = opts.disabled || [];
    var baseline = opts.baseline || [];
    var failOn = opts.failOn || 'error';

    var enabled = [];
    var suppressed = [];

    (findings || []).forEach(function (f) {
      var fp = fingerprint(f);
      if (disabled.indexOf(f.ruleId) !== -1) {
        suppressed.push({ finding: f, reason: 'rule-disabled', fingerprint: fp });
        return;
      }
      if (baseline.indexOf(fp) !== -1) {
        suppressed.push({ finding: f, reason: 'baseline', fingerprint: fp });
        return;
      }
      enabled.push(f);
    });

    var counts = { error: 0, warning: 0, info: 0 };
    enabled.forEach(function (f) {
      if (counts[f.severity] == null) counts[f.severity] = 0;
      counts[f.severity]++;
    });

    var penalty = counts.error * WEIGHT.error + counts.warning * WEIGHT.warning + counts.info * WEIGHT.info;
    var score = Math.max(0, Math.min(100, 100 - penalty));

    var blocking = 0;
    if (failOn === 'error') blocking = counts.error;
    else if (failOn === 'warning') blocking = counts.error + counts.warning;
    else blocking = 0;

    var verdict = blocking > 0 ? 'fail' : 'pass';

    return {
      verdict: verdict,
      failOn: failOn,
      counts: counts,
      score: score,
      grade: grade(score),
      blocking: blocking,
      findings: enabled,
      suppressed: suppressed,
      suppressedCount: suppressed.length,
      summary: summarize(verdict, counts, failOn)
    };
  }

  function grade(score) {
    if (score >= 90) return { letter: 'A', label: '可以直接上线' };
    if (score >= 75) return { letter: 'B', label: '小修后上线' };
    if (score >= 60) return { letter: 'C', label: '需要重写一部分' };
    return { letter: 'D', label: '建议重写' };
  }

  function summarize(verdict, counts, failOn) {
    if (verdict === 'pass') {
      var clean = counts.error + counts.warning + counts.info === 0;
      return clean ? '没有发现问题，可以上线' : '未触及门禁阈值（' + failOn + '），可以上线';
    }
    return '门禁未通过：' + counts.error + ' 个 error / ' + counts.warning + ' 个 warning';
  }

  /** 仪表盘用的分布：哪些规则贡献了多少扣分。 */
  function penaltyByRule(findings) {
    var map = Object.create(null);
    findings.forEach(function (f) {
      var w = WEIGHT[f.severity] || 0;
      if (!map[f.ruleId]) map[f.ruleId] = { ruleId: f.ruleId, count: 0, penalty: 0, severity: f.severity };
      map[f.ruleId].count++;
      map[f.ruleId].penalty += w;
      if (LEVEL_RANK[f.severity] > LEVEL_RANK[map[f.ruleId].severity]) map[f.ruleId].severity = f.severity;
    });
    return Object.keys(map).map(function (k) { return map[k]; })
      .sort(function (a, b) { return b.penalty - a.penalty || a.ruleId.localeCompare(b.ruleId); });
  }

  /** 基线导出：把当前未忽略的发现变成可提交的指纹列表。 */
  function toBaseline(findings) {
    var seen = Object.create(null);
    var out = [];
    (findings || []).forEach(function (f) {
      var fp = fingerprint(f);
      if (!seen[fp]) { seen[fp] = true; out.push(fp); }
    });
    return out.sort();
  }

  return {
    evaluate: evaluate,
    grade: grade,
    fingerprint: fingerprint,
    penaltyByRule: penaltyByRule,
    toBaseline: toBaseline,
    WEIGHT: WEIGHT,
    LEVEL_RANK: LEVEL_RANK
  };
}));
