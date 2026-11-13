'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { core } = require('./helpers');

const parser = core('parser');
const parse = parser.parsePrompt;

test('空输入不报错，行数为 1', () => {
  const m = parse('');
  assert.equal(m.text, '');
  assert.equal(m.lineCount, 1);
  assert.equal(m.stats.chars, 0);
  assert.deepEqual(m.variables, []);
});

test('CRLF 被归一化，行号从 1 开始', () => {
  const m = parse('a\r\nb\r\nc');
  assert.equal(m.text, 'a\nb\nc');
  assert.equal(m.lineCount, 3);
  assert.equal(m.lines[0].no, 1);
  assert.equal(m.lines[2].text, 'c');
});

test('识别标题、列表、代码围栏与小节', () => {
  const m = parse('# 角色\n你是助手\n\n# 输出\n- a\n- b\n```json\n{"a":1}\n```');
  assert.equal(m.lines[0].kind, 'heading');
  assert.equal(m.lines[0].title, '角色');
  assert.equal(m.lines[4].kind, 'list');
  assert.equal(m.codeBlocks.length, 1);
  assert.equal(m.codeBlocks[0].content, '{"a":1}');
  assert.equal(m.codeBlocks[0].start, 7);
  assert.equal(m.codeBlocks[0].end, 9);
  assert.equal(m.fenceCount, 2);
  assert.equal(m.fenceUnclosed, false);
  assert.deepEqual(m.sections.map((s) => s.title), ['角色', '输出']);
});

test('未闭合围栏被标记，且代码块延伸到文末', () => {
  const m = parse('说明\n```js\nlet a = 1');
  assert.equal(m.fenceCount, 1);
  assert.equal(m.fenceUnclosed, true);
  assert.equal(m.codeBlocks.length, 1);
  assert.equal(m.codeBlocks[0].end, 3);
});

test('围栏里的内层 ``` 视为内容而不是闭合', () => {
  const m = parse('````markdown\n```js\nx\n```\n````');
  assert.equal(m.fenceCount, 4);
  assert.equal(m.fenceUnclosed, false);
  assert.equal(m.codeBlocks[0].content, '```js\nx\n```');
});

test('占位符去重并记录出现次数与行号', () => {
  const m = parse('你好 {{name}}\n再见 {{ name }}\n{{other}}');
  const names = m.variables.map((v) => v.name);
  assert.deepEqual(names, ['name', 'other']);
  const name = m.variables[0];
  assert.equal(name.count, 2);
  assert.deepEqual(name.lines, [1, 2]);
  assert.equal(name.valid, true);
  assert.equal(m.variables[1].count, 1);
});

test('空占位符与非法变量名被标记', () => {
  const m = parse('{{}} {{userName}} {{2fast}}');
  const empty = m.variables.find((v) => v.empty);
  assert.ok(empty, '应识别空占位符');
  assert.equal(m.variables.find((v) => v.name === 'userName').valid, true);
  assert.equal(m.variables.find((v) => v.name === '2fast').valid, false);
});

test('双花括号不会被误判成单花括号风格', () => {
  const m = parse('{{ticket_text}}');
  assert.equal(m.otherStyles.singleBrace.length, 0);
  assert.equal(m.placeholderStyles.doubleBrace, 1);
});

test('其他占位符风格被分别计数', () => {
  const m = parse('a {{x}} b {y} c ${z} d [NAME]');
  assert.equal(m.placeholderStyles.doubleBrace, 1);
  assert.equal(m.placeholderStyles.singleBrace, 1);
  assert.equal(m.placeholderStyles.dollar, 1);
  assert.equal(m.placeholderStyles.bracket, 1);
});

test('代码块内的单花括号不计入风格统计（避免 JSON 误报）', () => {
  const m = parse('{"a": 1}\n```\n{ "b": 2 }\n```');
  assert.equal(m.placeholderStyles.singleBrace, 0);
});

test('renderTemplate 替换变量并报告未填项', () => {
  const r = parser.renderTemplate('你好 {{name}}，{{missing}}', { name: '小明' });
  assert.equal(r.text, '你好 小明，{{missing}}');
  assert.deepEqual(r.missing, ['missing']);
  assert.deepEqual(r.used, ['name', 'missing']);
});

test('renderTemplate 把空字符串视为未填写', () => {
  const r = parser.renderTemplate('{{a}}', { a: '' });
  assert.equal(r.text, '{{a}}');
  assert.deepEqual(r.missing, ['a']);
});

test('统计：CJK 字数、拉丁词数、最长行', () => {
  const m = parse('中文两个 hello world\n第二行');
  assert.equal(m.stats.cjkChars, 7);
  assert.equal(m.stats.latinWords, 2);
  assert.equal(m.stats.maxLineChars, 16);
  assert.equal(m.stats.nonBlankLines, 2);
});

test('URL 与 lineAt 辅助方法', () => {
  const m = parse('见 https://example.com/a?b=1\n第二行');
  assert.equal(m.urls.length, 1);
  assert.equal(m.urls[0].line, 1);
  assert.equal(m.lineAt(99).text, '第二行');
  assert.equal(m.lineAt(0).text, '见 https://example.com/a?b=1');
});
