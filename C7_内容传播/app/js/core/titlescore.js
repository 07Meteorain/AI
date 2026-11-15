// 标题评分器（JS 侧实现）。
// 与 tools/title_score.py 是同一套规则的两个实现：输入同一份 rubric，必须输出同一个分数。
// 一致性由 tests/titlescore-parity.test.js 兜底（32 条候选逐条比对 fixture）。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TitleScore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function effectiveLength(title) {
    return String(title).replace(/\s+/g, "").length;
  }

  function hits(kind, value, title) {
    var i, n;
    if (kind === "regex") return new RegExp(value).test(title) ? 1 : 0;
    if (kind === "regexCount") {
      var m = title.match(new RegExp(value, "g"));
      return m ? m.length : 0;
    }
    if (kind === "words") {
      for (i = 0; i < value.length; i++) if (title.indexOf(value[i]) !== -1) return 1;
      return 0;
    }
    if (kind === "wordCount") {
      n = 0;
      for (i = 0; i < value.length; i++) {
        var w = value[i];
        var pos = title.indexOf(w);
        while (pos !== -1) {
          n++;
          pos = title.indexOf(w, pos + w.length);
        }
      }
      return n;
    }
    throw new Error("unknown rule kind: " + kind);
  }

  // cap 对正分是上限，对负分是下限（与 Python 侧一致）
  function applyRule(rule, title) {
    var h = hits(rule.kind, rule.value, title);
    if (h === 0) return 0;
    var raw = rule.points * h;
    return rule.points >= 0 ? Math.min(raw, rule.cap) : Math.max(raw, rule.cap);
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function scoreTitle(title, rubric) {
    var reasons = [];
    var maxes = {};
    rubric.dimensions.forEach(function (d) {
      maxes[d.id] = d.max;
    });
    var scores = {};

    ["hook", "specificity", "searchability"].forEach(function (dim) {
      var spec = rubric[dim];
      var total = spec.base;
      spec.rules.forEach(function (rule) {
        var c = applyRule(rule, title);
        if (c) {
          total += c;
          reasons.push(dim + ":" + rule.label + "(" + (c > 0 ? "+" : "") + c + ")");
        }
      });
      scores[dim] = clamp(total, 0, maxes[dim]);
    });

    var pf = rubric.platformFit;
    var length = effectiveLength(title);
    var bandScore = 0;
    var bandLabel = "";
    pf.bands.forEach(function (band) {
      if (!bandLabel && band.minLength <= length && length <= band.maxLength) {
        bandScore = band.score;
        bandLabel = band.label;
      }
    });
    var fit = bandScore;
    reasons.push("platformFit:" + bandLabel + "(" + bandScore + ")");
    pf.penalties.forEach(function (rule) {
      var c = applyRule(rule, title);
      if (c) {
        fit += c;
        reasons.push("platformFit:" + rule.label + "(" + (c > 0 ? "+" : "") + c + ")");
      }
    });
    scores.platformFit = clamp(fit, 0, maxes.platformFit);

    var cr = rubric.credibility;
    var cred = cr.base;
    cr.penalties.forEach(function (rule) {
      var c = applyRule(rule, title);
      if (c) {
        cred += c;
        reasons.push("credibility:" + rule.label + "(" + (c > 0 ? "+" : "") + c + ")");
      }
    });
    cr.bonuses.forEach(function (rule) {
      var c = applyRule(rule, title);
      if (c) {
        cred += c;
        reasons.push("credibility:" + rule.label + "(" + (c > 0 ? "+" : "") + c + ")");
      }
    });
    scores.credibility = clamp(cred, 0, maxes.credibility);

    var total = 0;
    Object.keys(scores).forEach(function (k) {
      total += scores[k];
    });
    total = clamp(total, 0, 100);

    var veto = rubric.veto || {};
    var vetoed = (veto.words || []).some(function (w) {
      return title.indexOf(w) !== -1;
    });
    if (vetoed) {
      total = Math.min(total, veto.cap);
      reasons.push("veto:" + veto.label + "(封顶 " + veto.cap + ")");
    }

    var grade;
    if (vetoed) grade = "弃用";
    else if (total >= rubric.thresholds.strong) grade = "主推";
    else if (total >= rubric.thresholds.usable) grade = "可用";
    else if (total >= rubric.thresholds.weak) grade = "备选";
    else grade = "弃用";

    return {
      chars: length,
      hook: scores.hook,
      specificity: scores.specificity,
      searchability: scores.searchability,
      platformFit: scores.platformFit,
      credibility: scores.credibility,
      total: total,
      grade: grade,
      vetoed: vetoed,
      reasons: reasons,
    };
  }

  // 排序：总分 → 具体性 → 钩子 → ID（rubric.tieBreak 的文字版）
  function rank(rows) {
    return rows.slice().sort(function (a, b) {
      if (b.total !== a.total) return b.total - a.total;
      if (b.specificity !== a.specificity) return b.specificity - a.specificity;
      if (b.hook !== a.hook) return b.hook - a.hook;
      return String(a.id).localeCompare(String(b.id));
    });
  }

  return { scoreTitle: scoreTitle, rank: rank, effectiveLength: effectiveLength, applyRule: applyRule };
});
