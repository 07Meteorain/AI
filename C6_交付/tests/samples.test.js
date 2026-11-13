'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { core, ROOT } = require('./helpers');

const samples = core('samples');
const parser = core('parser');
const rules = core('rules');

test('样本 id 唯一且有标题/描述', () => {
  const ids = new Set();
  samples.SAMPLES.forEach((s) => {
    assert.ok(s.id && !ids.has(s.id), 'id 重复: ' + s.id);
    ids.add(s.id);
    assert.ok(s.title && s.description, s.id + ' 缺标题或描述');
    assert.ok(['ok', 'bad', 'warn'].includes(s.tone), s.id + ' tone 非法');
    assert.ok(s.text.trim().length > 0, s.id + ' 内容为空');
  });
});

test('get() 命中与未命中', () => {
  assert.equal(samples.get('good').id, 'good');
  assert.equal(samples.get('nope'), null);
});

test('合格样本：0 error / 0 warning / 0 info', () => {
  const findings = rules.lint(parser.parsePrompt(samples.get('good').text));
  assert.equal(findings.length, 0, '合格样本不应有任何命中：' +
    findings.map((f) => f.ruleId + '@' + f.line).join(', '));
});

test('反面教材覆盖 10 条以上规则', () => {
  const ids = new Set(rules.lint(parser.parsePrompt(samples.get('bad').text)).map((f) => f.ruleId));
  assert.ok(ids.size >= 10, '实际覆盖 ' + ids.size + ' 条');
});

test('每个样本都能被解析，且行号统计合理', () => {
  samples.SAMPLES.forEach((s) => {
    const m = parser.parsePrompt(s.text);
    assert.ok(m.lineCount >= 1);
    assert.ok(m.stats.chars > 0);
    assert.equal(m.stats.lines, m.lines.length);
  });
});

test('LONG_LINE 足够长以触发 PG015', () => {
  assert.ok(samples.LONG_LINE.length > 400, '实际长度 ' + samples.LONG_LINE.length);
});

test('载入样本不会抛错：renderTemplate 能处理所有样本的变量', () => {
  samples.SAMPLES.forEach((s) => {
    const m = parser.parsePrompt(s.text);
    const values = {};
    m.variables.forEach((v) => { values[v.name] = 'X'; });
    const out = parser.renderTemplate(s.text, values);
    assert.equal(typeof out.text, 'string');
    assert.ok(out.missing.length === 0, s.id + ' 还有未填变量: ' + out.missing.join(','));
  });
});

test('demo 里的示例文件与 samples.js 保持同步（CI 用它们做冒烟）', () => {
  const pairs = [
    ['示例-合格.md', 'good'],
    ['示例-反面.md', 'bad']
  ];
  pairs.forEach(([file, id]) => {
    const full = path.join(ROOT, 'demo', file);
    assert.ok(fs.existsSync(full), '缺少 demo/' + file);
    const text = fs.readFileSync(full, 'utf8').replace(/\r\n/g, '\n');
    assert.equal(text, samples.get(id).text, 'demo/' + file + ' 与 samples.get("' + id + '") 不一致');
  });
});
