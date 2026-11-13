/*!
 * PromptGate · core/exporter
 * 三种导出：人读的 Markdown 报告、机器读的 JSON、以及可直接给 GitHub Code Scanning 的 SARIF 2.1.0。
 * 全部是纯函数（除 toBlob 之外不碰 DOM），因此可以被测试逐字段断言。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.exporter = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var TOOL = {
    name: 'PromptGate',
    version: '1.0.0',
    uri: 'https://github.com/07Meteorain/AI'
  };

  var SEVERITY_LABEL = { error: '❌ error', warning: '⚠️ warning', info: 'ℹ️ info' };
  var SARIF_LEVEL = { error: 'error', warning: 'warning', info: 'note' };

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function fmtTime(ms) {
    var d = new Date(ms || Date.now());
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' +
      pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }

  function cell(value) {
    return String(value == null ? '' : value)
      .replace(/\|/g, '\\|')
      .replace(/\r?\n/g, ' ')
      .trim();
  }

  function num(n) {
    return String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function money(n) {
    var v = Number(n) || 0;
    if (v === 0) return '$0';
    if (v < 0.001) return '$' + v.toFixed(5);
    if (v < 0.01) return '$' + v.toFixed(4);
    if (v < 0.1) return '$' + v.toFixed(3);
    return '$' + v.toFixed(2);
  }

  // ---------------- Markdown ----------------

  function toMarkdown(report) {
    var g = report.gate;
    var lines = [];
    var verdict = g.verdict === 'pass' ? '✅ PASS' : '❌ FAIL';

    lines.push('# PromptGate 上线体检报告');
    lines.push('');
    lines.push('| 项目 | 内容 |');
    lines.push('| --- | --- |');
    lines.push('| 结论 | **' + verdict + '**（阈值：' + g.failOn + '）|');
    lines.push('| 健康分 | ' + g.score + ' / 100（' + g.grade.letter + '，' + g.grade.label + '）|');
    lines.push('| 统计 | ' + g.counts.error + ' error / ' + g.counts.warning + ' warning / ' + g.counts.info + ' info |');
    lines.push('| 变量 | ' + report.variables.length + ' 个 |');
    lines.push('| 规模 | ' + num(report.stats.chars) + ' 字符 · 约 ' + num(report.stats.tokens) + ' token（' +
      num(report.stats.range[0]) + '–' + num(report.stats.range[1]) + '）|');
    lines.push('| 生成时间 | ' + fmtTime(report.meta.generatedAt) + ' |');
    lines.push('| 工具 | ' + TOOL.name + ' v' + TOOL.version + ' · 本地浏览器运行，文本未上传 |');
    lines.push('');

    lines.push('> 结论依据：' + g.summary + '。健康分是阅读指标，不是门禁依据——' +
      '一条 error 就足以拦下，不会被大量 info 稀释。');
    lines.push('');

    lines.push('## 命中问题（' + report.findings.length + '）');
    lines.push('');
    if (!report.findings.length) {
      lines.push('没有发现问题。');
    } else {
      lines.push('| 级别 | 规则 | 行 | 问题 | 建议 |');
      lines.push('| --- | --- | --- | --- | --- |');
      report.findings.forEach(function (f) {
        lines.push('| ' + SEVERITY_LABEL[f.severity] + ' | ' + f.ruleId + ' ' + cell(f.ruleTitle) +
          ' | ' + f.line + ' | ' + cell(f.message) + ' | ' + cell(f.hint) + ' |');
      });
    }
    lines.push('');

    if (report.suppressed && report.suppressed.length) {
      lines.push('## 已忽略（' + report.suppressed.length + '）');
      lines.push('');
      lines.push('| 规则 | 行 | 原因 | 问题 |');
      lines.push('| --- | --- | --- | --- |');
      report.suppressed.forEach(function (s) {
        lines.push('| ' + s.finding.ruleId + ' | ' + s.finding.line + ' | ' +
          (s.reason === 'baseline' ? '基线' : '规则已关闭') + ' | ' + cell(s.finding.message) + ' |');
      });
      lines.push('');
    }

    if (report.variables.length) {
      lines.push('## 变量契约');
      lines.push('');
      lines.push('| 变量 | 出现次数 | 行号 |');
      lines.push('| --- | --- | --- |');
      report.variables.forEach(function (v) {
        lines.push('| `' + cell(v.raw || v.name) + '` | ' + v.count + ' | ' + v.lines.join(', ') + ' |');
      });
      lines.push('');
    }

    if (report.budget && report.budget.rows && report.budget.rows.length) {
      var b = report.budget;
      lines.push('## 成本预算');
      lines.push('');
      lines.push('假设：输入 = 当前 prompt（' + num(report.stats.tokens) + ' token），输出 ≈ ' +
        num(b.assumptions.outputTokens) + ' token/次，每天 ' + num(b.assumptions.callsPerDay) +
        ' 次 × ' + b.assumptions.days + ' 天。价格快照 ' + b.priceSnapshot + '（每 100 万 token 的美元价）。');
      lines.push('');
      lines.push('| 模型 | 输入价 | 输出价 | 单次成本 | 月度成本 |');
      lines.push('| --- | --- | --- | --- | --- |');
      b.rows.forEach(function (r) {
        lines.push('| ' + cell(r.label) + ' | ' + money(r.inPrice) + ' | ' + money(r.outPrice) + ' | ' +
          money(r.perCall) + ' | ' + money(r.monthly) + ' |');
      });
      lines.push('');
      if (b.cheapest) {
        lines.push('最省：**' + b.cheapest.label + '**，月度 ' + money(b.cheapest.monthly) + '；' +
          '最贵与最省相差 ' + b.spread + ' 倍。');
        lines.push('');
      }
    }

    lines.push('---');
    lines.push('');
    lines.push('由 ' + TOOL.name + ' 生成。token 为启发式估算（±20%），价格随官方调整，预算仅作量级参考。');
    return lines.join('\n') + '\n';
  }

  // ---------------- JSON ----------------

  function toJSON(report) {
    return JSON.stringify({
      tool: TOOL,
      schema: 'promptgate/report@1',
      generatedAt: new Date(report.meta.generatedAt || Date.now()).toISOString(),
      title: report.meta.title || '',
      gate: {
        verdict: report.gate.verdict,
        failOn: report.gate.failOn,
        blocking: report.gate.blocking,
        score: report.gate.score,
        grade: report.gate.grade,
        counts: report.gate.counts,
        summary: report.gate.summary
      },
      stats: {
        chars: report.stats.chars,
        tokens: report.stats.tokens,
        tokenRange: report.stats.range,
        lines: report.stats.lines,
        variables: report.variables.length
      },
      findings: report.findings.map(function (f) {
        return {
          ruleId: f.ruleId,
          title: f.ruleTitle,
          severity: f.severity,
          category: f.category,
          line: f.line,
          message: f.message,
          hint: f.hint,
          excerpt: f.excerpt
        };
      }),
      suppressed: (report.suppressed || []).map(function (s) {
        return { ruleId: s.finding.ruleId, line: s.finding.line, reason: s.reason, message: s.finding.message };
      }),
      variables: report.variables.map(function (v) {
        return { name: v.name, raw: v.raw, count: v.count, lines: v.lines };
      }),
      budget: report.budget || null
    }, null, 2);
  }

  // ---------------- SARIF ----------------

  function toSARIF(report, opts) {
    var options = opts || {};
    var uri = options.uri || 'prompt.md';
    var ruleOrder = [];
    var ruleIndex = Object.create(null);

    report.findings.forEach(function (f) {
      if (ruleIndex[f.ruleId] == null) {
        ruleIndex[f.ruleId] = ruleOrder.length;
        ruleOrder.push(f.ruleId);
      }
    });

    var rules = ruleOrder.map(function (id) {
      var first = report.findings.filter(function (f) { return f.ruleId === id; })[0];
      return {
        id: id,
        name: id.replace(/^PG/, 'PromptGate'),
        shortDescription: { text: first.ruleTitle },
        fullDescription: { text: first.hint },
        defaultConfiguration: { level: SARIF_LEVEL[first.severity] || 'warning' },
        helpUri: TOOL.uri + '#规则表'
      };
    });

    var results = report.findings.map(function (f) {
      return {
        ruleId: f.ruleId,
        ruleIndex: ruleIndex[f.ruleId],
        level: SARIF_LEVEL[f.severity] || 'warning',
        message: { text: f.message + (f.hint ? '（建议：' + f.hint + '）' : '') },
        locations: [{
          physicalLocation: {
            artifactLocation: { uri: uri },
            region: {
              startLine: Math.max(1, f.line | 0),
              startColumn: 1,
              snippet: f.excerpt ? { text: f.excerpt } : undefined
            }
          }
        }],
        properties: { category: f.category, severity: f.severity }
      };
    });

    return {
      $schema: 'https://json.schemastore.org/sarif-2.1.0.json',
      version: '2.1.0',
      runs: [{
        tool: {
          driver: {
            name: TOOL.name,
            version: TOOL.version,
            informationUri: TOOL.uri,
            rules: rules
          }
        },
        invocations: [{
          executionSuccessful: true,
          endTimeUtc: new Date(report.meta.generatedAt || Date.now()).toISOString()
        }],
        results: results
      }]
    };
  }

  function toSARIFString(report, opts) {
    return JSON.stringify(toSARIF(report, opts), null, 2);
  }

  function filename(report, ext) {
    var d = new Date(report.meta.generatedAt || Date.now());
    var stamp = d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '-' +
      pad(d.getHours()) + pad(d.getMinutes());
    return 'promptgate-' + stamp + '.' + ext;
  }

  return {
    TOOL: TOOL,
    toMarkdown: toMarkdown,
    toJSON: toJSON,
    toSARIF: toSARIF,
    toSARIFString: toSARIFString,
    filename: filename,
    SEVERITY_LABEL: SEVERITY_LABEL,
    SARIF_LEVEL: SARIF_LEVEL,
    fmtTime: fmtTime
  };
}));
