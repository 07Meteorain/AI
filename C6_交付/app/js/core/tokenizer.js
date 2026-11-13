/*!
 * PromptGate · core/tokenizer
 * token 估算器：不下载任何分词表，用可解释的字符分类 + 系数估算，
 * 并明确给出误差区间。预算功能的价值在「量级判断」，不在小数点。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.tokenizer = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // 系数来源：cl100k / o200k 系列分词器对中文与英文的经验比例。
  // 中文 1 字 ≈ 0.7~1.0 token（词表里的常见双字词可合并）；
  // 英文 1 词 ≈ 1.3 token；数字 3 位 ≈ 1 token；标点 ≈ 0.6 token。
  var COEF = {
    cjk: 0.75,
    latinWord: 1.3,
    digitGroup: 1.0,
    punct: 0.6,
    newline: 0.5,
    space: 0.05,
    other: 0.8
  };

  var CJK_RE = /[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u3000-\u303f\uff00-\uffef]/;

  /**
   * 估算 token 数。
   * @param {string} text
   * @returns {{tokens:number, breakdown:object, method:string, range:[number,number]}}
   */
  function estimateTokens(text) {
    var s = String(text == null ? '' : text);
    var b = { cjk: 0, latinWord: 0, digitGroup: 0, punct: 0, newline: 0, space: 0, other: 0 };
    var tokens = 0;
    var i = 0;
    var len = s.length;

    while (i < len) {
      var ch = s.charAt(i);
      var code = s.charCodeAt(i);

      if (ch === '\n') { tokens += COEF.newline; b.newline++; i++; continue; }
      if (ch === ' ' || ch === '\t') { tokens += COEF.space; b.space++; i++; continue; }

      if (CJK_RE.test(ch)) {
        // 连续 CJK 每 2 字约 1.5 token（词表常见词可合并），逐字累加同一系数即可
        tokens += COEF.cjk;
        b.cjk++;
        i++;
        continue;
      }

      if (/[0-9]/.test(ch)) {
        var digits = 0;
        while (i < len && /[0-9.,]/.test(s.charAt(i))) { digits++; i++; }
        var groups = Math.max(1, Math.ceil(digits / 3));
        tokens += groups * COEF.digitGroup;
        b.digitGroup += groups;
        continue;
      }

      if (/[A-Za-z]/.test(ch)) {
        var word = 0;
        while (i < len && /[A-Za-z0-9_'’-]/.test(s.charAt(i))) { word++; i++; }
        // 长单词会被切成多个 subword
        var extra = word > 6 ? Math.ceil((word - 6) / 4) : 0;
        tokens += COEF.latinWord + extra;
        b.latinWord += 1 + extra;
        continue;
      }

      if (/[.!?,;:()[\]{}<>/\\|@#$%^&*+=~`"'-]/.test(ch)) {
        tokens += COEF.punct;
        b.punct++;
        i++;
        continue;
      }

      tokens += COEF.other;
      b.other++;
      i++;
    }

    var rounded = Math.max(0, Math.round(tokens));
    return {
      tokens: rounded,
      breakdown: b,
      method: 'heuristic-v1 (cjk×0.75 + word×1.3 + digits/3 + punct×0.6)',
      // 估算器不假装精确：给区间，且在 UI 里如实显示
      range: [Math.max(0, Math.round(rounded * 0.8)), Math.round(rounded * 1.25) + 2]
    };
  }

  /**
   * 按行统计，用于「哪一段最贵」的定位视图。
   * @param {object} model parsePrompt 的结果
   */
  function estimateByLine(model) {
    var out = [];
    model.lines.forEach(function (l) {
      if (l.blank) return;
      var t = estimateTokens(l.text).tokens;
      out.push({ line: l.no, tokens: t, kind: l.kind, text: l.text });
    });
    return out;
  }

  /** 按小节聚合。 */
  function estimateBySection(model) {
    var out = [];
    model.sections.forEach(function (sec) {
      var chunk = model.lines
        .slice(sec.start - 1, sec.end)
        .map(function (l) { return l.text; })
        .join('\n');
      out.push({
        title: sec.title,
        start: sec.start,
        end: sec.end,
        tokens: estimateTokens(chunk).tokens
      });
    });
    return out.sort(function (a, b) { return b.tokens - a.tokens; });
  }

  /**
   * 成本计算。
   * @param {number} inputTokens
   * @param {number} outputTokens
   * @param {{inPrice:number,outPrice:number}} model 价格为「每 100 万 token 的美元价」
   * @returns {{perCall:number, per1kCalls:number, monthly:number}}
   */
  function costFor(inputTokens, outputTokens, model) {
    var inP = Number(model && model.inPrice) || 0;
    var outP = Number(model && model.outPrice) || 0;
    var perCall = (inputTokens * inP + outputTokens * outP) / 1e6;
    return {
      perCall: perCall,
      per1kCalls: perCall * 1000,
      monthly: perCall
    };
  }

  /**
   * 月度成本 = 单次成本 × 每天调用 × 天数。天数固定 30，UI 里写明。
   */
  function monthlyCost(inputTokens, outputTokens, model, callsPerDay, days) {
    var perCall = costFor(inputTokens, outputTokens, model).perCall;
    var d = Number(days) || 30;
    var calls = Number(callsPerDay) || 0;
    return {
      perCall: perCall,
      monthly: perCall * calls * d,
      calls: calls * d,
      days: d
    };
  }

  return {
    estimateTokens: estimateTokens,
    estimateByLine: estimateByLine,
    estimateBySection: estimateBySection,
    costFor: costFor,
    monthlyCost: monthlyCost,
    COEF: COEF
  };
}));
