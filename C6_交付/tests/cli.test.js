'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const { ROOT, tempDir, writeTemp, core } = require('./helpers');

const CLI = path.join(ROOT, 'tools', 'promptgate-cli.js');
const samples = core('samples');

function run(args, opts) {
  return spawnSync(process.execPath, [CLI].concat(args), Object.assign({
    encoding: 'utf8',
    timeout: 30000
  }, opts || {}));
}

function fixture(name, text) {
  const dir = tempDir('pg-cli-');
  return writeTemp(dir, name, text);
}

test('合格 prompt：退出码 0', () => {
  const file = fixture('good.md', samples.get('good').text);
  const res = run([file]);
  assert.equal(res.status, 0, res.stderr);
  assert.match(res.stdout, /PASS/);
  assert.match(res.stdout, /没有发现问题/);
});

test('有 error：退出码 1，并打印规则号与行号', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  const res = run([file]);
  assert.equal(res.status, 1);
  assert.match(res.stdout, /FAIL/);
  assert.match(res.stdout, /PG004/);
  assert.match(res.stdout, /L3/);
});

test('--format json 输出可解析的完整报告', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  const res = run([file, '--format', 'json']);
  assert.equal(res.status, 1);
  const json = JSON.parse(res.stdout);
  assert.equal(json.tool.name, 'PromptGate');
  assert.equal(json.gate.verdict, 'fail');
  assert.ok(json.findings.length > 0);
});

test('--format sarif 输出 SARIF 2.1.0', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  const res = run([file, '--format', 'sarif']);
  const sarif = JSON.parse(res.stdout);
  assert.equal(sarif.version, '2.1.0');
  assert.equal(sarif.runs[0].tool.driver.name, 'PromptGate');
  assert.ok(sarif.runs[0].results.length > 0);
});

test('--format markdown 输出报告正文', () => {
  const file = fixture('good.md', samples.get('good').text);
  const res = run([file, '--format', 'markdown']);
  assert.equal(res.status, 0);
  assert.match(res.stdout, /# PromptGate 上线体检报告/);
});

test('--fail-on none 让有 error 的 prompt 也通过', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  assert.equal(run([file, '--fail-on', 'none']).status, 0);
});

test('--fail-on warning 让纯 warning 的 prompt 失败', () => {
  // 31 个字符、有任务动词、没有格式约束 —— 只有 PG003 是 warning，PG001 不会命中
  const file = fixture('warn.md', '你是产品经理，请把下面这段会议记录整理成三条要点，语气正式。');
  const loose = run([file, '--fail-on', 'error']);
  const strict = run([file, '--fail-on', 'warning']);
  assert.equal(loose.status, 0, loose.stdout);
  assert.equal(strict.status, 1, strict.stdout);
});

test('--disable 关闭指定规则', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  const json = JSON.parse(run([file, '--format', 'json', '--disable', 'PG004,PG009']).stdout);
  const ids = json.findings.map((f) => f.ruleId);
  assert.ok(!ids.includes('PG004'));
  assert.ok(!ids.includes('PG009'));
});

test('--save-baseline + --baseline 组合：第二次跑就通过', () => {
  const dir = tempDir('pg-base-');
  const file = writeTemp(dir, 'bad.md', samples.get('bad').text);
  const base = path.join(dir, 'baseline.txt');
  const first = run([file, '--save-baseline', base]);
  assert.equal(first.status, 1);
  assert.ok(fs.existsSync(base));
  const second = run([file, '--baseline', base]);
  assert.equal(second.status, 0, second.stdout);
});

test('--out 写入文件而不是 stdout', () => {
  const dir = tempDir('pg-out-');
  const file = writeTemp(dir, 'good.md', samples.get('good').text);
  const out = path.join(dir, 'report.md');
  const res = run([file, '--format', 'markdown', '--out', out]);
  assert.equal(res.status, 0);
  assert.equal(res.stdout.trim(), '');
  assert.match(fs.readFileSync(out, 'utf8'), /PromptGate 上线体检报告/);
});

test('stdin 也能体检（cat prompt.md | cli -）', () => {
  const res = run(['-', '--format', 'json'], { input: samples.get('bad').text });
  assert.equal(res.status, 1);
  assert.equal(JSON.parse(res.stdout).gate.verdict, 'fail');
});

test('--quiet 只输出结论行', () => {
  const file = fixture('bad.md', samples.get('bad').text);
  const res = run([file, '--quiet']);
  assert.equal(res.status, 1);
  assert.match(res.stdout.trim(), /^FAIL /);
});

test('--list-rules 列出 15 条规则', () => {
  const res = run(['--list-rules']);
  assert.equal(res.status, 0);
  assert.equal((res.stdout.match(/^PG\d{3}/gm) || []).length, 15);
});

test('文件不存在：退出码 2（区分「运行错误」与「体检不合格」）', () => {
  const res = run([path.join(tempDir('pg-none-'), 'nope.md')]);
  assert.equal(res.status, 2);
  assert.match(res.stderr, /读取失败/);
});

test('未知选项：退出码 2', () => {
  const file = fixture('good.md', samples.get('good').text);
  const res = run([file, '--nope']);
  assert.equal(res.status, 2);
  assert.match(res.stderr, /未知选项/);
});

test('--help 打印用法', () => {
  const res = run(['--help']);
  assert.equal(res.status, 0);
  assert.match(res.stdout, /--fail-on/);
  assert.match(res.stdout, /退出码/);
});
