/* Recall 核心算法（与 Python 端逐位一致）
   —— 浏览器与 CLI 必须给出同一个 due 日期，否则「今天复习了哪些卡」
      在两边会打架。tests/selftest 用 vectors.js 做对照。 */
(function (global) {
  "use strict";

  var QUALITY = { 1: 2, 2: 3, 3: 4, 4: 5 };
  var MIN_EF = 1.3;
  var LEECH = 8;

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function todayISO(now) {
    var d = now || new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function addDays(iso, days) {
    var p = iso.split("-");
    var t = Date.UTC(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
    t += days * 86400000;
    return new Date(t).toISOString().slice(0, 10);
  }

  function sm2(state, grade, today) {
    var q = QUALITY[grade];
    if (!q) { throw new Error("grade 必须是 1–4，收到 " + grade); }
    var s = state || {};
    var ef = typeof s.ef === "number" ? s.ef : 2.5;
    var reps = s.reps || 0;
    var interval = s.interval || 0;
    var lapses = s.lapses || 0;

    if (q < 3) {
      reps = 0;
      interval = 1;
      lapses += 1;
    } else {
      if (reps === 0) {
        interval = 1;
      } else if (reps === 1) {
        interval = 6;
      } else {
        interval = Math.max(1, Math.floor(interval * ef + 0.5));
      }
      reps += 1;
    }

    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
    ef = Math.max(MIN_EF, Math.round(ef * 10000) / 10000);

    return {
      ef: ef,
      reps: reps,
      interval: interval,
      due: addDays(today, interval),
      lapses: lapses,
      suspended: lapses >= LEECH,
      last_review: today
    };
  }

  function isDue(state, today) {
    return !!(state && !state.suspended && state.due && state.due <= today);
  }

  function dueCount(cards, states, today) {
    var n = 0;
    (cards || []).forEach(function (card) {
      if (isDue(states[card.id], today)) { n += 1; }
    });
    return n;
  }

  function retention(state, today) {
    if (!state || !state.due || !state.interval) { return 0; }
    var due = new Date(state.due + "T00:00:00Z").getTime();
    var now = new Date(today + "T00:00:00Z").getTime();
    var elapsed = Math.max(0, state.interval - Math.round((due - now) / 86400000));
    return Math.round(Math.pow(0.9, elapsed / Math.max(1, state.interval)) * 1000) / 1000;
  }

  global.RecallCore = {
    sm2: sm2,
    isDue: isDue,
    dueCount: dueCount,
    retention: retention,
    todayISO: todayISO,
    addDays: addDays,
    MIN_EF: MIN_EF,
    LEECH: LEECH
  };
})(typeof window !== "undefined" ? window : globalThis);
