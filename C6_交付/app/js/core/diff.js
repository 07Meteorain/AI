/*!
 * PromptGate · core/diff
 * 行级 LCS diff，用于版本对比。纯函数，O(n*m) 内存，prompt 规模足够。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.diff = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function toLines(text) {
    return String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n');
  }

  /**
   * 返回 diff 行数组：{type:'context'|'add'|'del', text, aLine, bLine}
   */
  function diffLines(oldText, newText) {
    var a = toLines(oldText);
    var b = toLines(newText);
    var n = a.length;
    var m = b.length;

    // 大文本保护：超过 2000 行退化为前缀/后缀比较，避免卡死浏览器
    if (n > 2000 || m > 2000) return coarseDiff(a, b);

    var dp = [];
    for (var i = 0; i <= n; i++) {
      dp.push(new Int32Array(m + 1));
    }
    for (i = n - 1; i >= 0; i--) {
      for (var j = m - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }

    var out = [];
    var x = 0;
    var y = 0;
    while (x < n && y < m) {
      if (a[x] === b[y]) {
        out.push({ type: 'context', text: a[x], aLine: x + 1, bLine: y + 1 });
        x++;
        y++;
      } else if (dp[x + 1][y] >= dp[x][y + 1]) {
        out.push({ type: 'del', text: a[x], aLine: x + 1, bLine: null });
        x++;
      } else {
        out.push({ type: 'add', text: b[y], aLine: null, bLine: y + 1 });
        y++;
      }
    }
    while (x < n) { out.push({ type: 'del', text: a[x], aLine: x + 1, bLine: null }); x++; }
    while (y < m) { out.push({ type: 'add', text: b[y], aLine: null, bLine: y + 1 }); y++; }
    return out;
  }

  function coarseDiff(a, b) {
    var out = [];
    var common = 0;
    var limit = Math.min(a.length, b.length);
    while (common < limit && a[common] === b[common]) common++;
    var tailA = a.length;
    var tailB = b.length;
    while (tailA > common && tailB > common && a[tailA - 1] === b[tailB - 1]) { tailA--; tailB--; }

    for (var i = 0; i < common; i++) out.push({ type: 'context', text: a[i], aLine: i + 1, bLine: i + 1 });
    for (i = common; i < tailA; i++) out.push({ type: 'del', text: a[i], aLine: i + 1, bLine: null });
    for (i = common; i < tailB; i++) out.push({ type: 'add', text: b[i], aLine: null, bLine: i + 1 });
    while (tailA < a.length) {
      out.push({ type: 'context', text: a[tailA], aLine: tailA + 1, bLine: tailB + 1 });
      tailA++;
      tailB++;
    }
    out.truncated = '文本超过 2000 行，已降级为前缀/后缀比较';
    return out;
  }

  function stats(diff) {
    var add = 0;
    var del = 0;
    diff.forEach(function (d) {
      if (d.type === 'add') add++;
      else if (d.type === 'del') del++;
    });
    return { added: add, removed: del, changed: add + del, total: diff.length };
  }

  /** 只保留变更行 + 上下文，用于紧凑展示。 */
  function withContext(diff, context) {
    var ctx = context == null ? 2 : context;
    var keep = new Array(diff.length);
    var i, k;
    for (i = 0; i < diff.length; i++) {
      if (diff[i].type !== 'context') {
        for (k = Math.max(0, i - ctx); k <= Math.min(diff.length - 1, i + ctx); k++) keep[k] = true;
      }
    }
    var out = [];
    var gap = false;
    for (i = 0; i < diff.length; i++) {
      if (keep[i]) {
        if (gap) { out.push({ type: 'gap', text: '⋯' }); gap = false; }
        out.push(diff[i]);
      } else {
        gap = true;
      }
    }
    return out;
  }

  return { diffLines: diffLines, stats: stats, withContext: withContext, toLines: toLines };
}));
