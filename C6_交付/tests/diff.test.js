'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core } = require('./helpers');

const diff = core('diff');

test('完全相同的文本：全是 context', () => {
  const d = diff.diffLines('a\nb', 'a\nb');
  assert.deepEqual(d.map((x) => x.type), ['context', 'context']);
  assert.deepEqual(diff.stats(d), { added: 0, removed: 0, changed: 0, total: 2 });
});

test('删除一行', () => {
  const d = diff.diffLines('a\nb\nc', 'a\nc');
  const st = diff.stats(d);
  assert.equal(st.removed, 1);
  assert.equal(st.added, 0);
  assert.equal(d.find((x) => x.type === 'del').text, 'b');
});

test('新增一行', () => {
  const d = diff.diffLines('a\nc', 'a\nb\nc');
  const st = diff.stats(d);
  assert.equal(st.added, 1);
  assert.equal(st.removed, 0);
  assert.equal(d.find((x) => x.type === 'add').bLine, 2);
});

test('改写一行 = 一增一删', () => {
  const st = diff.stats(diff.diffLines('a\n旧\nc', 'a\n新\nc'));
  assert.deepEqual([st.added, st.removed], [1, 1]);
});

test('行号映射正确（aLine/bLine 指向各自原文）', () => {
  const d = diff.diffLines('x\na\nb', 'a\nb\ny');
  const add = d.find((x) => x.type === 'add');
  assert.equal(add.bLine, 3);
  assert.equal(add.aLine, null);
  const del = d.find((x) => x.type === 'del');
  assert.equal(del.aLine, 1);
  assert.equal(del.bLine, null);
});

test('CRLF 与 LF 视为相同内容', () => {
  const st = diff.stats(diff.diffLines('a\r\nb', 'a\nb'));
  assert.equal(st.changed, 0);
});

test('withContext 只保留改动附近的行，中间插入省略号', () => {
  const oldText = Array.from({ length: 12 }, (_, i) => 'line' + (i + 1)).join('\n');
  const newText = oldText.replace('line6', 'CHANGED');
  const d = diff.diffLines(oldText, newText);
  const compact = diff.withContext(d, 1);
  assert.ok(compact.some((x) => x.type === 'gap'), '远端应有省略号');
  assert.ok(compact.length < d.length);
  assert.ok(compact.some((x) => x.type === 'add' && x.text === 'CHANGED'));
});

test('withContext 在改动相邻时不插入 gap', () => {
  const d = diff.diffLines('a\nb\nc', 'a\nB\nc');
  const compact = diff.withContext(d, 5);
  assert.ok(!compact.some((x) => x.type === 'gap'));
});

test('空文本对比不抛错', () => {
  const st = diff.stats(diff.diffLines('', 'a'));
  assert.equal(st.added, 1);
  assert.equal(st.removed, 1, '空字符串会占一行，因此表现为一删一增');
});

test('超大文本走降级路径（前缀/后缀比较）', () => {
  const big = Array.from({ length: 2100 }, (_, i) => 'l' + i).join('\n');
  const bigger = big.replace('l1050', 'l1050-changed');
  const d = diff.diffLines(big, bigger);
  assert.equal(d.truncated !== undefined, true);
  assert.ok(diff.stats(d).changed >= 2);
});
