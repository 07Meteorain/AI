/*!
 * PromptGate · app
 * 状态 + 交互。所有渲染走 PG.ui，所有结论走 PG.report —— 这一层只负责「把事件接上」。
 */
(function () {
  'use strict';

  var PG = window.PG;
  var U = PG.util;
  var S = PG.storage.store;

  var LINE_H = 22;

  var DEFAULTS = {
    failOn: 'error',
    disabled: [],
    baseline: [],
    assumptions: { outputTokens: 800, callsPerDay: 200, days: 30 },
    models: PG.models.clone(PG.models.DEFAULT_MODELS)
  };

  var state = {
    text: '',
    title: '',
    filter: 'all',
    tab: 'check',
    theme: 'dark',
    search: '',
    editingPrice: false,
    report: null,
    versions: [],
    settings: JSON.parse(JSON.stringify(DEFAULTS))
  };

  var el = {};

  // ---------------------------------------------------------------- 启动

  function init() {
    cacheEls();
    loadSettings();
    state.versions = loadVersions();
    var params = parseParams();

    applyTheme(params.theme || S.get('theme', null) || systemTheme());
    loadInitialText(params);

    el.editor.value = state.text;
    wire();
    analyze();
    paintAll();

    if (params.tab) setTab(params.tab);
    if (params.filter) setFilter(params.filter);

    if (!S.isPersistent()) {
      toast('浏览器不允许本地存储：版本、设置、草稿都不会保留', 'bad');
    }
    if (params.sample) {
      var s = PG.samples.get(params.sample);
      if (s) toast('已载入样本：' + s.title, 'ok');
    }
    registerSW();
  }

  function cacheEls() {
    el.editor = document.getElementById('editor');
    el.gutter = document.getElementById('gutter');
    el.issues = document.getElementById('issues');
    el.varsBar = document.getElementById('vars-bar');
    el.docStats = document.getElementById('doc-stats');
    el.badge = document.getElementById('verdict-badge');
    el.score = document.getElementById('score');
    el.gateText = document.getElementById('gate-text');
    el.failOn = document.getElementById('fail-on');
    el.filters = document.getElementById('filters');
    el.samplesModal = document.getElementById('samples-modal');
    el.sampleList = document.getElementById('sample-list');
    el.toastWrap = document.getElementById('toast-wrap');
    el.exportMenu = document.getElementById('export-menu');
    el.btnExport = document.getElementById('btn-export');
    el.budgetTbody = document.querySelector('#budget-table tbody');
    el.versionList = document.getElementById('version-list');
    el.versionCount = document.getElementById('version-count');
    el.diffCard = document.getElementById('diff-card');
    el.diffView = document.getElementById('diff-view');
    el.diffSummary = document.getElementById('diff-summary');
    el.ruleList = document.getElementById('rule-list');
    el.ruleSearch = document.getElementById('rule-search');
  }

  // ---------------------------------------------------------------- 设置

  function loadSettings() {
    var saved = S.get('settings', null);
    var out = JSON.parse(JSON.stringify(DEFAULTS));
    if (saved && typeof saved === 'object') {
      if (['error', 'warning', 'none'].indexOf(saved.failOn) !== -1) out.failOn = saved.failOn;
      if (Array.isArray(saved.disabled)) {
        out.disabled = saved.disabled.filter(function (id) { return !!PG.rules.ruleById(id); });
      }
      if (Array.isArray(saved.baseline)) {
        out.baseline = saved.baseline.filter(function (s) { return typeof s === 'string'; }).slice(0, 500);
      }
      if (saved.assumptions && typeof saved.assumptions === 'object') {
        ['outputTokens', 'callsPerDay', 'days'].forEach(function (k) {
          var n = Number(saved.assumptions[k]);
          if (isFinite(n) && n >= 0) out.assumptions[k] = n;
        });
      }
      if (Array.isArray(saved.models) && saved.models.length) {
        var v = PG.models.validate(saved.models);
        if (v.ok) out.models = v.models;
      }
    }
    state.settings = out;
    el.failOn.value = out.failOn;
  }

  function saveSettings() {
    S.set('settings', state.settings);
  }

  function loadVersions() {
    var list = S.get('versions', []);
    if (!Array.isArray(list)) return [];
    return list.filter(function (v) {
      return v && typeof v.text === 'string' && typeof v.id === 'string';
    }).slice(0, 20);
  }

  function loadInitialText(params) {
    var sample = params.sample ? PG.samples.get(params.sample) : null;
    if (sample) {
      state.text = sample.text;
      state.title = sample.title;
      return;
    }
    var draft = S.get('draft', null);
    if (draft && typeof draft.text === 'string' && draft.text.trim()) {
      state.text = draft.text;
      state.title = draft.title || '';
      return;
    }
    var demo = PG.samples.get('good');
    state.text = demo.text;
    state.title = demo.title;
    S.set('draft', { text: state.text, title: state.title, savedAt: Date.now() });
    setTimeout(function () { toast('已载入一份合格样例，直接改成你的 prompt 就行', 'ok'); }, 400);
  }

  // ---------------------------------------------------------------- 解析 URL

  function parseParams() {
    var out = {};
    var q = String(location.search || '').replace(/^\?/, '');
    q.split('&').forEach(function (pair) {
      if (!pair) return;
      var kv = pair.split('=');
      out[decodeURIComponent(kv[0])] = decodeURIComponent(kv.slice(1).join('=') || '');
    });
    var hash = String(location.hash || '').replace(/^#/, '');
    if (hash) out.tab = hash;
    return out;
  }

  // ---------------------------------------------------------------- 主题

  function systemTheme() {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
    } catch (e) { /* ignore */ }
    return 'dark';
  }

  function applyTheme(theme) {
    state.theme = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', state.theme);
    S.set('theme', state.theme);
  }

  function toggleTheme() {
    applyTheme(state.theme === 'dark' ? 'light' : 'dark');
  }

  // ---------------------------------------------------------------- 分析

  function analyze() {
    try {
      state.report = PG.report.buildReport(state.text, {
        title: state.title,
        failOn: state.settings.failOn,
        disabled: state.settings.disabled,
        baseline: state.settings.baseline,
        models: state.settings.models,
        assumptions: state.settings.assumptions
      });
    } catch (err) {
      state.report = null;
      toast('体检失败：' + (err && err.message), 'bad');
      return;
    }
    if (state.tab === 'budget') paintBudget();
    if (state.tab === 'versions') paintVersions();
  }

  var scheduleAnalyze = U.debounce(function () {
    analyze();
    paintCheck();
    paintBudget();
  }, 150);

  var scheduleSaveDraft = U.debounce(function () {
    S.set('draft', { text: state.text, title: state.title, savedAt: Date.now() });
  }, 600);

  // ---------------------------------------------------------------- 绘制

  function paintAll() {
    paintCheck();
    paintBudget();
    paintVersions();
    paintRules();
  }

  function paintCheck() {
    var rep = state.report;
    if (!rep) return;
    var v = PG.ui.verdictHtml(rep.gate);

    el.badge.className = 'badge ' + v.badgeClass;
    el.badge.textContent = v.badgeText;
    el.score.textContent = v.score;
    el.gateText.textContent = v.text;
    el.gateText.title = v.text;

    el.docStats.textContent = rep.stats.lines + ' 行 · ' + U.num(rep.stats.chars) + ' 字符 · ~' +
      U.num(rep.stats.tokens) + ' token';

    el.gutter.innerHTML = PG.ui.gutterHtml(rep.model, rep.findings);
    el.gutter.scrollTop = el.editor.scrollTop;

    el.varsBar.innerHTML = PG.ui.varsHtml(rep.variables);

    document.getElementById('c-all').textContent = rep.findings.length;
    document.getElementById('c-error').textContent = rep.gate.counts.error;
    document.getElementById('c-warning').textContent = rep.gate.counts.warning;
    document.getElementById('c-info').textContent = rep.gate.counts.info;
    document.getElementById('c-suppressed').textContent = rep.suppressed.length;

    paintIssues();

    document.title = (rep.gate.verdict === 'pass' ? '✓ ' : '✗ ') + 'PromptGate · ' +
      (state.title ? state.title + ' · ' : '') + rep.gate.score + '/100';
  }

  function paintIssues() {
    var rep = state.report;
    if (!rep) return;
    el.issues.innerHTML = PG.ui.issuesHtml(rep, state.filter, PG.rules.RULE_INDEX);
    el.issues.scrollTop = 0;
  }

  function paintBudget() {
    var rep = state.report;
    if (!rep) return;
    document.getElementById('b-tokens').textContent = U.num(rep.stats.tokens);
    document.getElementById('b-price-date').textContent = rep.budget.priceSnapshot;
    el.budgetTbody.innerHTML = PG.ui.budgetRows(rep, state.editingPrice);

    var cheapest = rep.budget.cheapest;
    document.getElementById('b-cheapest').textContent = cheapest
      ? '最省：' + cheapest.label + ' · 月度 ' + U.money(cheapest.monthly) +
        (rep.budget.spread > 0 ? '（最贵差 ' + rep.budget.spread + ' 倍）' : '')
      : '';

    document.getElementById('section-bars').innerHTML = PG.ui.sectionBars(rep);

    var a = rep.budget.assumptions;
    setInputValue('a-output', a.outputTokens);
    setInputValue('a-calls', a.callsPerDay);
    setInputValue('a-days', a.days);
    document.getElementById('a-edit-price').checked = state.editingPrice;
  }

  function setInputValue(id, value) {
    var node = document.getElementById(id);
    if (node && document.activeElement !== node) node.value = value;
  }

  function paintVersions() {
    el.versionList.innerHTML = PG.ui.versionsHtml(state.versions);
    el.versionCount.textContent = state.versions.length ? (state.versions.length + ' / 20') : '';
  }

  function paintRules() {
    document.getElementById('rule-total').textContent = PG.rules.RULES.length;
    el.ruleList.innerHTML = PG.ui.rulesHtml(PG.rules.RULES, state.settings.disabled, state.search);
  }

  function paintSamples() {
    el.sampleList.innerHTML = PG.ui.samplesHtml(PG.samples.SAMPLES);
  }

  // ---------------------------------------------------------------- 交互绑定

  function wire() {
    el.editor.addEventListener('input', function () {
      state.text = el.editor.value;
      state.title = '';
      scheduleAnalyze();
      scheduleSaveDraft();
    });

    el.editor.addEventListener('scroll', function () {
      el.gutter.scrollTop = el.editor.scrollTop;
    });

    // 行号点击 → 选中该行
    el.gutter.addEventListener('click', function (e) {
      var line = e.target.closest('[data-line]');
      if (line) jumpToLine(Number(line.getAttribute('data-line')));
    });

    // 问题列表：全部按钮走事件委托
    el.issues.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var line = Number(btn.getAttribute('data-line'));
      if (action === 'jump') jumpToLine(line);
      else if (action === 'ignore') ignoreFinding(btn.getAttribute('data-rule'), line);
      else if (action === 'disable') disableRule(btn.getAttribute('data-rule'));
    });

    // 变量条
    el.varsBar.addEventListener('click', function (e) {
      var chip = e.target.closest('[data-var]');
      if (chip) {
        var f = state.report.variables.filter(function (v) { return v.name === chip.getAttribute('data-var'); })[0];
        if (f) jumpToLine(f.lines[0]);
        return;
      }
      if (e.target.id === 'btn-preview') openPreview();
    });

    // 筛选
    el.filters.addEventListener('click', function (e) {
      var chip = e.target.closest('[data-filter]');
      if (chip) setFilter(chip.getAttribute('data-filter'));
    });

    el.failOn.addEventListener('change', function () {
      state.settings.failOn = el.failOn.value;
      saveSettings();
      analyze();
      paintCheck();
      toast('门禁阈值已改为 ' + state.settings.failOn, 'ok');
    });

    document.getElementById('btn-reset-suppress').addEventListener('click', function () {
      var n = state.settings.baseline.length + state.settings.disabled.length;
      if (!n) return toast('没有被忽略的条目');
      state.settings.baseline = [];
      state.settings.disabled = [];
      saveSettings();
      analyze();
      paintCheck();
      paintRules();
      toast('已清空 ' + n + ' 条忽略设置', 'ok');
    });

    // 标签页
    document.querySelector('.tabs').addEventListener('click', function (e) {
      var tab = e.target.closest('[data-tab]');
      if (tab) setTab(tab.getAttribute('data-tab'));
    });

    // 顶栏
    document.getElementById('btn-theme').addEventListener('click', toggleTheme);
    document.getElementById('btn-samples').addEventListener('click', openSamples);
    document.getElementById('btn-clear').addEventListener('click', clearEditor);
    document.getElementById('btn-open').addEventListener('click', function () { document.getElementById('file-input').click(); });
    document.getElementById('file-input').addEventListener('change', onFileOpen);

    el.btnExport.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = el.exportMenu.hidden;
      el.exportMenu.hidden = !open;
      el.btnExport.setAttribute('aria-expanded', String(open));
    });
    el.exportMenu.addEventListener('click', function (e) {
      var item = e.target.closest('[data-export]');
      if (!item) return;
      el.exportMenu.hidden = true;
      doExport(item.getAttribute('data-export'));
    });
    document.addEventListener('click', function (e) {
      if (!el.exportMenu.hidden && !e.target.closest('.menu-wrap')) {
        el.exportMenu.hidden = true;
        el.btnExport.setAttribute('aria-expanded', 'false');
      }
    });

    // 模板
    el.samplesModal.addEventListener('click', function (e) {
      if (e.target.closest('[data-close]')) return closeSamples();
      var item = e.target.closest('[data-sample]');
      if (item) loadSample(item.getAttribute('data-sample'));
    });

    // 预算
    document.getElementById('a-output').addEventListener('input', onAssumption);
    document.getElementById('a-calls').addEventListener('input', onAssumption);
    document.getElementById('a-days').addEventListener('input', onAssumption);
    document.getElementById('a-edit-price').addEventListener('change', function (e) {
      state.editingPrice = e.target.checked;
      paintBudget();
    });
    el.budgetTbody.addEventListener('change', function (e) {
      var input = e.target.closest('[data-price]');
      if (!input) return;
      var id = input.getAttribute('data-model');
      var kind = input.getAttribute('data-price');
      var value = Number(input.value);
      if (!isFinite(value) || value < 0) { toast('价格必须是非负数字', 'bad'); paintBudget(); return; }
      state.settings.models = state.settings.models.map(function (m) {
        if (m.id !== id) return m;
        var next = Object.assign({}, m);
        if (kind === 'in') next.inPrice = value; else next.outPrice = value;
        return next;
      });
      saveSettings();
      analyze();
      paintBudget();
    });

    // 版本
    document.getElementById('btn-save-version').addEventListener('click', saveVersion);
    document.getElementById('version-msg').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') saveVersion();
    });
    el.versionList.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-vact]');
      if (!btn) return;
      var id = btn.getAttribute('data-id');
      var act = btn.getAttribute('data-vact');
      if (act === 'diff') showDiff(id);
      else if (act === 'restore') restoreVersion(id);
      else if (act === 'delete') deleteVersion(id);
    });

    // 规则
    el.ruleSearch.addEventListener('input', function () {
      state.search = el.ruleSearch.value;
      paintRules();
    });
    el.ruleList.addEventListener('change', function (e) {
      var box = e.target.closest('[data-toggle]');
      if (!box) return;
      var id = box.getAttribute('data-toggle');
      if (box.checked) {
        state.settings.disabled = state.settings.disabled.filter(function (x) { return x !== id; });
      } else if (state.settings.disabled.indexOf(id) === -1) {
        state.settings.disabled.push(id);
      }
      saveSettings();
      analyze();
      paintCheck();
      paintRules();
      toast((box.checked ? '已启用 ' : '已关闭 ') + id, 'ok');
    });

    // 键盘
    document.addEventListener('keydown', function (e) {
      var meta = e.ctrlKey || e.metaKey;
      var key = (e.key || '').toLowerCase();
      if (meta && key === 's') { e.preventDefault(); saveVersion(); return; }
      if (meta && key === 'k') { e.preventDefault(); el.editor.focus(); return; }
      if (e.key === 'Escape') { closeSamples(); closeDynamicModals(); return; }
      if (meta || e.altKey) return;
      var editing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement && document.activeElement.tagName);
      if (editing) return;
      if (key === 't') { e.preventDefault(); openSamples(); }
      else if (key === 'd') { e.preventDefault(); toggleTheme(); }
    });
  }

  function setTab(name) {
    var valid = ['check', 'budget', 'versions', 'rules'];
    if (valid.indexOf(name) === -1) return;
    state.tab = name;
    valid.forEach(function (t) {
      var panel = document.getElementById('tab-' + t);
      var tab = document.querySelector('.tab[data-tab="' + t + '"]');
      var on = t === name;
      if (panel) { panel.classList.toggle('active', on); panel.hidden = !on; }
      if (tab) { tab.classList.toggle('active', on); tab.setAttribute('aria-selected', String(on)); }
    });
    if (name === 'budget') paintBudget();
    if (name === 'versions') paintVersions();
    if (name === 'rules') paintRules();
    if (name === 'check') paintCheck();
  }

  function setFilter(name) {
    state.filter = name;
    Array.prototype.forEach.call(el.filters.querySelectorAll('[data-filter]'), function (chip) {
      chip.classList.toggle('active', chip.getAttribute('data-filter') === name);
    });
    paintIssues();
  }

  function jumpToLine(no) {
    if (!no || no < 1) return;
    var parts = el.editor.value.split('\n');
    var start = 0;
    var i;
    for (i = 0; i < no - 1 && i < parts.length; i++) start += parts[i].length + 1;
    var end = start + (parts[no - 1] ? parts[no - 1].length : 0);
    el.editor.focus();
    try { el.editor.setSelectionRange(start, end); } catch (err) { /* ignore */ }
    el.editor.scrollTop = Math.max(0, (no - 3) * LINE_H);
    el.gutter.scrollTop = el.editor.scrollTop;
  }

  function findFinding(ruleId, line) {
    if (!state.report) return null;
    return state.report.findings.filter(function (f) {
      return f.ruleId === ruleId && f.line === line;
    })[0] || null;
  }

  function ignoreFinding(ruleId, line) {
    var f = findFinding(ruleId, line);
    if (!f) return;
    var fp = PG.gate.fingerprint(f);
    if (state.settings.baseline.indexOf(fp) === -1) state.settings.baseline.push(fp);
    saveSettings();
    analyze();
    paintCheck();
    toast('已忽略：' + fp.split('|')[0] + '（在「已忽略」里可找回）', 'ok');
  }

  function disableRule(ruleId) {
    if (state.settings.disabled.indexOf(ruleId) === -1) state.settings.disabled.push(ruleId);
    saveSettings();
    analyze();
    paintCheck();
    paintRules();
    toast('已关闭规则 ' + ruleId, 'ok');
  }

  function onAssumption(e) {
    var key = { 'a-output': 'outputTokens', 'a-calls': 'callsPerDay', 'a-days': 'days' }[e.target.id];
    if (!key) return;
    var n = Number(e.target.value);
    if (!isFinite(n) || n < 0) return;
    state.settings.assumptions[key] = n;
    saveSettings();
    analyze();
    paintBudget();
  }

  // ---------------------------------------------------------------- 版本

  function saveVersion() {
    if (!state.text.trim()) return toast('先写点内容再保存', 'bad');
    var rep = state.report;
    var msgInput = document.getElementById('version-msg');
    var message = (msgInput.value || '').trim() || ('v' + (state.versions.length + 1));
    var v = {
      id: U.shortId('v'),
      message: message,
      time: U.formatTime(Date.now()),
      text: state.text,
      title: state.title,
      tokens: rep ? rep.stats.tokens : 0,
      verdict: rep ? rep.gate.verdict : 'pass',
      errorCount: rep ? rep.gate.counts.error : 0,
      warningCount: rep ? rep.gate.counts.warning : 0
    };
    state.versions.unshift(v);
    if (state.versions.length > 20) state.versions = state.versions.slice(0, 20);
    S.set('versions', state.versions);
    msgInput.value = '';
    paintVersions();
    setTab('versions');
    toast('已保存版本：' + message, 'ok');
  }

  function restoreVersion(id) {
    var v = state.versions.filter(function (x) { return x.id === id; })[0];
    if (!v) return;
    if (!window.confirm('恢复会把编辑器内容替换成「' + v.message + '」，当前内容若未保存会丢失。继续？')) return;
    state.text = v.text;
    state.title = v.title || '';
    el.editor.value = state.text;
    S.set('draft', { text: state.text, title: state.title, savedAt: Date.now() });
    analyze();
    paintCheck();
    setTab('check');
    toast('已恢复：' + v.message, 'ok');
  }

  function deleteVersion(id) {
    state.versions = state.versions.filter(function (x) { return x.id !== id; });
    S.set('versions', state.versions);
    paintVersions();
    if (!el.diffCard.hidden) el.diffCard.hidden = true;
    toast('已删除该版本');
  }

  function showDiff(id) {
    var v = state.versions.filter(function (x) { return x.id === id; })[0];
    if (!v) return;
    var d = PG.diff.diffLines(v.text, state.text);
    var st = PG.diff.stats(d);
    el.diffSummary.textContent = '「' + v.message + '」→ 当前：+' + st.added + ' −' + st.removed;
    el.diffView.innerHTML = PG.ui.diffHtml(PG.diff.withContext(d, 2));
    el.diffCard.hidden = false;
    el.diffCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---------------------------------------------------------------- 导出

  function doExport(kind) {
    var rep = state.report;
    if (!rep) return;
    if (kind === 'md') {
      download(PG.exporter.filename(rep, 'md'), PG.exporter.toMarkdown(rep), 'text/markdown');
      toast('已下载 Markdown 报告', 'ok');
    } else if (kind === 'json') {
      download(PG.exporter.filename(rep, 'json'), PG.exporter.toJSON(rep), 'application/json');
      toast('已下载 JSON 结果', 'ok');
    } else if (kind === 'sarif') {
      var uri = (state.title ? state.title.replace(/\s+/g, '-') : 'prompt') + '.md';
      download(PG.exporter.filename(rep, 'sarif'), PG.exporter.toSARIFString(rep, { uri: uri }), 'application/json');
      toast('已下载 SARIF，可直接上传到 GitHub Code Scanning', 'ok');
    } else if (kind === 'copy') {
      copyText(PG.exporter.toMarkdown(rep));
    } else if (kind === 'baseline') {
      var fps = PG.gate.toBaseline(rep.findings);
      if (!fps.length) return toast('当前没有可加入基线的条目');
      fps.forEach(function (fp) {
        if (state.settings.baseline.indexOf(fp) === -1) state.settings.baseline.push(fp);
      });
      saveSettings();
      analyze();
      paintCheck();
      toast('已把 ' + fps.length + ' 条发现加入基线', 'ok');
    }
  }

  function download(name, text, mime) {
    try {
      var blob = new Blob([text], { type: mime + ';charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        URL.revokeObjectURL(url);
        a.remove();
      }, 1000);
    } catch (e) {
      toast('下载失败：' + e.message, 'bad');
    }
  }

  function copyText(text) {
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      ta.remove();
      toast(ok ? '已复制 Markdown' : '复制失败，请手动选中', ok ? 'ok' : 'bad');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast('已复制 Markdown', 'ok');
      }).catch(fallback);
    } else {
      fallback();
    }
  }

  // ---------------------------------------------------------------- 文件与模板

  function onFileOpen(e) {
    var file = e.target.files && e.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      state.text = String(reader.result || '');
      state.title = file.name;
      el.editor.value = state.text;
      S.set('draft', { text: state.text, title: state.title, savedAt: Date.now() });
      analyze();
      paintCheck();
      toast('已载入 ' + file.name, 'ok');
    };
    reader.onerror = function () { toast('读取文件失败', 'bad'); };
    reader.readAsText(file);
    e.target.value = '';
  }

  function clearEditor() {
    if (state.text.trim() && !window.confirm('清空编辑器内容？')) return;
    state.text = '';
    state.title = '';
    el.editor.value = '';
    S.set('draft', { text: '', title: '', savedAt: Date.now() });
    analyze();
    paintCheck();
    el.editor.focus();
  }

  function openSamples() {
    paintSamples();
    el.samplesModal.hidden = false;
    var first = el.sampleList.querySelector('[data-sample]');
    if (first) first.focus();
  }

  function closeSamples() {
    el.samplesModal.hidden = true;
  }

  function loadSample(id) {
    var s = PG.samples.get(id);
    if (!s) return;
    if (state.text.trim() && !window.confirm('载入模板会覆盖当前内容（草稿已自动保存）。继续？')) return;
    state.text = s.text;
    state.title = s.title;
    el.editor.value = state.text;
    S.set('draft', { text: state.text, title: state.title, savedAt: Date.now() });
    closeSamples();
    analyze();
    paintCheck();
    setTab('check');
    toast('已载入：' + s.title, 'ok');
  }

  // ---------------------------------------------------------------- 渲染预览

  function openPreview() {
    var vars = state.report ? state.report.variables : [];
    if (!vars.length) return toast('这段 prompt 没有变量');

    var fields = vars.map(function (v) {
      return '<label style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)">' +
        '<span class="mono">' + U.escapeHtml(v.raw || ('{{' + v.name + '}}')) + '</span>' +
        '<textarea class="input" data-pv="' + U.escapeHtml(v.name) + '" rows="2" ' +
        'style="min-width:240px;resize:vertical"></textarea></label>';
    }).join('');

    var wrap = document.createElement('div');
    wrap.className = 'modal';
    wrap.setAttribute('data-dynamic', 'preview');
    wrap.innerHTML =
      '<div class="modal-backdrop" data-close></div>' +
      '<div class="modal-body" role="dialog" aria-modal="true" aria-labelledby="pv-title">' +
        '<div class="modal-head"><h2 id="pv-title">渲染预览</h2>' +
        '<button class="btn icon ghost" data-close aria-label="关闭">✕</button></div>' +
        '<p class="muted">填上值就能看到 prompt 实际长什么样。空着的变量会保留 {{name}} 原样。</p>' +
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:10px">' + fields + '</div>' +
        '<pre class="excerpt" id="pv-out" style="max-height:38vh;overflow:auto;white-space:pre-wrap;margin-top:14px"></pre>' +
        '<div class="row" style="justify-content:flex-end">' +
          '<button class="btn tiny ghost" data-close>关闭</button>' +
          '<button class="btn tiny" id="pv-copy">复制渲染结果</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(wrap);

    function currentValues() {
      var values = {};
      Array.prototype.forEach.call(wrap.querySelectorAll('[data-pv]'), function (input) {
        values[input.getAttribute('data-pv')] = input.value;
      });
      return values;
    }

    function render() {
      var r = PG.parser.renderTemplate(state.text, currentValues());
      wrap.querySelector('#pv-out').textContent = r.text;
      if (r.missing.length) {
        wrap.querySelector('#pv-out').textContent += '\n\n// 尚未填写的变量：' + r.missing.join('、');
      }
    }

    wrap.addEventListener('input', render);
    wrap.addEventListener('click', function (e) {
      if (e.target.closest('[data-close]')) { wrap.remove(); return; }
      if (e.target.id === 'pv-copy') {
        copyText(wrap.querySelector('#pv-out').textContent);
      }
    });
    render();
    var firstInput = wrap.querySelector('[data-pv]');
    if (firstInput) firstInput.focus();
  }

  function closeDynamicModals() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-dynamic]'), function (n) { n.remove(); });
  }

  // ---------------------------------------------------------------- 提示

  function toast(message, kind) {
    var node = document.createElement('div');
    node.className = 'toast' + (kind ? ' ' + kind : '');
    node.textContent = message;
    el.toastWrap.appendChild(node);
    setTimeout(function () {
      node.style.opacity = '0';
      node.style.transition = 'opacity .2s';
      setTimeout(function () { node.remove(); }, 220);
    }, 2600);
  }

  // ---------------------------------------------------------------- PWA

  function registerSW() {
    if (!('serviceWorker' in navigator)) return;
    if (location.protocol !== 'http:' && location.protocol !== 'https:') return;
    navigator.serviceWorker.register('sw.js').catch(function () { /* 离线缓存失败不影响使用 */ });
  }

  // ---------------------------------------------------------------- go

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
