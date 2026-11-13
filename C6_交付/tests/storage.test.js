'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core, fakeBackend, quotaBackend, throwingBackend } = require('./helpers');

const storage = core('storage');

test('基本读写：set/get/remove', () => {
  const s = storage.createStorage(fakeBackend());
  assert.equal(s.isPersistent(), true);
  s.set('a', { x: 1 });
  assert.deepEqual(s.get('a'), { x: 1 });
  s.remove('a');
  assert.equal(s.get('a', 'fallback'), 'fallback');
});

test('带前缀存储，避免污染同域其它应用', () => {
  const backend = fakeBackend();
  const s = storage.createStorage(backend);
  s.set('draft', 'v');
  assert.ok(backend.getItem(storage.PREFIX + 'draft'));
  assert.equal(backend.getItem('draft'), null);
});

test('keys 只返回本命名空间的键', () => {
  const backend = fakeBackend();
  const s = storage.createStorage(backend);
  backend.setItem('别的应用', '1');
  s.set('x', 1);
  s.set('y', 2);
  assert.deepEqual(s.keys().sort(), ['x', 'y']);
  s.clearAll();
  assert.deepEqual(s.keys(), []);
  assert.equal(backend.getItem('别的应用'), '1', '不能删别人的键');
});

test('损坏的 JSON 回退到默认值而不是抛错', () => {
  const backend = fakeBackend();
  const s = storage.createStorage(backend);
  backend.setItem(storage.PREFIX + 'bad', '{not json');
  assert.equal(s.get('bad', 'ok'), 'ok');
});

test('存储不可用（隐私模式）时退化为内存，功能仍可用', () => {
  const s = storage.createStorage(throwingBackend());
  assert.equal(s.isPersistent(), false);
  assert.equal(s.backendKind, 'memory');
  s.set('k', { a: 1 });
  assert.deepEqual(s.get('k'), { a: 1 }, '写进内存后能读出来');
  s.remove('k');
  assert.equal(s.get('k', null), null);
});

test('没有任何 backend 时同样退化为内存', () => {
  const s = storage.createStorage(null);
  assert.equal(s.isPersistent(), false);
  s.set('k', 1);
  assert.equal(s.get('k'), 1);
});

test('配额写满：set 返回 false，但内存副本仍然可读', () => {
  // 构造函数会先做一次写入探测，因此这里允许 2 次
  const s = storage.createStorage(quotaBackend(2));
  assert.equal(s.isPersistent(), true);
  assert.equal(s.set('k1', 'v1'), true);
  const second = s.set('k2', 'v2');
  assert.equal(second, false, '第二次写入应报告失败');
  assert.equal(s.get('k2'), 'v2', '内存兜底仍可读，不丢数据');
});
