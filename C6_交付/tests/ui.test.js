'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core, ui: loadUi, rules: loadRules } = require('./helpers');

const report = core('report');
const samples = core('samples');
const ui = loadUi();
const rules = loadRules();

function bad() { return report.buildReport(samples.get('bad').text, { now: 1 }); }
function good() { return report.buildReport(samples.get('good').text, { now: 1 }); }

test('行号槽给命中行加级别类名', () => {
  const r = bad();
  const html = ui.gutterHtml(r.model, r.findings);
  assert.match(html, /class="gline sev-error" data-line="3"/);
  assert.match(html, /class="gline" data-line="2"/);
  assert.equal((html.match(/class="gline/g) || []).length, r.model.lines.length);
});

test('问题卡片包含规则号、行号、建议与去定位按钮', () => {
  const r = bad();
  const html = ui.issuesHtml(r, 'all', rules.RULE_INDEX);
  assert.match(html, /data-rule="PG004"/);
  assert.match(html, /第 3 行 ↑/);
  assert.match(html, /为什么这是问题/);
  assert.match(html, /忽略这一条/);
});

test('所有用户可写内容都被转义（XSS 回归）', () => {
  const r = good();
  r.findings.push({
    ruleId: 'PG004', ruleTitle: '<img src=x onerror=alert(1)>', severity: 'error', category: '安全',
    line: 1, message: '<script>alert(2)</script>', hint: '<b onmouseover=alert(3)>x</b>',
    excerpt: '<iframe src="javascript:alert(4)"></iframe>'
  });
  const html = ui.issuesHtml(r, 'all', rules.RULE_INDEX);
  assert.ok(!html.includes('<script>'), '压缩后的 script 标签必须被转义');
  assert.ok(!html.includes('<img'), 'img 标签必须被转义');
  assert.ok(!html.includes('<iframe'), 'iframe 标签必须被转义');
  assert.ok(html.includes('&lt;script&gt;'));
});

test('空结果给出「通过」而不是空白', () => {
  const html = ui.issuesHtml(good(), 'all', rules.RULE_INDEX);
  assert.match(html, /通过：没有发现问题/);
});

test('按级别筛选只留对应条目', () => {
  const r = bad();
  const errors = ui.issuesHtml(r, 'error', rules.RULE_INDEX);
  assert.ok(!/sev-warning">warning/.test(errors));
  const infos = ui.issuesHtml(r, 'info', rules.RULE_INDEX);
  assert.ok(infos.includes('sev-info'));
});

test('已忽略视图列出被基线排除的条目', () => {
  const r = bad();
  const html = ui.issuesHtml(r, 'suppressed', rules.RULE_INDEX);
  if (r.suppressed.length === 0) {
    assert.match(html, /没有忽略项/);
  } else {
    assert.match(html, /已被加入基线|对应规则已关闭/);
  }
});

test('变量条渲染每个变量与出现次数', () => {
  const r = bad();
  const html = ui.varsHtml(r.variables);
  assert.match(html, /data-var="userName"/);
  assert.match(html, /×1/);
  assert.match(html, /渲染预览/);
});

test('没有变量时给出解释而不是空白', () => {
  const html = ui.varsHtml([]);
  assert.match(html, /没有 \{\{占位符\}\}/);
});

test('预算表格标记最省的一行，并给占比条', () => {
  const r = good();
  const html = ui.budgetRows(r, false);
  assert.match(html, /class="best"/);
  assert.match(html, /style="width:\d+%"/);
  assert.equal((html.match(/<tr/g) || []).length, r.budget.rows.length);
});

test('预算表开启编辑后价格变成输入框', () => {
  const html = ui.budgetRows(good(), true);
  assert.match(html, /data-price="in"/);
  assert.match(html, /data-price="out"/);
});

test('规则表支持搜索过滤', () => {
  const all = ui.rulesHtml(rules.RULES, [], '');
  assert.equal((all.match(/class="rule(?: off)?"/g) || []).length, rules.RULES.length);
  const only = ui.rulesHtml(rules.RULES, [], '凭据');
  assert.ok(only.includes('PG004'));
  assert.ok(!only.includes('PG015'));
  const none = ui.rulesHtml(rules.RULES, [], '不存在的关键词zzz');
  assert.match(none, /没有匹配的规则/);
});

test('关闭的规则在列表里带 off 类，且开关未勾选', () => {
  const html = ui.rulesHtml(rules.RULES, ['PG004'], 'PG004');
  assert.match(html, /class="rule off"/);
  assert.ok(!/data-toggle="PG004" checked/.test(html));
});

test('版本列表空态给出操作指引', () => {
  assert.match(ui.versionsHtml([]), /还没有保存过版本/);
});

test('diff 渲染区分增删行', () => {
  const html = ui.diffHtml([
    { type: 'context', text: 'same', aLine: 1, bLine: 1 },
    { type: 'add', text: 'new', aLine: null, bLine: 2 },
    { type: 'del', text: 'old', aLine: 2, bLine: null },
    { type: 'gap', text: '⋯' }
  ]);
  assert.match(html, /dline add/);
  assert.match(html, /dline del/);
  assert.match(html, /dline gap/);
  assert.ok(html.includes('+ new'));
  assert.ok(html.includes('- old'));
});

test('verdict 徽章：通过为绿色类，失败为红色类', () => {
  assert.equal(ui.verdictHtml(good().gate).badgeClass, 'badge-pass');
  assert.equal(ui.verdictHtml(bad().gate).badgeClass, 'badge-fail');
  assert.equal(ui.verdictHtml(bad().gate).score, String(bad().gate.score));
});

test('样本列表每项都带 tone 与 id', () => {
  const html = ui.samplesHtml(samples.SAMPLES);
  samples.SAMPLES.forEach((s) => {
    assert.ok(html.includes('data-sample="' + s.id + '"'), s.id);
  });
  assert.match(html, /class="tone ok"/);
  assert.match(html, /class="tone bad"/);
});
