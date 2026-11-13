/*!
 * PromptGate · core/report
 * 「一次体检」的唯一入口：文本 → 解析 → 规则 → 门禁 → 预算 → 报告对象。
 * UI、CLI、测试都走这里，保证三处结论完全一致。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(
      require('./parser'),
      require('./rules'),
      require('./tokenizer'),
      require('./gate'),
      require('./models')
    );
  } else {
    root.PG = root.PG || {};
    root.PG.report = factory(root.PG.parser, root.PG.rules, root.PG.tokenizer, root.PG.gate, root.PG.models);
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (parser, rules, tokenizer, gate, models) {
  'use strict';

  var VERSION = '1.0.0';

  /**
   * @param {string} text
   * @param {object} opts {title, disabled:[], baseline:[], failOn, models:[], assumptions:{}, now}
   */
  function buildReport(text, opts) {
    var options = opts || {};
    var model = parser.parsePrompt(text);
    // 注意：这里不把 disabled 传给 lint —— 规则照常执行，由 gate 统一裁决是否忽略。
    // 这样「已关闭的规则」在报告里仍然可见（标注为 rule-disabled），而不是凭空消失。
    var findings = rules.lint(model, {});
    var gateResult = gate.evaluate(findings, {
      failOn: options.failOn || 'error',
      disabled: options.disabled || [],
      baseline: options.baseline || []
    });

    var est = tokenizer.estimateTokens(model.text);
    var assumption = {
      outputTokens: numOr(options.assumptions && options.assumptions.outputTokens, models.ASSUMPTIONS.outputTokens),
      callsPerDay: numOr(options.assumptions && options.assumptions.callsPerDay, models.ASSUMPTIONS.callsPerDay),
      days: numOr(options.assumptions && options.assumptions.days, models.ASSUMPTIONS.days)
    };

    var list = (options.models && options.models.length) ? options.models : models.DEFAULT_MODELS;
    var validated = models.validate(list);
    var rows = validated.models.map(function (m) {
      var c = tokenizer.monthlyCost(est.tokens, assumption.outputTokens, m, assumption.callsPerDay, assumption.days);
      return {
        id: m.id,
        label: m.label,
        vendor: m.vendor,
        inPrice: m.inPrice,
        outPrice: m.outPrice,
        ctx: m.ctx,
        perCall: c.perCall,
        monthly: c.monthly
      };
    });

    var cheapest = null;
    var priciest = null;
    rows.forEach(function (r) {
      if (!cheapest || r.monthly < cheapest.monthly) cheapest = r;
      if (!priciest || r.monthly > priciest.monthly) priciest = r;
    });
    var spread = cheapest && priciest && cheapest.monthly > 0
      ? Math.round((priciest.monthly / cheapest.monthly) * 10) / 10
      : 0;

    var totalLines = tokenizer.estimateByLine(model).length;

    return {
      meta: {
        app: 'PromptGate',
        tool: 'PromptGate',
        version: VERSION,
        generatedAt: options.now || Date.now(),
        title: options.title || ''
      },
      model: model,
      findings: gateResult.findings,
      suppressed: gateResult.suppressed,
      gate: gateResult,
      variables: model.variables.map(function (v) {
        return { name: v.name, raw: v.raw, count: v.count, lines: v.lines, valid: v.valid };
      }),
      stats: {
        chars: model.stats.chars,
        charsNoSpace: model.stats.charsNoSpace,
        lines: model.stats.lines,
        nonBlankLines: totalLines,
        tokens: est.tokens,
        range: est.range,
        method: est.method,
        headings: model.stats.headings,
        codeBlocks: model.codeBlocks.length
      },
      sections: tokenizer.estimateBySection(model),
      budget: {
        priceSnapshot: models.PRICE_SNAPSHOT,
        assumptions: assumption,
        rows: rows,
        cheapest: cheapest,
        priciest: priciest,
        spread: spread,
        warnings: validated.errors
      }
    };
  }

  function numOr(value, fallback) {
    var n = Number(value);
    return isFinite(n) && n >= 0 ? n : fallback;
  }

  return { buildReport: buildReport, VERSION: VERSION };
}));
