// CSV 解析：回收来的数据表多半是 Excel 导出的（带 BOM、CRLF、引号），要能吃下去。
const test = require("node:test");
const assert = require("node:assert");

const Csv = require("../app/js/core/csv.js");

test("基本解析", () => {
  const rows = Csv.parse("a,b,c\n1,2,3\n4,5,6\n");
  assert.strictEqual(rows.length, 2);
  assert.deepStrictEqual(rows[0], { a: "1", b: "2", c: "3" });
});

test("BOM + CRLF（Excel 默认导出）", () => {
  const rows = Csv.parse("\uFEFFchannel,views\r\nwechat,860\r\nzhihu,4200\r\n");
  assert.strictEqual(rows.length, 2);
  assert.strictEqual(rows[0].channel, "wechat");
  assert.strictEqual(rows[1].views, "4200");
});

test("引号内的逗号与转义引号", () => {
  const rows = Csv.parse('name,note\n"标题, 带逗号","他说 ""不错"" 了"\n');
  assert.deepStrictEqual(rows[0], { name: "标题, 带逗号", note: '他说 "不错" 了' });
});

test("空行被忽略，字段数少的行不报错", () => {
  const rows = Csv.parse("a,b\n\n1\n2,3\n");
  assert.strictEqual(rows.length, 2);
  assert.strictEqual(rows[0].b, "");
});

test("空输入返回空数组", () => {
  assert.deepStrictEqual(Csv.parse(""), []);
  assert.deepStrictEqual(Csv.parse(null), []);
});

test("toCsv 会转义，且能 round-trip", () => {
  const rows = [{ a: 'x,"y"', b: "1" }];
  const text = Csv.toCsv(rows, ["a", "b"]);
  assert.strictEqual(text, 'a,b\n"x,""y""",1');
  assert.deepStrictEqual(Csv.parse(text)[0].a, 'x,"y"');
});
