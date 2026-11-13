#!/usr/bin/env node
/*!
 * PromptGate CLI —— 同一套引擎的命令行入口，可直接接进 pre-commit 或 CI。
 *
 *   node tools/promptgate-cli.js prompt.md
 *   node tools/promptgate-cli.js prompt.md --fail-on warning --format sarif --out report.sarif
 *   cat prompt.md | node tools/promptgate-cli.js -
 *
 * 退出码：0 = 通过；1 = 未通过门禁；2 = 用法/IO 错误。
 */
'use strict';

var fs = require('fs');
var path = require('path');

var ROOT = path.join(__dirname, '..', 'app');
function load(name) { return require(path.join(ROOT, 'js', 'core', name)); }

var parser = load('parser');
var rules = load('rules');
var tokenizer = load('tokenizer');
var gate = load('gate');
var models = load('models');
var exporter = load('exporter');
var report = load('report');

var HELP = [
  'PromptGate v' + report.VERSION + ' — prompt 上线前的静态体检',
  '',
  '用法:',
  '  node tools/promptgate-cli.js <file|-> [options]',
  '',
  '选项:',
  '  --format text|markdown|json|sarif   输出格式（默认 text）',
  '  --out <file>                        写入文件（默认 stdout）',
  '  --fail-on error|warning|none        门禁阈值（默认 error）',
  '  --disable PG004,PG013               关闭指定规则',
  '  --baseline <file>                   读取基线指纹（每行一条）',
  '  --save-baseline <file>              把当前发现写成基线',
  '  --list-rules                        列出全部规则',
  '  --quiet                             只输出结论行',
  '  -h, --help                          显示帮助',
  '',
  '退出码: 0 通过 / 1 未通过 / 2 错误'
].join('\n');

function parseArgs(argv) {
  var out = { format: 'text', failOn: 'error', disable: [], quiet: false };
  var i = 0;
  while (i < argv.length) {
    var a = argv[i];
    if (a === '-h' || a === '--help') out.help = true;
    else if (a === '--list-rules') out.listRules = true;
    else if (a === '--quiet') out.quiet = true;
    else if (a === '--format') out.format = argv[++i];
    else if (a === '--out') out.out = argv[++i];
    else if (a === '--fail-on') out.failOn = argv[++i];
    else if (a === '--disable') out.disable = String(argv[++i] || '').split(',').filter(Boolean);
    else if (a === '--baseline') out.baseline = argv[++i];
    else if (a === '--save-baseline') out.saveBaseline = argv[++i];
    else if (a === '-') out.file = '-'; // 单独的 - 表示从 stdin 读，不是选项
    else if (a.charAt(0) === '-') { out.error = '未知选项: ' + a; }
    else if (!out.file) out.file = a;
    else { out.error = '多余的参数: ' + a; }
    i++;
  }
  return out;
}

function readInput(file) {
  if (file === '-' || !file) return fs.readFileSync(0, 'utf8');
  return fs.readFileSync(file, 'utf8');
}

function readBaseline(file) {
  if (!file) return [];
  try {
    return fs.readFileSync(file, 'utf8')
      .split(/\r?\n/)
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && s.charAt(0) !== '#'; });
  } catch (e) {
    return [];
  }
}

function textReport(rep, file) {
  var lines = [];
  var icon = rep.gate.verdict === 'pass' ? '✅ PASS' : '❌ FAIL';
  lines.push(icon + '  ' + (file || 'stdin'));
  lines.push('  健康分 ' + rep.gate.score + '/100 (' + rep.gate.grade.letter + ') · ' +
    rep.gate.counts.error + ' error / ' + rep.gate.counts.warning + ' warning / ' + rep.gate.counts.info + ' info' +
    ' · 约 ' + rep.stats.tokens + ' token');
  if (!rep.findings.length) {
    lines.push('  没有发现问题。');
    return lines.join('\n');
  }
  lines.push('');
  rep.findings.forEach(function (f) {
    var mark = f.severity === 'error' ? '  ✖' : f.severity === 'warning' ? '  ▲' : '  ·';
    lines.push(mark + ' ' + f.ruleId + '  L' + f.line + '  ' + f.message);
    lines.push('        → ' + f.hint);
  });
  if (rep.suppressed.length) {
    lines.push('');
    lines.push('  （已忽略 ' + rep.suppressed.length + ' 条：规则关闭或命中基线）');
  }
  return lines.join('\n');
}

function main() {
  var args = parseArgs(process.argv.slice(2));
  if (args.error) { console.error(args.error + '\n\n' + HELP); process.exitCode = 2; return; }
  if (args.help) { console.log(HELP); return; }
  if (args.listRules) {
    rules.RULES.forEach(function (r) {
      console.log(r.id + '  ' + r.severity.padEnd(8) + r.category + '  ' + r.title);
    });
    return;
  }
  if (!args.file && process.stdin.isTTY) { console.error(HELP); process.exitCode = 2; return; }

  var text;
  try {
    text = readInput(args.file);
  } catch (e) {
    console.error('读取失败: ' + e.message);
    process.exitCode = 2;
    return;
  }

  var rep = report.buildReport(text, {
    title: args.file ? path.basename(args.file) : 'stdin',
    failOn: args.failOn,
    disabled: args.disable,
    baseline: readBaseline(args.baseline)
  });

  if (args.saveBaseline) {
    var fps = gate.toBaseline(rep.findings);
    fs.writeFileSync(args.saveBaseline, '# PromptGate baseline\n' + fps.join('\n') + '\n', 'utf8');
    console.error('已写入基线 ' + args.saveBaseline + '（' + fps.length + ' 条）');
  }

  var output;
  if (args.format === 'markdown') output = exporter.toMarkdown(rep);
  else if (args.format === 'json') output = exporter.toJSON(rep);
  else if (args.format === 'sarif') output = exporter.toSARIFString(rep, { uri: args.file || 'prompt.md' });
  else output = args.quiet
    ? (rep.gate.verdict === 'pass' ? 'PASS ' : 'FAIL ') + (args.file || 'stdin')
    : textReport(rep, args.file);

  if (args.out) {
    fs.writeFileSync(args.out, output, 'utf8');
    if (!args.quiet) console.error('已写入 ' + args.out);
  } else {
    console.log(output);
  }

  // 用 exitCode 而不是 process.exit()：Windows 上管道输出是异步的，
  // 立刻 exit 会把没来得及 flush 的 JSON/SARIF 截断。
  process.exitCode = rep.gate.verdict === 'pass' ? 0 : 1;
}

main();
