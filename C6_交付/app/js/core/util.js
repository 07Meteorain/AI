/*!
 * PromptGate · core/util
 * 共用小工具。UMD 包装：浏览器挂到 window.PG.util，Node 下可 require（供测试使用）。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.util = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  /** HTML 转义：所有用户输入在插入 DOM 前必须过这里。 */
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** 截断到 n 个字符，超出补省略号（用于证据摘录）。 */
  function clip(text, n) {
    var s = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
    if (s.length <= n) return s;
    return s.slice(0, Math.max(0, n - 1)) + '…';
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        fn.apply(self, args);
      }, wait);
    };
  }

  /** 稳定短 id，用于版本快照。不依赖 crypto，file:// 下也可用。 */
  function shortId(prefix) {
    var stamp = Date.now().toString(36);
    var rand = Math.random().toString(36).slice(2, 6);
    return (prefix || 'id') + '_' + stamp + rand;
  }

  function pad2(n) {
    return (n < 10 ? '0' : '') + n;
  }

  /** 本地时间 yyyy-mm-dd HH:MM:SS，避免依赖 locale。 */
  function formatTime(ms) {
    var d = new Date(ms);
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) + ' ' +
      pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  /** 数字千分位。 */
  function num(n) {
    var v = Number(n);
    if (!isFinite(v)) return '—';
    var s = Math.round(v).toString();
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** 金额：小额保留更多小数，避免显示成 $0.00。 */
  function money(n) {
    var v = Number(n);
    if (!isFinite(v)) return '—';
    if (v === 0) return '$0';
    if (v < 0.001) return '$' + v.toFixed(5);
    if (v < 0.01) return '$' + v.toFixed(4);
    if (v < 0.1) return '$' + v.toFixed(3);
    return '$' + v.toFixed(2);
  }

  function clamp(n, lo, hi) {
    return Math.min(hi, Math.max(lo, Number(n)));
  }

  /** 生成相对于 base 的路径差（用于 GitHub Pages 子路径部署）。 */
  function moduleList() {
    // 仅用于自检脚本，避免把加载顺序散落在多处
    return [
      'js/core/util.js',
      'js/core/parser.js',
      'js/core/tokenizer.js',
      'js/core/diff.js',
      'js/core/rules.js',
      'js/core/gate.js',
      'js/core/exporter.js',
      'js/core/storage.js',
      'js/core/models.js',
      'js/core/samples.js',
      'js/ui.js',
      'js/app.js'
    ];
  }

  return {
    escapeHtml: escapeHtml,
    clip: clip,
    debounce: debounce,
    shortId: shortId,
    formatTime: formatTime,
    num: num,
    money: money,
    clamp: clamp,
    moduleList: moduleList
  };
}));
