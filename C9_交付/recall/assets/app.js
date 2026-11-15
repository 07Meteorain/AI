/* Recall 前端主逻辑：复习 / 审核 / 统计。
   所有卡片文本都通过 textContent 写入，避免把笔记里的 HTML 当代码执行。 */
(function () {
  "use strict";

  var deck = window.RECALL_DECK || { cards: [] };
  var cards = Array.isArray(deck.cards) ? deck.cards : [];
  var STORE_KEY = "recall.states.v1";
  var DECISION_KEY = "recall.decisions.v1";
  var NEW_LIMIT = 20;
  var today = window.RecallCore.todayISO();

  var KIND_LABELS = {
    "heading-question": "标题提问",
    "term-list": "术语定义",
    "definition": "行内定义",
    "explicit-qa": "问答",
    "cloze": "填空",
    "gist": "章节概述"
  };

  function load(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (err) {
      /* 隐私模式下写不进去时，至少本次会话还能用 */
    }
  }

  var states = load(STORE_KEY, {});
  var decisions = load(DECISION_KEY, {});
  var skipped = {};
  var currentTab = "study";

  cards.forEach(function (card) {
    if (card.state && !states[card.id]) { states[card.id] = card.state; }
  });

  function statusOf(card) {
    return decisions[card.id] || card.status || "approved";
  }

  function kindLabel(kind) { return KIND_LABELS[kind] || kind; }

  function sourceLabel(card) {
    return card.source + (card.line ? ":" + card.line : "");
  }

  function make(tag, className, text) {
    var el = document.createElement(tag);
    if (className) { el.className = className; }
    if (text !== undefined) { el.textContent = text; }
    return el;
  }

  function chipClass(kind) {
    return "chip kind-" + String(kind || "").replace(/[^a-z-]/g, "");
  }

  /* ---------------- 复习 ---------------- */

  var session = { queue: [], index: 0, revealed: false, tally: { 1: 0, 2: 0, 3: 0, 4: 0 } };

  function buildQueue() {
    var due = [];
    var fresh = [];
    cards.forEach(function (card) {
      if (statusOf(card) !== "approved") { return; }
      var state = states[card.id];
      if (!state) {
        fresh.push(card);
      } else if (!state.suspended && state.due && state.due <= today) {
        due.push(card);
      }
    });
    due.sort(function (a, b) {
      return String(states[a.id].due).localeCompare(String(states[b.id].due));
    });
    fresh.sort(function (a, b) {
      return (a.source + a.line).localeCompare(b.source + b.line);
    });
    return due.concat(fresh.slice(0, NEW_LIMIT));
  }

  function counts() {
    var due = 0;
    var fresh = 0;
    cards.forEach(function (card) {
      if (statusOf(card) !== "approved") { return; }
      var state = states[card.id];
      if (!state) { fresh += 1; }
      else if (!state.suspended && state.due && state.due <= today) { due += 1; }
    });
    return { due: due, fresh: fresh };
  }

  function startSession() {
    var queue = buildQueue();
    session = { queue: queue, index: 0, revealed: false, tally: { 1: 0, 2: 0, 3: 0, 4: 0 } };
    document.getElementById("study-done").classList.add("hidden");
    renderStudy();
  }

  function renderStudy() {
    var cardEl = document.getElementById("study-card");
    var doneEl = document.getElementById("study-done");
    var emptyEl = document.getElementById("study-empty");
    var counter = document.getElementById("counter");
    var dueNote = document.getElementById("due-note");
    var bar = document.getElementById("progress-bar");

    if (session.queue.length === 0) {
      cardEl.classList.add("hidden");
      doneEl.classList.add("hidden");
      emptyEl.classList.remove("hidden");
      counter.textContent = "0 / 0";
      dueNote.textContent = "";
      bar.style.width = "0%";
      return;
    }

    if (session.index >= session.queue.length) {
      cardEl.classList.add("hidden");
      emptyEl.classList.add("hidden");
      doneEl.classList.remove("hidden");
      var t = session.tally;
      document.getElementById("done-summary").textContent =
        "本轮 " + session.queue.length + " 张：忘记 " + t[1] + " · 困难 " + t[2] +
        " · 记得 " + t[3] + " · 简单 " + t[4] + "。下一批到期日已按 SM-2 排好。";
      counter.textContent = session.queue.length + " / " + session.queue.length;
      bar.style.width = "100%";
      return;
    }

    emptyEl.classList.add("hidden");
    doneEl.classList.add("hidden");
    cardEl.classList.remove("hidden");

    var card = session.queue[session.index];
    var chip = document.getElementById("card-kind");
    chip.textContent = kindLabel(card.kind);
    chip.className = chipClass(card.kind);
    document.getElementById("card-source").textContent = sourceLabel(card);
    document.getElementById("card-prompt").textContent = card.prompt;
    document.getElementById("card-answer").textContent = card.answer;

    var hint = "来源：" + card.heading;
    if (card.kind === "cloze") { hint += " · 答案是一个术语或数字"; }
    document.getElementById("card-hint").textContent = hint;

    document.getElementById("answer-block").classList.toggle("hidden", !session.revealed);
    document.getElementById("study-tip").classList.toggle("hidden", session.revealed);
    document.getElementById("reveal-row").classList.toggle("hidden", session.revealed);
    document.getElementById("grade-row").classList.toggle("hidden", !session.revealed);

    counter.textContent = (session.index + 1) + " / " + session.queue.length;
    var c = counts();
    dueNote.textContent = "到期 " + c.due + " · 新卡 " + c.fresh;
    bar.style.width = (session.index / session.queue.length) * 100 + "%";
  }

  function reveal() {
    if (session.queue.length === 0 || session.index >= session.queue.length) { return; }
    session.revealed = true;
    renderStudy();
  }

  function grade(value) {
    if (!session.revealed || session.index >= session.queue.length) { return; }
    var card = session.queue[session.index];
    states[card.id] = window.RecallCore.sm2(states[card.id], value, today);
    save(STORE_KEY, states);
    session.tally[value] += 1;
    session.index += 1;
    session.revealed = false;
    renderStudy();
  }

  /* ---------------- 审核 ---------------- */

  var auditIndex = 0;

  function decidedCount() {
    var n = 0;
    cards.forEach(function (card) {
      if (decisions[card.id]) { n += 1; }
    });
    return n;
  }

  function nextUndecided(from) {
    for (var i = from; i < cards.length; i += 1) {
      var card = cards[i];
      if (!decisions[card.id] && !skipped[card.id]) { return i; }
    }
    return -1;
  }

  function renderAudit() {
    var cardEl = document.getElementById("audit-card");
    var doneEl = document.getElementById("audit-done");
    var countEl = document.getElementById("audit-count");
    if (!countEl) { return; }
    countEl.textContent = decidedCount() + " / " + cards.length + " 已决定";

    if (cards.length === 0) {
      cardEl.classList.add("hidden");
      doneEl.classList.remove("hidden");
      return;
    }

    var index = nextUndecided(auditIndex);
    if (index < 0) {
      cardEl.classList.add("hidden");
      doneEl.classList.remove("hidden");
      return;
    }
    auditIndex = index;
    var card = cards[index];
    cardEl.classList.remove("hidden");
    doneEl.classList.add("hidden");

    var chip = document.getElementById("audit-kind");
    chip.textContent = kindLabel(card.kind);
    chip.className = chipClass(card.kind);
    document.getElementById("audit-source").textContent = sourceLabel(card);
    document.getElementById("audit-prompt").textContent = card.prompt;
    document.getElementById("audit-answer").textContent = card.answer;
  }

  function decide(status) {
    if (auditIndex >= cards.length) { return; }
    decisions[cards[auditIndex].id] = status;
    save(DECISION_KEY, decisions);
    auditIndex += 1;
    renderAudit();
  }

  function skip() {
    if (auditIndex >= cards.length) { return; }
    skipped[cards[auditIndex].id] = true;
    auditIndex += 1;
    renderAudit();
  }

  function exportDecisions() {
    var approved = [];
    var rejected = [];
    cards.forEach(function (card) {
      if (decisions[card.id] === "approved") { approved.push(card.id); }
      else if (decisions[card.id] === "rejected") { rejected.push(card.id); }
    });
    var payload = {
      version: 1,
      exported: new Date().toISOString(),
      approved: approved,
      rejected: rejected
    };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "recall-decisions.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ---------------- 统计 ---------------- */

  function renderStats() {
    var total = cards.length;
    var approved = 0;
    var rejected = 0;
    var c = counts();
    var kinds = {};
    cards.forEach(function (card) {
      var status = statusOf(card);
      if (status === "approved") {
        approved += 1;
        kinds[card.kind] = (kinds[card.kind] || 0) + 1;
      } else if (status === "rejected") {
        rejected += 1;
      }
    });

    var grid = document.getElementById("stat-cards");
    grid.textContent = "";
    [
      ["总卡片", total],
      ["可复习", approved],
      ["已剔除", rejected],
      ["今天到期", c.due],
      ["未学新卡", c.fresh]
    ].forEach(function (pair) {
      var box = make("div", "stat");
      box.appendChild(make("b", null, String(pair[1])));
      box.appendChild(make("span", null, pair[0]));
      grid.appendChild(box);
    });

    var kindRows = Object.keys(kinds).map(function (kind) {
      return { label: kindLabel(kind), count: kinds[kind] };
    }).sort(function (a, b) { return b.count - a.count; });
    renderBars("kind-bars", kindRows);

    var forecast = [];
    for (var i = 0; i < 7; i += 1) {
      var day = window.RecallCore.addDays(today, i);
      var n = 0;
      cards.forEach(function (card) {
        if (statusOf(card) !== "approved") { return; }
        var state = states[card.id];
        if (state && !state.suspended && state.due === day) { n += 1; }
      });
      forecast.push({ label: i === 0 ? "今天" : day.slice(5), count: n });
    }
    renderBars("forecast", forecast);

    document.getElementById("stats-note").textContent =
      "新卡每轮最多 " + NEW_LIMIT + " 张；未来 7 天只统计已排程的卡。";
  }

  function renderBars(containerId, rows) {
    var container = document.getElementById(containerId);
    container.textContent = "";
    var max = 1;
    rows.forEach(function (row) { max = Math.max(max, row.count); });
    if (rows.length === 0) {
      container.appendChild(make("p", "muted", "暂无数据"));
      return;
    }
    rows.forEach(function (row) {
      var line = make("div", "bar-row");
      line.appendChild(make("span", "label", row.label));
      var track = make("div", "bar-track");
      var fill = make("span", null);
      fill.style.width = Math.round((row.count / max) * 100) + "%";
      track.appendChild(fill);
      line.appendChild(track);
      line.appendChild(make("span", "num", String(row.count)));
      container.appendChild(line);
    });
  }

  /* ---------------- 导航 ---------------- */

  function switchTab(name) {
    currentTab = name;
    var tabs = document.querySelectorAll(".tab");
    for (var i = 0; i < tabs.length; i += 1) {
      tabs[i].classList.toggle("active", tabs[i].getAttribute("data-tab") === name);
    }
    var panels = document.querySelectorAll(".panel");
    for (var j = 0; j < panels.length; j += 1) {
      panels[j].classList.toggle("active", panels[j].id === "tab-" + name);
    }
    try {
      if (window.location.hash !== "#" + name) {
        window.history.replaceState(null, "", "#" + name);
      }
    } catch (err) { /* file:// 下个别浏览器禁止改历史，忽略 */ }
    if (name === "stats") { renderStats(); }
    if (name === "audit") {
      auditIndex = 0;
      skipped = {};
      renderAudit();
    }
    if (name === "study") { renderStudy(); }
  }

  /* ---------------- 事件 ---------------- */

  document.getElementById("reveal-btn").addEventListener("click", reveal);
  document.getElementById("restart-btn").addEventListener("click", startSession);
  document.getElementById("export-btn").addEventListener("click", exportDecisions);
  document.getElementById("keep-btn").addEventListener("click", function () { decide("approved"); });
  document.getElementById("drop-btn").addEventListener("click", function () { decide("rejected"); });
  document.getElementById("skip-btn").addEventListener("click", skip);

  var gradeButtons = document.querySelectorAll("[data-grade]");
  for (var g = 0; g < gradeButtons.length; g += 1) {
    gradeButtons[g].addEventListener("click", function (event) {
      grade(parseInt(event.currentTarget.getAttribute("data-grade"), 10));
    });
  }

  var tabButtons = document.querySelectorAll(".tab");
  for (var t = 0; t < tabButtons.length; t += 1) {
    tabButtons[t].addEventListener("click", function (event) {
      switchTab(event.currentTarget.getAttribute("data-tab"));
    });
  }

  document.addEventListener("keydown", function (event) {
    var tag = (event.target && event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") { return; }
    if (currentTab === "study") {
      if (event.code === "Space" || event.key === "Enter") {
        event.preventDefault();
        if (!session.revealed) { reveal(); }
      } else if (session.revealed && ["1", "2", "3", "4"].indexOf(event.key) >= 0) {
        grade(parseInt(event.key, 10));
      }
    } else if (currentTab === "audit") {
      var key = String(event.key || "").toLowerCase();
      if (key === "k") { decide("approved"); }
      else if (key === "d") { decide("rejected"); }
      else if (key === "s") { skip(); }
    }
  });

  var foot = document.getElementById("foot-meta");
  if (foot) {
    foot.textContent = cards.length + " 张卡 · 生成于 " + (deck.generated || "—") +
      (deck.app_version ? " · v" + deck.app_version : "");
  }

  startSession();

  var initialTab = String(window.location.hash || "").replace("#", "");
  if (["study", "audit", "stats"].indexOf(initialTab) >= 0) {
    switchTab(initialTab);
  }
})();
