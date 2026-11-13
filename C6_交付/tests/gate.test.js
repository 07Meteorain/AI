'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core } = require('./helpers');

const gate = core('gate');

function f(ruleId, severity, message, line) {
  return { ruleId, severity, message, line: line || 1 };
}

test('默认阈值 error：有 error 就 FAIL', () => {
  const g = gate.evaluate([f('PG004', 'error', 'x')], {});
  assert.equal(g.verdict, 'fail');
  assert.equal(g.blocking, 1);
  assert.deepEqual(g.counts, { error: 1, warning: 0, info: 0 });
});

test('只有 warning 时默认 PASS', () => {
  const g = gate.evaluate([f('PG003', 'warning', 'x')], { failOn: 'error' });
  assert.equal(g.verdict, 'pass');
  assert.equal(g.findings.length, 1);
});

test('failOn=warning 时 warning 也会被拦下', () => {
  const g = gate.evaluate([f('PG003', 'warning', 'x')], { failOn: 'warning' });
  assert.equal(g.verdict, 'fail');
  assert.equal(g.blocking, 1);
});

test('failOn=none 时永不拦下', () => {
  const g = gate.evaluate([f('PG004', 'error', 'x')], { failOn: 'none' });
  assert.equal(g.verdict, 'pass');
  assert.equal(g.blocking, 0);
});

test('健康分：按权重扣分，且不出现负数', () => {
  const g1 = gate.evaluate([], {});
  assert.equal(g1.score, 100);
  assert.equal(g1.grade.letter, 'A');

  const g2 = gate.evaluate([f('PG004', 'error', 'a')], {});
  assert.equal(g2.score, 100 - gate.WEIGHT.error);

  const many = [];
  for (let i = 0; i < 20; i++) many.push(f('PG004', 'error', 'm' + i));
  const g3 = gate.evaluate(many, {});
  assert.equal(g3.score, 0, '扣到底就是 0，不能是负数');
  assert.equal(g3.grade.letter, 'D');
});

test('分级边界：90/75/60', () => {
  assert.equal(gate.grade(90).letter, 'A');
  assert.equal(gate.grade(89).letter, 'B');
  assert.equal(gate.grade(75).letter, 'B');
  assert.equal(gate.grade(74).letter, 'C');
  assert.equal(gate.grade(60).letter, 'C');
  assert.equal(gate.grade(59).letter, 'D');
});

test('基线命中：不计入 counts，也不会被丢掉（进 suppressed）', () => {
  const finding = f('PG006', 'warning', '占位符风格混用');
  const fp = gate.fingerprint(finding);
  const g = gate.evaluate([finding], { baseline: [fp] });
  assert.equal(g.findings.length, 0);
  assert.equal(g.suppressedCount, 1);
  assert.equal(g.suppressed[0].reason, 'baseline');
  assert.equal(g.counts.warning, 0);
  assert.equal(g.score, 100);
});

test('指纹不含行号：挪动位置后基线依然有效', () => {
  const a = gate.fingerprint(f('PG006', 'warning', '占位符风格混用', 3));
  const b = gate.fingerprint(f('PG006', 'warning', '占位符风格混用', 99));
  assert.equal(a, b);
});

test('关闭的规则同样进入 suppressed 并标注原因', () => {
  const g = gate.evaluate([f('PG012', 'info', 'x')], { disabled: ['PG012'] });
  assert.equal(g.suppressed[0].reason, 'rule-disabled');
  assert.equal(g.findings.length, 0);
});

test('toBaseline 去重并排序', () => {
  const list = gate.toBaseline([
    f('PG006', 'warning', 'b'),
    f('PG006', 'warning', 'b'),
    f('PG004', 'error', 'a')
  ]);
  assert.deepEqual(list, ['PG004|a', 'PG006|b']);
});

test('penaltyByRule 按扣分降序，同规则取最高级别', () => {
  const rows = gate.penaltyByRule([
    f('PG012', 'info', 'a'),
    f('PG012', 'warning', 'b'),
    f('PG004', 'error', 'c')
  ]);
  assert.equal(rows[0].ruleId, 'PG004');
  assert.equal(rows[0].penalty, gate.WEIGHT.error);
  const p12 = rows.find((r) => r.ruleId === 'PG012');
  assert.equal(p12.count, 2);
  assert.equal(p12.severity, 'warning');
});

test('summary 文案随结论变化', () => {
  assert.match(gate.evaluate([], {}).summary, /没有发现问题/);
  assert.match(gate.evaluate([f('PG004', 'error', 'x')], {}).summary, /门禁未通过/);
});
