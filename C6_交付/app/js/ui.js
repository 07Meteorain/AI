/*!
 * PromptGate · ui
 * 只做「数据 → HTML 字符串」与少量 DOM 工具，不持有状态。
 * 这样所有渲染逻辑都可以在 Node 里跑（tests/ui.test.js 会断言关键输出），
 * 也避免出现「同一个数字在三个地方各算一遍」的经典前端事故。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./core/util'));
  } else {
    root.PG = root.PG || {};
    root.PG.ui = factory(root.PG.util);
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (util) {
  'use strict';

  var esc = util.escapeHtml;
  var SEV_ORDER = { error: 0, warning: 1, info: 2 };

  function num(n) { return util.num(n); }
  function money(n) { return util.money(n); }

  // ---------------- 行号槽 ----------------

  function gutterHtml(model, findings) {
    var worst = Object.create(null);
    (findings || []).forEach(function (f) {
      var cur = worst[f.line];
      if (cur == null || SEV_ORDER[f.severity] < SEV_ORDER[cur]) worst[f.line] = f.severity;
    });
    var out = [];
    for (var i = 0; i < model.lines.length; i++) {
      var no = i + 1;
      var sev = worst[no];
      out.push('<div class="gline' + (sev ? ' sev-' + sev : '') + '" data-line="' + no + '">' + no + '</div>');
    }
    return out.join('');
  }

  // ---------------- 变量条 ----------------

  function varsHtml(variables) {
    if (!variables.length) {
      return '<span class="label">变量</span><span class="var-none">没有 {{占位符}} —— 如果这个 prompt 需要运行时数据，建议改成变量而不是写死示例值。</span>';
    }
    var chips = variables.map(function (v) {
      var bad = !v.valid;
      return '<button class="var-chip' + (bad ? ' bad' : '') + '" data-var="' + esc(v.name) + '" ' +
        'title="第 ' + v.lines.join('、') + ' 行">' + esc(v.raw || ('{{' + v.name + '}}')) +
        '<span class="cnt">×' + v.count + '</span></button>';
    }).join('');
    return '<span class="label">变量 ' + variables.length + '</span>' + chips +
      '<button class="btn tiny" id="btn-preview">渲染预览</button>';
  }

  // ---------------- 问题列表 ----------------

  function issueHtml(f, rules) {
    var rule = (rules && rules[f.ruleId]) || {};
    return '' +
      '<article class="issue sev-' + esc(f.severity) + '" data-line="' + f.line + '" data-rule="' + esc(f.ruleId) + '">' +
        '<div class="issue-top">' +
          '<span class="sev sev-' + esc(f.severity) + '">' + esc(f.severity) + '</span>' +
          '<span class="rid">' + esc(f.ruleId) + '</span>' +
          '<span class="rtitle">' + esc(f.ruleTitle) + '</span>' +
          '<button class="jump" data-action="jump" data-line="' + f.line + '" title="定位到第 ' + f.line + ' 行">第 ' + f.line + ' 行 ↑</button>' +
        '</div>' +
        '<p class="msg">' + esc(f.message) + '</p>' +
        '<p class="hint">' + esc(f.hint) + '</p>' +
        (f.excerpt ? '<pre class="excerpt">' + esc(f.excerpt) + '</pre>' : '') +
        (rule.rationale ? '<details><summary>为什么这是问题</summary><p>' + esc(rule.rationale) + '</p></details>' : '') +
        '<div class="issue-actions">' +
          '<button class="btn tiny ghost" data-action="ignore" data-rule="' + esc(f.ruleId) + '">忽略这一条</button>' +
          '<button class="btn tiny ghost" data-action="disable" data-rule="' + esc(f.ruleId) + '">关闭 ' + esc(f.ruleId) + '</button>' +
        '</div>' +
      '</article>';
  }

  function issuesHtml(report, filter, rules) {
    var findings = report.findings;
    var suppressed = report.suppressed || [];

    if (filter === 'suppressed') {
      if (!suppressed.length) return emptyHtml('🗂️', '没有忽略项', '被「忽略这一条」或规则开关排除的条目会出现在这里。');
      return suppressed.map(function (s) {
        var f = s.finding;
        return '<article class="issue sev-' + esc(f.severity) + '" data-line="' + f.line + '">' +
          '<div class="issue-top">' +
            '<span class="sev sev-' + esc(f.severity) + '">' + esc(f.severity) + '</span>' +
            '<span class="rid">' + esc(f.ruleId) + '</span>' +
            '<span class="rtitle">' + esc(f.message) + '</span>' +
            '<button class="jump" data-action="jump" data-line="' + f.line + '">第 ' + f.line + ' 行 ↑</button>' +
          '</div>' +
          '<p class="hint">' + (s.reason === 'baseline' ? '已被加入基线（不再计入门禁）' : '对应规则已关闭') + '</p>' +
          '</article>';
      }).join('');
    }

    var list = filter === 'all' ? findings : findings.filter(function (f) { return f.severity === filter; });

    if (!list.length) {
      if (!findings.length && filter === 'all') {
        return emptyHtml('✅', '通过：没有发现问题',
          '这段 prompt 已覆盖角色、任务、输出格式、示例与边界，且没有硬编码凭据或注入面。' +
          '可以点右上角「导出」生成一份可提交的体检报告。');
      }
      return emptyHtml('🔍', '该级别下没有条目', '换一个筛选条件看看，或载入一个反面教材对比。');
    }

    return list.map(function (f) { return issueHtml(f, rules); }).join('');
  }

  function emptyHtml(icon, title, text) {
    return '<div class="empty"><div class="big">' + icon + '</div><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p></div>';
  }

  // ---------------- 预算 ----------------

  function budgetRows(report, editable) {
    var rows = report.budget.rows;
    var max = 0;
    rows.forEach(function (r) { max = Math.max(max, r.monthly); });
    return rows.map(function (r) {
      var pct = max > 0 ? Math.round((r.monthly / max) * 100) : 0;
      var isBest = report.budget.cheapest && r.id === report.budget.cheapest.id;
      return '<tr' + (isBest ? ' class="best"' : '') + ' data-model="' + esc(r.id) + '">' +
        '<td>' + esc(r.label) + '</td>' +
        '<td class="muted">' + esc(r.vendor) + '</td>' +
        '<td class="num">' + (editable
          ? '<input type="number" min="0" step="0.01" value="' + r.inPrice + '" data-price="in" data-model="' + esc(r.id) + '">'
          : money(r.inPrice)) + '</td>' +
        '<td class="num">' + (editable
          ? '<input type="number" min="0" step="0.01" value="' + r.outPrice + '" data-price="out" data-model="' + esc(r.id) + '">'
          : money(r.outPrice)) + '</td>' +
        '<td class="num">' + money(r.perCall) + '</td>' +
        '<td class="num">' + money(r.monthly) + '</td>' +
        '<td><div class="bar-cell"><div class="bar"><i style="width:' + pct + '%"></i></div>' +
          '<span class="muted">' + pct + '%</span></div></td>' +
        '</tr>';
    }).join('');
  }

  function sectionBars(report) {
    var sections = report.sections || [];
    if (!sections.length) return '<p class="muted">没有可聚合的小节。</p>';
    var max = sections.reduce(function (a, s) { return Math.max(a, s.tokens); }, 0) || 1;
    return sections.map(function (s) {
      var pct = Math.round((s.tokens / max) * 100);
      return '<div class="bar-row">' +
        '<span class="name" title="' + esc(s.title) + '">' + esc(s.title) + '</span>' +
        '<span class="bar"><i style="width:' + pct + '%"></i></span>' +
        '<span class="val">' + num(s.tokens) + '</span>' +
        '</div>';
    }).join('');
  }

  // ---------------- 版本 ----------------

  function versionHtml(v, index) {
    return '<div class="version" data-id="' + esc(v.id) + '">' +
      '<span class="vbadge ' + (v.verdict === 'pass' ? 'pass' : 'fail') + '">' +
        (v.verdict === 'pass' ? 'PASS' : 'FAIL') + '</span>' +
      '<span class="vmsg">' + esc(v.message || '(无说明)') + '</span>' +
      '<span class="vmeta">' + esc(v.time) + ' · ' + num(v.tokens) + ' token · ' +
        v.errorCount + 'e/' + v.warningCount + 'w</span>' +
      '<span class="vacts">' +
        '<button class="btn tiny" data-vact="diff" data-id="' + esc(v.id) + '">对比当前</button>' +
        '<button class="btn tiny ghost" data-vact="restore" data-id="' + esc(v.id) + '">恢复</button>' +
        '<button class="btn tiny ghost danger" data-vact="delete" data-id="' + esc(v.id) + '">删除</button>' +
      '</span>' +
    '</div>';
  }

  function versionsHtml(versions) {
    if (!versions.length) {
      return '<p class="muted">还没有保存过版本。改完一个 prompt 之后按 Ctrl/⌘+S 存一版，' +
        '下次改动就能看到 diff —— 这比凭记忆「感觉变好了」可靠得多。</p>';
    }
    return versions.map(versionHtml).join('');
  }

  function diffHtml(lines) {
    return lines.map(function (d) {
      if (d.type === 'gap') return '<div class="dline gap">⋯</div>';
      var sign = d.type === 'add' ? '+' : d.type === 'del' ? '-' : ' ';
      var ln = d.type === 'add' ? d.bLine : d.aLine;
      return '<div class="dline ' + d.type + '">' +
        '<span class="ln">' + (ln == null ? '' : ln) + '</span>' +
        '<span>' + esc(sign + ' ' + d.text) + '</span></div>';
    }).join('');
  }

  // ---------------- 规则表 ----------------

  function rulesHtml(rules, disabled, query) {
    var q = String(query || '').trim().toLowerCase();
    var list = rules.filter(function (r) {
      if (!q) return true;
      return (r.id + ' ' + r.title + ' ' + r.category + ' ' + r.rationale).toLowerCase().indexOf(q) !== -1;
    });
    if (!list.length) return '<p class="muted">没有匹配的规则。</p>';
    return list.map(function (r) {
      var off = disabled.indexOf(r.id) !== -1;
      return '<div class="rule' + (off ? ' off' : '') + '" data-rule="' + esc(r.id) + '">' +
        '<div class="rule-top">' +
          '<span class="sev sev-' + esc(r.severity) + '">' + esc(r.severity) + '</span>' +
          '<span class="rid">' + esc(r.id) + '</span>' +
          '<span class="rtitle">' + esc(r.title) + '</span>' +
          '<span class="muted" style="font-size:11.5px">' + esc(r.category) + '</span>' +
          '<label class="switch"><input type="checkbox" data-toggle="' + esc(r.id) + '"' + (off ? '' : ' checked') + '> 启用</label>' +
        '</div>' +
        '<p class="rat">' + esc(r.rationale) + '</p>' +
        '<p class="rat"><b>怎么改：</b>' + esc(r.fix) + '</p>' +
        '<div class="examples">' +
          '<div class="bad"><span class="cap">反例</span>' + esc(r.bad) + '</div>' +
          '<div class="good"><span class="cap">正例</span>' + esc(r.good) + '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  // ---------------- 模板库 ----------------

  function samplesHtml(samples) {
    return samples.map(function (s) {
      return '<button class="sample" data-sample="' + esc(s.id) + '">' +
        '<span class="tone ' + esc(s.tone) + '"></span>' +
        '<span><strong>' + esc(s.title) + '</strong><span>' + esc(s.description) + '</span></span>' +
        '</button>';
    }).join('');
  }

  // ---------------- 报告头部 ---------------- 

  function verdictHtml(gate) {
    return {
      badgeClass: gate.verdict === 'pass' ? 'badge-pass' : 'badge-fail',
      badgeText: gate.verdict === 'pass' ? '✓ PASS' : '✗ FAIL',
      score: String(gate.score),
      text: gate.summary
    };
  }

  return {
    gutterHtml: gutterHtml,
    varsHtml: varsHtml,
    issuesHtml: issuesHtml,
    issueHtml: issueHtml,
    emptyHtml: emptyHtml,
    budgetRows: budgetRows,
    sectionBars: sectionBars,
    versionsHtml: versionsHtml,
    versionHtml: versionHtml,
    diffHtml: diffHtml,
    rulesHtml: rulesHtml,
    samplesHtml: samplesHtml,
    verdictHtml: verdictHtml
  };
}));
