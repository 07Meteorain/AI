// 唯一持有状态的一层：把 core/* 的纯函数接到 DOM 上。
// 约定：core 里不出现 document，这里不出现业务公式。
(function () {
  "use strict";

  var D = window.C7DATA;
  var TS = window.TitleScore;
  var M = window.Metrics;
  var U = window.Utm;
  var Csv = window.Csv;
  var Ui = window.Ui;

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var STORE_CHECK = "c7.publish.checklist.v1";
  var STORE_AAR = "c7.aar.draft.v1";

  var CHECKLIST = [
    "公众号：正文粘贴后检查首行缩进、代码块与表格是否错位",
    "公众号：封面图 2.35:1，标题不超过 24 字",
    "公众号：自动回复关键词「验收」已配置，链接指向《验收清单》",
    "公众号：原文链接已插入带 utm 的落地页",
    "知乎：首段给出结论，标题改成问题句，文末放仓库链接",
    "小红书：拆成 5 张卡片，首图文字即标题，评论区置顶关键词",
    "即刻：单条发布，第一句当钩子，评论区自取清单",
    "四个渠道的 utm_source 各不相同，且都记录进 数据/utm.csv",
    "发布 24 小时后回收一次数据：阅读 / 读完 / 互动 / 领取",
    "发布 7 天后补第二次数据，写进 AAR 的「预期 vs 实际」",
  ];

  var SHOTS = [
    "01_标题评分.png",
    "02_渠道漏斗.png",
    "03_七日增长.png",
    "04_AB显著性.png",
    "05_正文结构.png",
    "06_仓库事实.png",
  ];

  function store(key, value) {
    try {
      if (value === undefined) {
        var raw = window.localStorage.getItem(key);
        return raw ? JSON.parse(raw) : null;
      }
      window.localStorage.setItem(key, JSON.stringify(value));
      return value;
    } catch (e) {
      return null; // 隐私模式 / file:// 受限时静默降级，不影响主功能
    }
  }

  // ---------------------------------------------------------------- 路由
  function showTab(name) {
    var found = false;
    $$(".view").forEach(function (v) {
      var on = v.id === "view-" + name;
      v.classList.toggle("on", on);
      found = found || on;
    });
    if (!found) {
      $("#view-read").classList.add("on");
      name = "read";
    }
    $$(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.getAttribute("href") === "#" + name);
    });
    document.body.setAttribute("data-tab", name);
  }

  // ---------------------------------------------------------------- 阅读
  function initRead() {
    var frame = $("#articleFrame");
    var fit = $("#fitFrame");
    if (fit) {
      fit.addEventListener("click", function () {
        var h = frame.contentWindow && frame.contentDocument
          ? frame.contentDocument.body.scrollHeight
          : 2400;
        frame.style.height = Math.min(Math.max(h + 40, 800), 20000) + "px";
      });
    }
    var open = $("#openArticle");
    if (open) open.setAttribute("href", "article.html");
  }

  // ---------------------------------------------------------------- 标题实验室
  function scoreInto(el, result) {
    el.innerHTML = Ui.renderScoreCard(result, D.rubric);
  }

  function initTitles() {
    var input = $("#titleInput");
    var card = $("#scoreCard");
    var rows = TS.rank(D.titles.map(function (r) { return r; }));

    scoreInto(card, TS.scoreTitle(input.value, D.rubric));
    input.addEventListener("input", function () {
      scoreInto(card, TS.scoreTitle(input.value, D.rubric));
    });

    $("#titleTable").innerHTML = Ui.renderTitleTable(rows);
    $("#titleCount").textContent = rows.length + " 条";

    var p1 = $("#abP1"), p2 = $("#abP2"), n = $("#abN");
    function ab() {
      var a = parseFloat(p1.value) / 100;
      var b = parseFloat(p2.value) / 100;
      var arm = Math.max(1, Math.round(parseFloat(n.value) / 2));
      if (!isFinite(a) || !isFinite(b) || a <= 0 || b <= 0 || a >= 1 || b >= 1 || a === b) {
        $("#abOut").innerHTML = "<p class='warn'>两组转化率需要是 0–100 之间、且不相等的两个数。</p>";
        return;
      }
      var need = M.abRequired(a, b);
      var power = M.powerAt(arm, a, b);
      var ratio = arm / need;
      $("#abOut").innerHTML =
        "<dl class='kv'>" +
        "<div><dt>每臂所需样本</dt><dd>" + Ui.fmtNum(need) + " 组</dd></div>" +
        "<div><dt>本次每臂可用</dt><dd>" + Ui.fmtNum(arm) + " 组（" + (ratio * 100).toFixed(0) + "% 的所需量）</dd></div>" +
        "<div><dt>该样本量下的功效</dt><dd>" + (power * 100).toFixed(1) + "%</dd></div>" +
        "</dl>" +
        (power >= 0.8
          ? "<p class='ok'>功效 ≥ 80%，这次能判定。</p>"
          : "<p class='warn'>功效低于 80%：样本不足，任何“差异”都可能是噪声。别用这次结果写结论。</p>");
    }
    [p1, p2, n].forEach(function (el) { el.addEventListener("input", ab); });
    ab();
  }

  // ---------------------------------------------------------------- 渠道
  function initChannels() {
    $("#channelCards").innerHTML = Ui.renderChannelCards(D.params, D.channels);

    // UTM
    var base = $("#utmBase");
    var campaign = $("#utmCampaign");
    var out = $("#utmMatrix");
    function render() {
      var res = U.matrix(base.value, campaign.value);
      out.innerHTML = res
        .map(function (r) {
          if (!r.ok) {
            return "<div class='utm-row bad'><b>" + Ui.esc(r.source) + "</b><span>" + Ui.esc(r.errors.join("；")) + "</span></div>";
          }
          return (
            "<div class='utm-row'><b>" + Ui.esc(r.source) + "</b>" +
            "<code>" + Ui.esc(r.url) + "</code>" +
            "<button class='mini' data-copy='" + Ui.esc(r.url) + "'>复制</button></div>"
          );
        })
        .join("");
      $$("[data-copy]", out).forEach(function (btn) {
        btn.addEventListener("click", function () {
          copyText(btn.getAttribute("data-copy"));
          btn.textContent = "已复制";
          setTimeout(function () { btn.textContent = "复制"; }, 1200);
        });
      });
    }
    [base, campaign].forEach(function (el) { el.addEventListener("input", render); });
    render();

    // 发布清单
    var saved = store(STORE_CHECK) || {};
    var box = $("#checklist");
    box.innerHTML = Ui.renderChecklist(CHECKLIST, saved);
    var count = $("#checkDone");
    function refresh() {
      var done = $$("input[type=checkbox]", box).filter(function (i) { return i.checked; }).length;
      count.textContent = done + "/" + CHECKLIST.length;
    }
    refresh();
    box.addEventListener("change", function (e) {
      if (e.target.type !== "checkbox") return;
      var idx = e.target.getAttribute("data-idx");
      var state = store(STORE_CHECK) || {};
      state[idx] = e.target.checked;
      store(STORE_CHECK, state);
      refresh();
    });
    $("#resetCheck").addEventListener("click", function () {
      store(STORE_CHECK, {});
      $$("input[type=checkbox]", box).forEach(function (i) { i.checked = false; });
      refresh();
    });
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () {});
      return;
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }

  // ---------------------------------------------------------------- 数据
  function initData() {
    var main = "公众号";
    var stages = M.funnel(D.params[main]);
    $("#funnelBox").innerHTML = Ui.renderFunnelSvg(stages, Ui.CHANNEL_COLORS[main]);
    $("#funnelNote").textContent =
      "公众号：曝光 " + Ui.fmtNum(stages[0].value) + " → 进入正文 " + Ui.fmtNum(stages[1].value) +
      " → 读完 " + Ui.fmtNum(stages[2].value) + " → 领取清单 " + Ui.fmtNum(stages[4].value) + "。";

    var series = {};
    D.channels.forEach(function (ch) { series[ch] = M.growth(D.params[ch]); });
    $("#growthBox").innerHTML = Ui.renderGrowthSvg(series, D.channels);

    var totalReads = M.totalReads(D.params, D.channels);
    $("#totals").innerHTML =
      "<span><b>" + Ui.fmtNum(totalReads) + "</b> 进入正文（四渠道合计）</span>" +
      "<span><b>" + Ui.fmtNum(D.meta.total_tests) + "</b> 项仓库测试</span>" +
      "<span><b>" + Ui.fmtNum(D.meta.total_commits) + "</b> 次提交</span>";

    var rows = D.facts
      .slice()
      .sort(function (a, b) { return (b.tests_computed || 0) - (a.tests_computed || 0); });
    $("#factsTable").innerHTML =
      "<table class='grid'><thead><tr><th>目录</th><th>文件</th><th>KB</th><th>提交</th><th>测试（实测）</th><th>测试（自报）</th></tr></thead><tbody>" +
      rows
        .map(function (r) {
          return (
            "<tr><td class='mono'>" + Ui.esc(r.scope) + "</td><td>" + (r.files || 0) + "</td><td>" + (r.kb || 0) +
            "</td><td>" + (r.commits || 0) + "</td><td><b>" + (r.tests_computed || 0) + "</b></td><td>" +
            (r.declared_tests === null || r.declared_tests === "" ? "—" : r.declared_tests) + "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table>";

    $("#shots").innerHTML = Ui.renderShots(SHOTS);
  }

  // ---------------------------------------------------------------- 复盘
  function initReview() {
    var ta = $("#aarNotes");
    var saved = store(STORE_AAR);
    ta.value = saved && saved.text ? saved.text : AAR_TEMPLATE;
    var status = $("#aarStatus");
    function save() {
      store(STORE_AAR, { text: ta.value, at: new Date().toISOString() });
      status.textContent = "已保存草稿（本机）";
      setTimeout(function () { status.textContent = ""; }, 1500);
    }
    ta.addEventListener("input", function () {
      window.clearTimeout(ta._t);
      ta._t = window.setTimeout(save, 600);
    });

    $("#aarExport").addEventListener("click", function () {
      download("AAR草稿.md", ta.value, "text/markdown");
    });
    $("#aarClear").addEventListener("click", function () {
      ta.value = AAR_TEMPLATE;
      save();
    });

    var csv = "channel,date,impressions,entered,finished,engagements,leads\n" +
      "wechat,2026-11-16,0,0,0,0,0\n" +
      "zhihu,2026-11-16,0,0,0,0,0\n" +
      "xiaohongshu,2026-11-16,0,0,0,0,0\n" +
      "jike,2026-11-16,0,0,0,0,0\n";
    $("#csvPreview").textContent = csv;
    $("#dlCsv").addEventListener("click", function () {
      download("metrics_template.csv", csv, "text/csv");
    });
    $("#checkCsv").addEventListener("click", function () {
      var rows = Csv.parse($("#csvPaste").value);
      $("#csvResult").innerHTML = rows.length
        ? "<p class='ok'>解析到 " + rows.length + " 行：" + Object.keys(rows[0]).join(" / ") + "</p>"
        : "<p class='warn'>没解析出数据行。第一行要是表头。</p>";
    });
  }

  function download(name, text, mime) {
    var blob = new Blob([text], { type: mime + ";charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  var AAR_TEMPLATE = [
    "# AAR 复盘（发布后填写）",
    "",
    "## 1. 预期（发布前写下，不许事后改）",
    "- 目标阅读量：",
    "- 目标领取数：",
    "- 最想验证的一个判断：",
    "",
    "## 2. 实际（发布 7 天后）",
    "- 四渠道阅读 / 读完 / 互动 / 领取：",
    "- 与预期差多少：",
    "",
    "## 3. 差距归因（至少写清一条是「我的错」）",
    "-",
    "",
    "## 4. 下次改什么（要具体到一个动作）",
    "-",
  ].join("\n");

  // ---------------------------------------------------------------- 启动
  document.addEventListener("DOMContentLoaded", function () {
    initRead();
    initTitles();
    initChannels();
    initData();
    initReview();

    window.addEventListener("hashchange", function () {
      showTab((location.hash || "#read").slice(1));
    });
    showTab((location.hash || "#read").slice(1));
  });
})();
