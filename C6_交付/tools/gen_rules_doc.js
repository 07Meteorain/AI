#!/usr/bin/env node
/*!
 * 从 app/js/core/rules.js 生成 docs/rules.md。
 *
 * 为什么要有这个脚本：规则说明散落在「代码注释 / README / 文档」三处，
 * 半年后必然对不上。这里让代码成为唯一来源，CI 里跑一次 `git diff --exit-code docs/rules.md`
 * 就能发现「改了规则忘了改文档」。
 *
 *   node tools/gen_rules_doc.js          # 写入 docs/rules.md
 *   node tools/gen_rules_doc.js --check  # 只校验，不写入（CI 用）
 */
'use strict';

var fs = require('fs');
var path = require('path');

var ROOT = path.join(__dirname, '..');
var rules = require(path.join(ROOT, 'app', 'js', 'core', 'rules.js'));

var SEV_LABEL = { error: '❌ error', warning: '⚠️ warning', info: 'ℹ️ info' };

function generate() {
  var lines = [];
  lines.push('# PromptGate 规则表');
  lines.push('');
  lines.push('> 本文件由 `tools/gen_rules_doc.js` 从 `app/js/core/rules.js` 生成，请勿手改。');
  lines.push('> 校验：`node tools/gen_rules_doc.js --check`（CI 会在每次提交时执行）。');
  lines.push('');
  lines.push('共 **' + rules.RULES.length + '** 条规则。每条规则给出：判定条件、为什么是问题、怎么改、正反例。');
  lines.push('');
  lines.push('| 规则 | 级别 | 分类 | 标题 |');
  lines.push('| --- | --- | --- | --- |');
  rules.RULES.forEach(function (r) {
    lines.push('| [' + r.id + '](#' + r.id.toLowerCase() + ') | ' + r.severity + ' | ' + r.category + ' | ' + r.title + ' |');
  });
  lines.push('');
  lines.push('级别含义：**error** 会让门禁直接判 FAIL；**warning** 在 `--fail-on warning` 时才拦；**info** 不拦，只作为改进提示。');
  lines.push('');

  rules.RULES.forEach(function (r) {
    lines.push('<a id="' + r.id.toLowerCase() + '"></a>');
    lines.push('');
    lines.push('## ' + r.id + ' · ' + r.title);
    lines.push('');
    lines.push('- 级别：' + (SEV_LABEL[r.severity] || r.severity));
    lines.push('- 分类：' + r.category);
    lines.push('');
    lines.push('**为什么是问题**');
    lines.push('');
    lines.push(blockquote(r.rationale));
    lines.push('');
    lines.push('**怎么改**');
    lines.push('');
    lines.push(blockquote(r.fix));
    lines.push('');
    lines.push('**反例**');
    lines.push('');
    lines.push(fenced(r.bad));
    lines.push('');
    lines.push('**正例**');
    lines.push('');
    lines.push(fenced(r.good));
    lines.push('');
  });

  lines.push('---');
  lines.push('');
  lines.push('## 误报边界（诚实声明）');
  lines.push('');
  lines.push('- PG002 / PG003 / PG013 / PG014 都是关键词启发式：换一种写法表达同一个意思就可能漏检，反之正常行文也可能被提示。');
  lines.push('- PG012（模糊措辞）只匹配固定词表，不判断语义，「适当」在数学语境里可能是精确用法。');
  lines.push('- PG010 的「变量未隔离」只有在**全文没有任何分隔符**时才报告，属于偏保守的一侧：宁可漏报也不误伤。');
  lines.push('- token 估算（PG015 与「预算」页）是启发式，误差约 ±20%，不是分词器的精确值。');
  lines.push('');
  lines.push('出现误报时的正确做法：用「忽略这一条」把它写入基线（按「规则 + 消息」指纹，不含行号），');
  lines.push('而不是关掉整条规则 —— 基线是个可 review、可提交的文件，关规则则是静默的。');
  lines.push('');

  return lines.join('\n');
}

function blockquote(text) {
  return String(text)
    .split('\n')
    .map(function (line) { return '> ' + line; })
    .join('\n');
}

function fenced(text) {
  return '```text\n' + String(text) + '\n```';
}

function main() {
  var content = generate();
  var target = path.join(ROOT, 'docs', 'rules.md');
  if (process.argv.indexOf('--check') !== -1) {
    var current = '';
    try { current = fs.readFileSync(target, 'utf8'); } catch (e) { current = ''; }
    if (current !== content) {
      console.error('docs/rules.md 与规则定义不一致，请运行：node tools/gen_rules_doc.js');
      process.exit(1);
    }
    console.log('docs/rules.md 与规则定义一致（' + rules.RULES.length + ' 条）');
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content, 'utf8');
  console.log('已生成 docs/rules.md（' + rules.RULES.length + ' 条规则）');
}

main();
