'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core } = require('./helpers');

const report = core('report');
const exporter = core('exporter');
const samples = core('samples');
const models = core('models');

function badReport(extra) {
  return report.buildReport(samples.get('bad').text, Object.assign({ now: 1767225600000 }, extra));
}

function goodReport(extra) {
  return report.buildReport(samples.get('good').text, Object.assign({ now: 1767225600000 }, extra));
}

test('报告结构完整：meta/gate/findings/stats/variables/budget/sections', () => {
  const r = badReport();
  assert.equal(r.meta.app, 'PromptGate');
  assert.equal(r.meta.generatedAt, 1767225600000);
  assert.ok(r.gate && r.findings && r.stats && r.variables && r.budget && r.sections);
  assert.equal(r.findings.length, r.gate.findings.length, 'findings 必须与门禁结果一致');
  const severities = r.findings.reduce((acc, f) => {
    acc[f.severity] = (acc[f.severity] || 0) + 1;
    return acc;
  }, {});
  assert.equal(severities.error || 0, r.gate.counts.error);
  assert.equal(severities.warning || 0, r.gate.counts.warning);
  assert.equal(severities.info || 0, r.gate.counts.info);
});

test('门禁阈值与基线在报告层生效', () => {
  const strict = goodReport({ failOn: 'warning' });
  assert.equal(strict.gate.verdict, 'pass');
  const withDisabled = badReport({ disabled: ['PG004'] });
  assert.equal(withDisabled.findings.filter((f) => f.ruleId === 'PG004').length, 0);
  assert.ok(withDisabled.suppressed.some((s) => s.finding.ruleId === 'PG004'));
});

test('预算行数等于模型数，最省的就是最小值', () => {
  const r = badReport();
  assert.equal(r.budget.rows.length, models.DEFAULT_MODELS.length);
  const min = r.budget.rows.reduce((a, b) => (a.monthly <= b.monthly ? a : b));
  assert.equal(r.budget.cheapest.id, min.id);
  const max = r.budget.rows.reduce((a, b) => (a.monthly >= b.monthly ? a : b));
  assert.equal(r.budget.priciest.id, max.id);
  assert.ok(r.budget.spread >= 1);
});

test('假设参数为 0 时月度成本为 0，而不是 NaN', () => {
  const r = goodReport({ assumptions: { callsPerDay: 0, outputTokens: 0, days: 30 } });
  r.budget.rows.forEach((row) => {
    assert.equal(Number.isFinite(row.monthly), true);
    assert.equal(row.monthly, 0);
  });
});

test('自定义价格表覆盖默认值', () => {
  const r = goodReport({
    models: [{ id: 'my-model', label: 'My', vendor: 'X', inPrice: 100, outPrice: 100, ctx: 1000 }],
    assumptions: { callsPerDay: 1, outputTokens: 0, days: 1 }
  });
  assert.equal(r.budget.rows.length, 1);
  assert.equal(r.budget.rows[0].id, 'my-model');
  const expected = (r.stats.tokens * 100) / 1e6;
  assert.ok(Math.abs(r.budget.rows[0].perCall - expected) < 1e-12);
});

test('sections 按 token 降序且覆盖全文', () => {
  const r = badReport();
  assert.ok(r.sections.length >= 1);
  for (let i = 1; i < r.sections.length; i++) {
    assert.ok(r.sections[i - 1].tokens >= r.sections[i].tokens);
  }
});

test('Markdown 报告含结论、规则表与被忽略项', () => {
  const r = badReport({ disabled: ['PG012'] });
  const md = exporter.toMarkdown(r);
  assert.match(md, /# PromptGate 上线体检报告/);
  assert.match(md, /❌ FAIL/);
  assert.match(md, /PG004/);
  assert.match(md, /\| 级别 \| 规则 \| 行 \| 问题 \| 建议 \|/);
  assert.match(md, /## 已忽略/);
  assert.match(md, /## 变量契约/);
  assert.match(md, /## 成本预算/);
  assert.match(md, /文本未上传/);
});

test('Markdown 表格里的竖线被转义，不会破表', () => {
  const r = goodReport();
  r.findings.push({
    ruleId: 'PG999', ruleTitle: '含|竖线', severity: 'info', category: 'x', line: 1,
    message: 'a|b', hint: 'c|d', excerpt: ''
  });
  const md = exporter.toMarkdown(r);
  assert.ok(md.includes('a\\|b'));
});

test('JSON 报告可解析且字段稳定', () => {
  const r = badReport();
  const json = JSON.parse(exporter.toJSON(r));
  assert.equal(json.schema, 'promptgate/report@1');
  assert.equal(json.gate.verdict, 'fail');
  assert.equal(json.findings.length, r.findings.length);
  assert.equal(json.stats.variables, r.variables.length);
  assert.ok(Array.isArray(json.budget.rows));
  assert.match(json.generatedAt, /^\d{4}-\d{2}-\d{2}T/);
});

test('SARIF 2.1.0 结构合法', () => {
  const r = badReport();
  const sarif = exporter.toSARIF(r, { uri: 'prompt.md' });
  assert.equal(sarif.version, '2.1.0');
  assert.match(sarif.$schema, /sarif-2\.1\.0/);
  const run = sarif.runs[0];
  assert.equal(run.tool.driver.name, 'PromptGate');
  assert.equal(run.results.length, r.findings.length);
  assert.equal(run.invocations[0].executionSuccessful, true);

  run.results.forEach((res, i) => {
    assert.equal(res.ruleId, r.findings[i].ruleId);
    assert.ok(['error', 'warning', 'note'].includes(res.level));
    assert.ok(res.ruleIndex >= 0 && res.ruleIndex < run.tool.driver.rules.length);
    assert.equal(run.tool.driver.rules[res.ruleIndex].id, res.ruleId);
    assert.ok(res.locations[0].physicalLocation.region.startLine >= 1);
    assert.equal(res.locations[0].physicalLocation.artifactLocation.uri, 'prompt.md');
  });
});

test('SARIF 级别映射：info → note', () => {
  const r = badReport();
  const info = r.findings.find((f) => f.severity === 'info');
  const sarif = exporter.toSARIF(r);
  const res = sarif.runs[0].results.find((x) => x.ruleId === info.ruleId);
  assert.equal(res.level, 'note');
});

test('通过的 prompt 生成 zero findings 的 SARIF', () => {
  const sarif = exporter.toSARIF(goodReport());
  assert.equal(sarif.runs[0].results.length, 0);
  assert.equal(sarif.runs[0].tool.driver.rules.length, 0);
});

test('文件名带时间戳与扩展名', () => {
  const r = badReport();
  assert.match(exporter.filename(r, 'md'), /^promptgate-\d{8}-\d{4}\.md$/);
  assert.match(exporter.filename(r, 'sarif'), /\.sarif$/);
});
