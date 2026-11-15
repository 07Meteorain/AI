// UTM 链接生成器：渠道埋点的最小可用实现。
// 规则见 数据/指标口径.md：utm_source 必填且只能是小写英文/数字/下划线，
// 目的是让"从哪来"这件事在后台报表里可分组、可对比，而不是一堆 "wechat/WeChat/微信" 混在一起。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Utm = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SLUG = /^[a-z0-9_]+$/;
  var ORDER = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];

  function validate(fields) {
    var errors = [];
    if (!fields.source) errors.push("utm_source 不能为空");
    else if (!SLUG.test(fields.source)) errors.push("utm_source 只能用小写字母、数字、下划线（收到：" + fields.source + "）");
    if (fields.medium && !SLUG.test(fields.medium)) errors.push("utm_medium 只能用小写字母、数字、下划线");
    if (fields.campaign && !SLUG.test(fields.campaign)) errors.push("utm_campaign 只能用小写字母、数字、下划线");
    if (fields.content && !SLUG.test(fields.content)) errors.push("utm_content 只能用小写字母、数字、下划线");
    return errors;
  }

  // 把 base 与 utm 参数拼起来；已有同名参数会被覆盖而不是追加（重复参数会让后台统计翻倍）
  function build(base, fields) {
    var errors = validate(fields);
    if (errors.length) return { ok: false, errors: errors, url: "" };

    var url;
    try {
      url = new URL(base);
    } catch (e) {
      return { ok: false, errors: ["base 不是合法 URL"], url: "" };
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { ok: false, errors: ["只支持 http/https 链接"], url: "" };
    }

    ORDER.forEach(function (key) {
      var value = fields[key.replace("utm_", "")];
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    });
    return { ok: true, errors: [], url: url.toString() };
  }

  // 一次生成一套渠道矩阵，避免"每个渠道手工拼一次"这种一定会漏的事
  function matrix(base, campaign) {
    var presets = [
      { source: "wechat", medium: "social", content: "article_body" },
      { source: "zhihu", medium: "social", content: "answer" },
      { source: "xiaohongshu", medium: "social", content: "card" },
      { source: "jike", medium: "social", content: "post" },
    ];
    return presets.map(function (p) {
      var r = build(base, {
        source: p.source,
        medium: p.medium,
        campaign: campaign || "c7_acceptance",
        content: p.content,
      });
      return { source: p.source, ok: r.ok, url: r.url, errors: r.errors };
    });
  }

  return { build: build, validate: validate, matrix: matrix, ORDER: ORDER };
});
