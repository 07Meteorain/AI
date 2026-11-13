'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core } = require('./helpers');

const tk = core('tokenizer');

test('空文本为 0 token', () => {
  const r = tk.estimateTokens('');
  assert.equal(r.tokens, 0);
  assert.deepEqual(r.range, [0, 2]);
});

test('token 随文本长度单调增长', () => {
  const base = '请把这段话翻译成英文。';
  const one = tk.estimateTokens(base).tokens;
  const ten = tk.estimateTokens(base.repeat(10)).tokens;
  assert.ok(ten > one * 5, '10 倍文本应产生显著更多 token');
});

test('同样 10 个字符的中文比英文吃 token', () => {
  const zh = tk.estimateTokens('中文文本内容示例测试').tokens; // 10 个汉字
  const en = tk.estimateTokens('abcdefghij').tokens; // 1 个 10 字母的单词
  assert.ok(zh > en, '中文 ' + zh + ' 应大于英文 ' + en);
  assert.ok(zh >= 6, '10 个汉字至少 6 token，实际 ' + zh);
});

test('区间包含点估计，且上界更宽（承认估算误差）', () => {
  const r = tk.estimateTokens('Hello 世界，12345 tokens');
  assert.ok(r.range[0] <= r.tokens);
  assert.ok(r.range[1] >= r.tokens);
  assert.ok(r.range[1] - r.tokens >= r.tokens - r.range[0]);
});

test('标点与换行参与计数', () => {
  const plain = tk.estimateTokens('abcabcabc').tokens;
  const punct = tk.estimateTokens('abc,abc,abc.').tokens;
  assert.ok(punct > plain);
});

test('costFor：按每百万 token 单价计算单次成本', () => {
  const c = tk.costFor(1000, 500, { inPrice: 2, outPrice: 8 });
  assert.equal(Math.round(c.perCall * 1e6), Math.round((1000 * 2 + 500 * 8)));
  assert.equal(Math.round(c.per1kCalls * 1e6), Math.round((1000 * 2 + 500 * 8) * 1000));
});

test('monthlyCost：单次 × 每天 × 天数', () => {
  const m = tk.monthlyCost(10000, 0, { inPrice: 1, outPrice: 0 }, 100, 30);
  assert.ok(Math.abs(m.monthly - 30) < 1e-9, '10000 token × $1/M × 100 次 × 30 天 = $30');
  assert.equal(m.calls, 3000);
  assert.equal(m.days, 30);
});

test('monthlyCost：缺省参数不产生 NaN', () => {
  const m = tk.monthlyCost(100, 100, { inPrice: 1, outPrice: 1 });
  assert.ok(isFinite(m.monthly));
  assert.equal(m.calls, 0);
});

test('价格表为空时成本为 0 而不是 NaN', () => {
  const m = tk.monthlyCost(1000, 1000, {}, 10, 30);
  assert.equal(m.monthly, 0);
});

test('estimateBySection 覆盖小节且按 token 降序', () => {
  const parse = core('parser').parsePrompt;
  const model = parse('# A\n' + '短'.repeat(10) + '\n\n# B\n' + '长'.repeat(200) + '\n');
  const sections = tk.estimateBySection(model);
  assert.equal(sections.length, 2);
  assert.equal(sections[0].title, 'B');
  assert.ok(sections[0].tokens > sections[1].tokens);
});

test('estimateByLine 跳过空行', () => {
  const parse = core('parser').parsePrompt;
  const model = parse('a\n\nb\n');
  const lines = tk.estimateByLine(model);
  assert.deepEqual(lines.map((l) => l.line), [1, 3]);
});

test('估算方法带版本名，便于以后替换', () => {
  assert.match(tk.estimateTokens('x').method, /heuristic-v1/);
});
