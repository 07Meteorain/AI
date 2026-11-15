// 纯渲染层：数据 → HTML/SVG 字符串。不碰 DOM，不持有状态（这样 node 里能直接测）。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Ui = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var DIM_COLORS = {
    hook: "#2f6feb",
    specificity: "#0ea5a5",
    searchability: "#7c3aed",
    platformFit: "#f59e0b",
    credibility: "#10b981",
  };
  var CHANNEL_COLORS = { 公众号: "#2f6feb", 知乎: "#0ea5a5", 小红书: "#f59e0b", 即刻: "#7c3aed" };

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function gradeClass(grade) {
    if (grade === "主推") return "g-strong";
    if (grade === "可用") return "g-ok";
    if (grade === "备选") return "g-mid";
    return "g-bad";
  }

  // 五个维度的横向填充条
  function renderDims(scores, rubric) {
    return rubric.dimensions
      .map(function (d) {
        var val = scores[d.id];
        var pct = Math.max((val / d.max) * 100, 2);
        return (
          '<div class="dim-row">' +
          '<span class="dim-name">' + esc(d.label) + "</span>" +
          '<span class="dim-track"><i style="width:' + pct.toFixed(1) + "%;background:" + DIM_COLORS[d.id] + '"></i></span>' +
          '<span class="dim-val">' + val + "<em>/" + d.max + "</em></span>" +
          "</div>"
        );
      })
      .join("");
  }

  function renderScoreCard(result, rubric) {
    var reasons = (result.reasons || []).slice(0, 6);
    return (
      '<div class="score-head">' +
      '<div class="score-total">' + result.total + '<em>/100</em></div>' +
      '<div class="score-grade ' + gradeClass(result.grade) + '">' + esc(result.grade) + "</div>" +
      '<div class="score-meta">' + result.chars + " 个有效字符（去空白）" + (result.vetoed ? " · 触发一票否决" : "") + "</div>" +
      "</div>" +
      '<div class="dims">' + renderDims(result, rubric) + "</div>" +
      (reasons.length
        ? '<ul class="reasons">' + reasons.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>"
        : "")
    );
  }

  function renderTitleTable(rows) {
    var head =
      "<tr><th>#</th><th>ID</th><th>标题</th><th>钩子</th><th>具体</th><th>检索</th><th>适配</th><th>可信</th><th>总分</th><th>评级</th></tr>";
    var body = rows
      .map(function (r, i) {
        return (
          "<tr>" +
          "<td>" + (i + 1) + "</td>" +
          "<td class='mono'>" + esc(r.id) + "</td>" +
          "<td class='tt'>" + esc(r.title) + "<span class='formula'>" + esc(r.formula) + "</span></td>" +
          "<td>" + r.hook + "</td><td>" + r.specificity + "</td><td>" + r.searchability + "</td>" +
          "<td>" + r.platformFit + "</td><td>" + r.credibility + "</td>" +
          "<td><b>" + r.total + "</b></td>" +
          "<td><span class='grade " + gradeClass(r.grade) + "'>" + esc(r.grade) + "</span></td>" +
          "</tr>"
        );
      })
      .join("");
    return "<table class='grid'><thead>" + head + "</thead><tbody>" + body + "</tbody></table>";
  }

  function renderChannelCards(params, channels) {
    return channels
      .map(function (ch) {
        var p = params[ch];
        return (
          "<article class='card chan' style='--c:" + CHANNEL_COLORS[ch] + "'>" +
          "<h3>" + esc(ch) + "</h3>" +
          "<dl>" +
          "<div><dt>曝光</dt><dd>" + p.exposure + "</dd></div>" +
          "<div><dt>打开率</dt><dd>" + (p.open_rate * 100).toFixed(0) + "%</dd></div>" +
          "<div><dt>进入率</dt><dd>" + (p.click_rate * 100).toFixed(1) + "%</dd></div>" +
          "<div><dt>读完率</dt><dd>" + (p.read_through * 100).toFixed(0) + "%</dd></div>" +
          "<div><dt>互动率</dt><dd>" + (p.engage_rate * 100).toFixed(1) + "%</dd></div>" +
          "<div><dt>转化率</dt><dd>" + (p.convert_rate * 100).toFixed(1) + "%</dd></div>" +
          "</dl></article>"
        );
      })
      .join("");
  }

  // 漏斗：横向条形，宽度按曝光归一
  function renderFunnelSvg(stages, color) {
    var w = 640, h = 46 * stages.length + 24;
    var max = stages[0].value || 1;
    var barMax = 430;
    var rows = stages.map(function (s, i) {
      var y = 16 + i * 46;
      var len = Math.max((s.value / max) * barMax, 6);
      var pct = i === 0 ? "" : " · 上一步的 " + ((s.value / stages[i - 1].value) * 100).toFixed(1) + "%";
      return (
        "<g>" +
        "<text x='0' y='" + (y + 18) + "' class='svg-label'>" + esc(s.label) + "</text>" +
        "<rect x='110' y='" + y + "' width='" + barMax + "' height='26' rx='6' class='svg-track'/>" +
        "<rect x='110' y='" + y + "' width='" + len.toFixed(1) + "' height='26' rx='6' fill='" + color + "'/>" +
        "<text x='" + (110 + barMax + 12) + "' y='" + (y + 19) + "' class='svg-value'>" + fmtNum(s.value) + "</text>" +
        "<text x='110' y='" + (y + 42) + "' class='svg-note'>" + esc(pct) + "</text>" +
        "</g>"
      );
    });
    return '<svg viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="渠道漏斗">' + rows.join("") + "</svg>";
  }

  function renderGrowthSvg(series, channels) {
    var w = 640, h = 330, pad = { l: 46, r: 60, t: 16, b: 66 };
    var maxY = 0;
    channels.forEach(function (ch) {
      series[ch].forEach(function (v) {
        if (v > maxY) maxY = v;
      });
    });
    maxY = Math.ceil(maxY / 100) * 100 || 100;
    var plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
    var grid = [0, 1, 2, 3, 4]
      .map(function (i) {
        var y = pad.t + plotH - (plotH * i) / 4;
        return (
          "<line x1='" + pad.l + "' y1='" + y + "' x2='" + (pad.l + plotW) + "' y2='" + y + "' class='svg-grid'/>" +
          "<text x='" + (pad.l - 8) + "' y='" + (y + 4) + "' class='svg-axis' text-anchor='end'>" +
          Math.round((maxY * i) / 4) + "</text>"
        );
      })
      .join("");

    var xLabels = [0, 1, 2, 3, 4, 5, 6]
      .map(function (d) {
        var x = pad.l + (plotW * d) / 6;
        return "<text x='" + x + "' y='" + (h - 50) + "' class='svg-axis' text-anchor='middle'>D" + (d + 1) + "</text>";
      })
      .join("");

    var lines = channels
      .map(function (ch) {
        var pts = series[ch]
          .map(function (v, d) {
            var x = pad.l + (plotW * d) / 6;
            var y = pad.t + plotH - (plotH * v) / maxY;
            return x.toFixed(1) + "," + y.toFixed(1);
          })
          .join(" ");
        var last = series[ch][6];
        var ly = pad.t + plotH - (plotH * last) / maxY;
        return (
          "<polyline points='" + pts + "' fill='none' stroke='" + CHANNEL_COLORS[ch] + "' stroke-width='2.5'/>" +
          "<circle cx='" + (pad.l + plotW) + "' cy='" + ly.toFixed(1) + "' r='4' fill='" + CHANNEL_COLORS[ch] + "'/>" +
          "<text x='" + (pad.l + plotW + 8) + "' y='" + (ly + 4).toFixed(1) + "' class='svg-value' fill='" + CHANNEL_COLORS[ch] + "'>" +
          Math.round(last) + "</text>"
        );
      })
      .join("");

    var legend = channels
      .map(function (ch, i) {
        var x = pad.l + i * 96;
        return (
          "<rect x='" + x + "' y='" + (h - 30) + "' width='10' height='10' rx='2' fill='" + CHANNEL_COLORS[ch] + "'/>" +
          "<text x='" + (x + 15) + "' y='" + (h - 12) + "' class='svg-axis'>" + esc(ch) + "</text>"
        );
      })
      .join("");

    return (
      '<svg viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="七日累积阅读">' +
      grid + xLabels + lines + legend + "</svg>"
    );
  }

  function renderShots(files) {
    return files
      .map(function (f, i) {
        return (
          "<a class='shot' href='assets/shots/" + esc(f) + "' target='_blank' rel='noopener'>" +
          "<img src='assets/shots/" + esc(f) + "' alt='" + esc(f) + "' loading='lazy'>" +
          "<span>" + (i + 1) + " · " + esc(f.replace(/^\d+_/, "").replace(/\.png$/, "")) + "</span>" +
          "</a>"
        );
      })
      .join("");
  }

  function renderChecklist(items, done) {
    return items
      .map(function (item, i) {
        var checked = done[i] ? " checked" : "";
        return (
          '<label class="check"><input type="checkbox" data-idx="' + i + '"' + checked + ">" +
          "<span>" + esc(item) + "</span></label>"
        );
      })
      .join("");
  }

  function fmtNum(v) {
    var r = Math.abs(v) >= 10 ? Math.round(v) : Math.round(v * 10) / 10;
    return String(r).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  return {
    esc: esc,
    renderDims: renderDims,
    renderScoreCard: renderScoreCard,
    renderTitleTable: renderTitleTable,
    renderChannelCards: renderChannelCards,
    renderFunnelSvg: renderFunnelSvg,
    renderGrowthSvg: renderGrowthSvg,
    renderShots: renderShots,
    renderChecklist: renderChecklist,
    fmtNum: fmtNum,
    DIM_COLORS: DIM_COLORS,
    CHANNEL_COLORS: CHANNEL_COLORS,
  };
});
