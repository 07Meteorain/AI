// UTM 生成器：埋点是最容易"看起来配了其实没配"的一环，所以规则要能测。
const test = require("node:test");
const assert = require("node:assert");

const U = require("../app/js/core/utm.js");

const BASE = "https://07meteorain.github.io/AI/C7/";

test("四个渠道一次生成，source 各不相同", () => {
  const rows = U.matrix(BASE, "c7_acceptance");
  assert.strictEqual(rows.length, 4);
  const sources = rows.map((r) => r.source);
  assert.strictEqual(new Set(sources).size, 4, "source 必须互不相同，否则后台分不开渠道");
  for (const r of rows) {
    assert.ok(r.ok, `${r.source} 生成失败：${r.errors}`);
    const url = new URL(r.url);
    assert.strictEqual(url.searchParams.get("utm_source"), r.source);
    assert.strictEqual(url.searchParams.get("utm_medium"), "social");
    assert.strictEqual(url.searchParams.get("utm_campaign"), "c7_acceptance");
  }
});

test("参数顺序固定（同样的输入永远同样的字符串，方便 diff）", () => {
  const a = U.build(BASE, { source: "wechat", medium: "social", campaign: "c7", content: "body" });
  const b = U.build(BASE, { content: "body", campaign: "c7", medium: "social", source: "wechat" });
  assert.strictEqual(a.url, b.url);
  assert.ok(a.url.indexOf("utm_source=") < a.url.indexOf("utm_medium="));
});

test("重复生成不会叠加参数（重复的 utm 会让统计翻倍）", () => {
  const once = U.build(BASE, { source: "wechat", medium: "social", campaign: "c7" });
  const twice = U.build(once.url, { source: "wechat", medium: "social", campaign: "c7" });
  assert.strictEqual(twice.url, once.url);
  assert.strictEqual((twice.url.match(/utm_source=/g) || []).length, 1);
});

test("拒绝大写与非 ASCII 的 source（统一小写是分组的前提）", () => {
  for (const bad of ["WeChat", "微信", "we-chat", ""]) {
    const r = U.build(BASE, { source: bad });
    assert.strictEqual(r.ok, false, `"${bad}" 应该被拒绝`);
    assert.ok(r.errors.length > 0);
  }
});

test("拒绝非 http(s) 链接", () => {
  const r = U.build("javascript:alert(1)", { source: "wechat" });
  assert.strictEqual(r.ok, false);
  assert.match(r.errors.join(), /http/);
});

test("改 campaign 只动 campaign，其他参数保留", () => {
  const r = U.build(BASE + "?utm_source=wechat&utm_medium=social", { source: "wechat", medium: "social", campaign: "c7_b" });
  const url = new URL(r.url);
  assert.strictEqual(url.searchParams.get("utm_campaign"), "c7_b");
  assert.strictEqual(url.searchParams.get("utm_medium"), "social");
});
