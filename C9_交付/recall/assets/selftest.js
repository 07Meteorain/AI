/* 浏览器端自检：与 Python 的 tests/test_scheduler.py 共用 vectors.js。
   结果写进 <body data-result>，可以用 headless 浏览器 --dump-dom 抓取。 */
(function () {
  "use strict";

  var pass = 0;
  var fail = 0;
  var lines = [];

  function check(name, ok, detail) {
    if (ok) {
      pass += 1;
      lines.push("PASS  " + name);
    } else {
      fail += 1;
      lines.push("FAIL  " + name + (detail ? "  (" + detail + ")" : ""));
    }
  }

  function eq(name, actual, expected) {
    check(name, actual === expected, "expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual));
  }

  var vectors = window.RECALL_VECTORS || [];
  check("vectors.js 已加载", vectors.length > 0, "0 组向量");

  vectors.forEach(function (vector) {
    var state = vector.start;
    vector.steps.forEach(function (step, index) {
      state = window.RecallCore.sm2(state, step.grade, step.day);
      ["ef", "reps", "interval", "due", "lapses", "suspended"].forEach(function (key) {
        eq(vector.name + "#" + (index + 1) + "." + key, state[key], step.state[key]);
      });
    });
  });

  eq("addDays 跨月", window.RecallCore.addDays("2026-01-31", 1), "2026-02-01");
  eq("addDays 跨年", window.RecallCore.addDays("2026-12-31", 1), "2027-01-01");
  eq("addDays 闰年", window.RecallCore.addDays("2028-02-28", 1), "2028-02-29");
  check("todayISO 格式", /^\d{4}-\d{2}-\d{2}$/.test(window.RecallCore.todayISO()));

  eq("isDue 到期", window.RecallCore.isDue({ due: "2026-01-01", suspended: false }, "2026-01-02"), true);
  eq("isDue 未来", window.RecallCore.isDue({ due: "2026-01-03", suspended: false }, "2026-01-02"), false);
  eq("isDue 暂停", window.RecallCore.isDue({ due: "2026-01-01", suspended: true }, "2026-01-02"), false);

  // 5 × 2.5 = 12.5，约定四舍五入 → 13（Python 端同样实现）
  var half = window.RecallCore.sm2({ ef: 2.5, reps: 3, interval: 5, lapses: 0, due: "", suspended: false }, 3, "2026-01-01");
  eq("间隔四舍五入", half.interval, 13);

  var leech = window.RecallCore.sm2({ ef: 2.5, reps: 0, interval: 1, lapses: 7, due: "2026-01-01", suspended: false }, 1, "2026-01-02");
  eq("leech 累计", leech.lapses, 8);
  eq("leech 暂停", leech.suspended, true);

  var r = window.RecallCore.retention({ ef: 2.5, reps: 1, interval: 6, due: "2026-01-07", suspended: false }, "2026-01-01");
  check("retention 在 (0,1]", r > 0 && r <= 1, String(r));

  var summary = document.getElementById("summary");
  var result = fail === 0 ? "PASS" : "FAIL";
  document.body.setAttribute("data-result", result);
  summary.textContent = (fail === 0 ? "通过 " : "失败 ") + pass + " / " + (pass + fail) + " 项断言";
  if (fail > 0) { summary.className = "bad"; }
  document.getElementById("out").textContent = lines.join("\n");
})();
