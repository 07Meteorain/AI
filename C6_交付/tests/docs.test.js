'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const { ROOT, core } = require('./helpers');

function runTool(name, args) {
  return spawnSync(process.execPath, [path.join(ROOT, 'tools', name)].concat(args || []), {
    encoding: 'utf8',
    timeout: 30000
  });
}

test('docs/rules.md 与 rules.js 保持一致（文档漂移检测）', () => {
  const res = runTool('gen_rules_doc.js', ['--check']);
  assert.equal(res.status, 0, res.stderr || res.stdout);
  assert.match(res.stdout, /一致/);
});

test('docs/rules.md 覆盖全部规则 id，且每个 id 都有锚点', () => {
  const md = fs.readFileSync(path.join(ROOT, 'docs', 'rules.md'), 'utf8');
  core('rules').RULES.forEach((r) => {
    assert.ok(md.includes('## ' + r.id + ' · '), r.id + ' 缺少二级标题');
    assert.ok(md.includes('<a id="' + r.id.toLowerCase() + '"></a>'), r.id + ' 缺少锚点');
  });
  assert.match(md, /误报边界/);
});

test('index.html 引用的脚本全部存在（防止线上 404）', () => {
  const html = fs.readFileSync(path.join(ROOT, 'app', 'index.html'), 'utf8');
  const srcs = Array.from(html.matchAll(/<script src="([^"]+)"/g)).map((m) => m[1]);
  assert.ok(srcs.length >= 10, '脚本数量异常: ' + srcs.length);
  srcs.forEach((src) => {
    const file = path.join(ROOT, 'app', src);
    assert.ok(fs.existsSync(file), '缺少脚本: ' + src);
  });
  const links = Array.from(html.matchAll(/<link rel="(?:stylesheet|manifest|icon)[^"]*" href="([^"]+)"/g)).map((m) => m[1]);
  links.forEach((href) => {
    assert.ok(fs.existsSync(path.join(ROOT, 'app', href)), '缺少资源: ' + href);
  });
});

test('service worker 的预缓存清单与实际文件一致', () => {
  const sw = fs.readFileSync(path.join(ROOT, 'app', 'sw.js'), 'utf8');
  const listed = Array.from(sw.matchAll(/'((?:js|assets)\/[^']+)'/g)).map((m) => m[1]);
  assert.ok(listed.length >= 12, '预缓存清单太少: ' + listed.length);
  listed.forEach((rel) => {
    assert.ok(fs.existsSync(path.join(ROOT, 'app', rel)), 'sw.js 列了不存在的文件: ' + rel);
  });
});

test('README 里引用的仓库内文件都存在', () => {
  const md = fs.readFileSync(path.join(ROOT, 'README.md'), 'utf8');
  const links = Array.from(md.matchAll(/\]\((?!https?:)([^)#]+)\)/g)).map((m) => m[1]);
  const missing = links.filter((rel) => !fs.existsSync(path.join(ROOT, decodeURI(rel))));
  assert.deepEqual(missing, [], 'README 里有失效链接: ' + missing.join(', '));
});

test('每个 JS 文件都能通过语法检查（node --check）', () => {
  const files = [];
  const walk = (dir) => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.js')) files.push(full);
    });
  };
  walk(path.join(ROOT, 'app'));
  walk(path.join(ROOT, 'tools'));
  files.forEach((file) => {
    const res = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    assert.equal(res.status, 0, file + ' 语法错误: ' + res.stderr);
  });
});
