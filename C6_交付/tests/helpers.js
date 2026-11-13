'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');

/** 这些模块是 UMD 包装的，Node 下可直接 require（与浏览器同一份代码）。 */
function core(name) {
  return require(path.join(ROOT, 'app', 'js', 'core', name + '.js'));
}

function ui() {
  return require(path.join(ROOT, 'app', 'js', 'ui.js'));
}

function rules() {
  return require(path.join(ROOT, 'app', 'js', 'core', 'rules.js'));
}

/** 内存版 localStorage，行为与浏览器对象一致（含 length/key 的语义）。 */
function fakeBackend() {
  const map = new Map();
  return {
    _map: map,
    getItem(k) { return map.has(k) ? map.get(k) : null; },
    setItem(k, v) { map.set(k, String(v)); },
    removeItem(k) { map.delete(k); },
    key(i) { return Array.from(map.keys())[i] ?? null; },
    get length() { return map.size; }
  };
}

/** 写入第 n 次之后开始抛配额错误。 */
function quotaBackend(limit) {
  const backend = fakeBackend();
  let writes = 0;
  const setItem = backend.setItem.bind(backend);
  backend.setItem = function (k, v) {
    writes++;
    if (writes > limit) {
      const err = new Error('QuotaExceededError');
      err.name = 'QuotaExceededError';
      throw err;
    }
    setItem(k, v);
  };
  return backend;
}

/** 一碰就抛（隐私模式）。 */
function throwingBackend() {
  return {
    getItem() { throw new Error('SecurityError'); },
    setItem() { throw new Error('SecurityError'); },
    removeItem() { throw new Error('SecurityError'); },
    key() { throw new Error('SecurityError'); },
    get length() { throw new Error('SecurityError'); }
  };
}

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix || 'pg-test-'));
}

function writeTemp(dir, name, content) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, content, 'utf8');
  return file;
}

module.exports = { ROOT, core, ui, rules, fakeBackend, quotaBackend, throwingBackend, tempDir, writeTemp };
