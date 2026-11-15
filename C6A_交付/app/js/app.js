/* C6A · 交卷雷达
 * 纯前端：数据在 js/data.js（由 data/build_dataset.py 生成），这里只做筛选、聚合、画图。
 * 三条自我约束：
 *   1) 不引第三方库 —— 图表是手写 SVG，离线双击就能跑。
 *   2) 不在前端「编」数字 —— 所有洞察文案与数值都来自 metrics.json，页面只负责筛选与呈现。
 *   3) 每个比率都带分母 —— 悬停/副标题能看到分子分母。 */
(function () {
  "use strict";

  const D = window.C6A_DATA;
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const fmt1 = (v) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(1));
  const pct1 = (v) => (v == null ? "—" : Number(v).toFixed(1) + "%");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  /* ---------------------------------------------------------------- 数据整形 */
  const roster = D.students.filter((s) => s.status === "在读");
  const submittedRows = D.rows.slice();
  const has = new Set(submittedRows.map((r) => r.student_id + "|" + r.challenge_id));
  const missingRows = [];
  for (const s of roster) {
    for (const c of D.challenges) {
      if (has.has(s.id + "|" + c.id)) continue;
      missingRows.push({
        submission_id: null,
        student_id: s.id,
        student_name: s.name,
        class: s.class,
        challenge_id: c.id,
        challenge_name: c.name,
        deadline: c.deadline,
        submitted_at: null,
        early_hours: null,
        is_late: false,
        late_hours: 0,
        attempts: 0,
        status: "missing",
        channel: null,
        files: 0,
        flags: [],
        flag_count: 0,
        ai_turns: 0,
        reviewer: null,
        reviewed: false,
        scores: null,
        total: null,
      });
    }
  }
  const allRows = submittedRows.concat(missingRows);
  const byStudent = new Map();
  for (const r of allRows) {
    if (!byStudent.has(r.student_id)) byStudent.set(r.student_id, []);
    byStudent.get(r.student_id).push(r);
  }
  for (const arr of byStudent.values()) arr.sort((a, b) => a.challenge_id.localeCompare(b.challenge_id));

  const TODAY = (D.meta.generated_at || "2026-11-15").slice(0, 10);
  const CH = D.challenges;
  const chIndex = new Map(CH.map((c, i) => [c.id, i]));

  /* ---------------------------------------------------------------- 状态 */
  const state = {
    challenge: "all",
    cls: "all",
    status: "all",
    flag: "all",
    q: "",
    tab: "overview",
    sort: { key: "total", dir: 1 },
    page: 1,
    size: 25,
  };

  const STATUS_LABEL = {
    all: "全部",
    ok: "按时",
    late: "迟交",
    missing: "未交",
    pending: "待评审",
    flag: "有红旗",
    returned: "被退回",
  };

  function inScope(r) {
    if (state.challenge !== "all" && r.challenge_id !== state.challenge) return false;
    if (state.cls !== "all" && r.class !== state.cls) return false;
    if (state.q) {
      const q = state.q.toLowerCase();
      if (!(r.student_name.toLowerCase().includes(q) || r.student_id.includes(q))) return false;
    }
    const isMissing = r.status === "missing";
    switch (state.status) {
      case "ok": return !isMissing && !r.is_late;
      case "late": return !isMissing && r.is_late;
      case "missing": return isMissing;
      case "pending": return !isMissing && !r.reviewed;
      case "flag": return !isMissing && (state.flag === "all" ? r.flag_count > 0 : r.flags.includes(state.flag));
      case "returned": return r.status === "returned";
      default: return true;
    }
  }

  function scopedRows() { return allRows.filter(inScope); }

  function expectedCount() {
    const nStu = state.cls === "all" ? roster.length : roster.filter((s) => s.class === state.cls).length;
    const nCh = state.challenge === "all" ? CH.length : 1;
    return nStu * nCh;
  }

  function aggregate(rows) {
    const live = rows.filter((r) => r.status !== "missing");
    const scored = live.filter((r) => r.total != null);
    const late = live.filter((r) => r.is_late);
    const onTime = live.filter((r) => !r.is_late);
    const pending = live.filter((r) => !r.reviewed);
    const flagged = live.filter((r) => r.flag_count > 0);
    const nums = scored.map((r) => r.total).sort((a, b) => a - b);
    const median = nums.length ? (nums.length % 2 ? nums[(nums.length - 1) / 2] : (nums[nums.length / 2 - 1] + nums[nums.length / 2]) / 2) : null;
    const avg = nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
    return {
      expected: expectedCount(),
      live: live.length,
      missing: rows.filter((r) => r.status === "missing").length,
      onTime: onTime.length,
      late: late.length,
      pending: pending.length,
      flagged: flagged.length,
      scored,
      median,
      avg,
      rate: expectedCount() ? (live.length / expectedCount()) * 100 : 0,
      onTimeRate: expectedCount() ? (onTime.length / expectedCount()) * 100 : 0,
    };
  }

  /* ---------------------------------------------------------------- 小工具 */
  function el(tag, cls, html) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function svgNode(w, h) {
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", `0 0 ${w} ${h}`);
    s.setAttribute("width", w);
    s.setAttribute("height", h);
    s.setAttribute("role", "img");
    return s;
  }
  function node(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function scale(domain, range) {
    const [d0, d1] = domain, [r0, r1] = range;
    const k = (r1 - r0) / (d1 - d0 || 1);
    const f = (v) => r0 + (v - d0) * k;
    f.invert = (p) => d0 + (p - r0) / k;
    return f;
  }
  function niceTicks(max, count = 4) {
    if (!max) return [0];
    const raw = max / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
    const out = [];
    for (let v = 0; v <= max + step * 0.001; v += step) out.push(Math.round(v * 100) / 100);
    return out;
  }
  const tooltip = $("#tooltip");
  function bindTip(root) {
    $$("[data-tip]", root).forEach((n) => {
      n.addEventListener("mouseenter", (e) => {
        tooltip.innerHTML = n.getAttribute("data-tip");
        tooltip.classList.add("on");
        moveTip(e);
      });
      n.addEventListener("mousemove", moveTip);
      n.addEventListener("mouseleave", () => tooltip.classList.remove("on"));
    });
  }
  function moveTip(e) {
    const r = tooltip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > window.innerWidth - 10) x = e.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 10) y = e.clientY - r.height - 14;
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
  }

  /* ---------------------------------------------------------------- 图表 */
  function chartBox(host, h) {
    host.innerHTML = "";
    const w = Math.max(300, host.clientWidth || 600);
    const s = svgNode(w, h || host.clientHeight || 200);
    host.appendChild(s);
    return { svg: s, w, h: h || host.clientHeight || 200 };
  }

  /* 时间线：堆叠柱 + 截止日虚线 */
  function drawTimeline(rows) {
    const host = $("#chartTimeline");
    const { svg, w, h } = chartBox(host);
    const M = { t: 14, r: 8, b: 24, l: 34 };
    const iw = w - M.l - M.r, ih = h - M.t - M.b;

    const days = [];
    const start = new Date(D.timeline[0].date + "T00:00:00");
    const end = new Date(TODAY + "T00:00:00");
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) days.push(d.toISOString().slice(0, 10));
    const idx = new Map(days.map((d, i) => [d, i]));

    const bucket = days.map(() => ({ ok: 0, late: 0 }));
    rows.forEach((r) => {
      if (r.status === "missing" || !r.submitted_at) return;
      const d = r.submitted_at.slice(0, 10);
      if (!idx.has(d)) return;
      bucket[idx.get(d)][r.is_late ? "late" : "ok"]++;
    });
    const max = Math.max(4, ...bucket.map((b) => b.ok + b.late));
    const y = scale([0, max], [M.t + ih, M.t]);
    const bw = Math.max(2, iw / days.length - 1);

    niceTicks(max, 4).forEach((t) => {
      node("line", { x1: M.l, x2: M.l + iw, y1: y(t), y2: y(t), class: "ax-line" }, svg);
      node("text", { x: M.l - 6, y: y(t) + 3, "text-anchor": "end", class: "ax-text" }, svg).textContent = t;
    });

    days.forEach((d, i) => {
      const b = bucket[i];
      if (!b.ok && !b.late) return;
      const x = M.l + (i * iw) / days.length + 0.5;
      const tip = `<b>${d}</b><br>按时 ${b.ok} · 迟交 ${b.late}`;
      let yTop = y(0);
      if (b.ok) {
        const hh = y(0) - y(b.ok);
        node("rect", { x, y: y(b.ok), width: bw, height: Math.max(1, hh), rx: 1.5, class: "bar bar-ontime", "data-tip": tip }, svg);
        yTop = y(b.ok);
      }
      if (b.late) {
        const hh = y(b.ok) - y(b.ok + b.late);
        const rect = node("rect", { x, y: yTop - hh, width: bw, height: Math.max(1, hh), rx: 1.5, class: "bar bar-late", "data-tip": tip }, svg);
        rect.style.cursor = "pointer";
      }
    });

    CH.forEach((c) => {
      const d = c.deadline.slice(0, 10);
      if (!idx.has(d)) return;
      const x = M.l + (idx.get(d) * iw) / days.length + bw / 2;
      node("line", { x1: x, x2: x, y1: M.t, y2: M.t + ih, class: "deadline" }, svg);
      node("text", { x: x + 3, y: M.t + 9, class: "deadline-label" }, svg).textContent = c.id;
    });

    const tick = Math.max(1, Math.floor(days.length / 7));
    days.forEach((d, i) => {
      if (i % tick) return;
      node("text", { x: M.l + (i * iw) / days.length, y: h - 7, class: "ax-text" }, svg).textContent = d.slice(5).replace("-", "/");
    });

    const agg = aggregate(rows);
    $("#noteTimeline").innerHTML = `当前视图 <b>${agg.live}</b> 份提交，其中 <b>${agg.late}</b> 份迟交；红线是 6 个挑战的截止日，C6 还在进行中。`;
    bindTip(host);
  }

  /* 挑战完成度：横向条 */
  function drawChallenges(rows) {
    const host = $("#chartChallenges");
    const { svg, w, h } = chartBox(host);
    const M = { t: 8, r: 76, b: 6, l: 40 };
    const iw = w - M.l - M.r;
    const rowH = (h - M.t - M.b) / CH.length;
    const x = scale([0, 100], [M.l, M.l + iw]);
    const live = rows.filter((r) => r.status !== "missing");
    const nStu = state.cls === "all" ? roster.length : roster.filter((s) => s.class === state.cls).length;

    CH.forEach((c, i) => {
      const rs = live.filter((r) => r.challenge_id === c.id);
      const exp = nStu;
      const rate = exp ? (rs.length / exp) * 100 : 0;
      const scored = rs.filter((r) => r.total != null);
      const med = scored.length ? scored.map((r) => r.total).sort((a, b) => a - b)[Math.floor(scored.length / 2)] : null;
      const yy = M.t + i * rowH + rowH * 0.18;
      const bh = Math.max(10, rowH * 0.42);
      node("text", { x: M.l - 8, y: yy + bh / 2 + 4, "text-anchor": "end", class: "ax-text-l" }, svg).textContent = c.id;
      node("rect", { x: M.l, y: yy, width: iw, height: bh, rx: 4, class: "bar-track" }, svg);
      const bar = node("rect", {
        x: M.l, y: yy, width: Math.max(2, x(rate) - M.l), height: bh, rx: 4, class: "bar bar-ontime",
        "data-tip": `<b>${c.id} ${c.name}</b><br>提交 ${rs.length}/${exp} = ${pct1(rate)}<br>中位 ${med == null ? "—" : fmt1(med)} · 迟交 ${rs.filter((r) => r.is_late).length}`,
      }, svg);
      bar.addEventListener("click", () => { state.challenge = state.challenge === c.id ? "all" : c.id; state.page = 1; syncControls(); render(); });
      node("text", { x: M.l + iw + 7, y: yy + bh / 2, class: "ax-text", style: "font-size:11px;fill:var(--text)" }, svg).textContent = pct1(rate);
      node("text", { x: M.l + iw + 7, y: yy + bh / 2 + 11, class: "ax-text", style: "font-size:9.5px" }, svg).textContent = rs.length + "/" + exp;
    });
    bindTip(host);
  }

  /* 总分分布 */
  function drawHist(rows) {
    const host = $("#chartHist");
    const { svg, w, h } = chartBox(host);
    const M = { t: 16, r: 6, b: 22, l: 28 };
    const iw = w - M.l - M.r, ih = h - M.t - M.b;
    const bins = [];
    for (let b = 40; b < 100; b += 10) bins.push({ label: `${b}-${b + 9}`, n: 0 });
    rows.forEach((r) => {
      if (r.total == null) return;
      const b = clamp(Math.floor(r.total / 10) * 10, 40, 90);
      const bin = bins.find((x) => x.label.startsWith(String(b)));
      if (bin) bin.n++;
    });
    const max = Math.max(1, ...bins.map((b) => b.n));
    const y = scale([0, max], [M.t + ih, M.t]);
    niceTicks(max, 3).forEach((t) => {
      node("line", { x1: M.l, x2: M.l + iw, y1: y(t), y2: y(t), class: "ax-line" }, svg);
      node("text", { x: M.l - 5, y: y(t) + 3, "text-anchor": "end", class: "ax-text" }, svg).textContent = t;
    });
    const bw = iw / bins.length;
    bins.forEach((b, i) => {
      const x = M.l + i * bw + bw * 0.18;
      const bh = M.t + ih - y(b.n);
      node("rect", { x, y: y(b.n), width: bw * 0.64, height: Math.max(0, bh), rx: 3, class: "bar bar-dim", "data-tip": `<b>${b.label} 分</b><br>${b.n} 份` }, svg);
      node("text", { x: M.l + i * bw + bw / 2, y: h - 7, "text-anchor": "middle", class: "ax-text" }, svg).textContent = b.label.split("-")[0];
      if (b.n) node("text", { x: M.l + i * bw + bw / 2, y: y(b.n) - 4, "text-anchor": "middle", class: "grid-text" }, svg).textContent = b.n;
    });
    const agg = aggregate(rows);
    $("#noteHist").innerHTML = `已评审 <b>${agg.scored.length}</b> 份，中位 <b>${fmt1(agg.median)}</b>、均分 <b>${fmt1(agg.avg)}</b>；${agg.pending} 份待评审未计入。`;
    bindTip(host);
  }

  /* 五维度：中位 + IQR */
  function drawDims(rows) {
    const host = $("#chartDims");
    const { svg, w, h } = chartBox(host);
    const M = { t: 10, r: 34, b: 18, l: 68 };
    const iw = w - M.l - M.r;
    const rowH = (h - M.t - M.b) / 5;
    const x = scale([40, 100], [M.l, M.l + iw]);
    const scored = rows.filter((r) => r.total != null && r.scores);

    D.dims.forEach((d, i) => {
      const vals = scored.map((r) => r.scores[d.key]).filter((v) => v != null).sort((a, b) => a - b);
      const yy = M.t + i * rowH + rowH / 2;
      const q = (p) => (vals.length ? vals[clamp(Math.round((vals.length - 1) * p), 0, vals.length - 1)] : null);
      const med = q(0.5), p25 = q(0.25), p75 = q(0.75);
      node("text", { x: M.l - 8, y: yy + 4, "text-anchor": "end", class: "ax-text-l" }, svg).textContent = d.label;
      node("line", { x1: M.l, x2: M.l + iw, y1: yy, y2: yy, class: "ax-line" }, svg);
      if (med != null) {
        node("line", { x1: x(p25), x2: x(p75), y1: yy, y2: yy, class: "iqr" }, svg);
        node("line", { x1: x(p25), x2: x(p25), y1: yy - 5, y2: yy + 5, class: "iqr" }, svg);
        node("line", { x1: x(p75), x2: x(p75), y1: yy - 5, y2: yy + 5, class: "iqr" }, svg);
        node("circle", { cx: x(med), cy: yy, r: 4, class: "marker" }, svg);
        node("text", { x: M.l + iw + 6, y: yy + 4, class: "ax-text" }, svg).textContent = fmt1(med);
        node("rect", { x: x(p25), y: yy - 9, width: Math.max(1, x(p75) - x(p25)), height: 18, fill: "transparent",
          "data-tip": `<b>${d.label}</b>（权重 ${d.weight}%）<br>中位 ${fmt1(med)} · p25 ${fmt1(p25)} · p75 ${fmt1(p75)}<br>低于 60 分：${pct1((vals.filter((v) => v < 60).length / vals.length) * 100)}` }, svg);
      }
      node("text", { x: M.l - 8, y: yy + 15, "text-anchor": "end", class: "ax-text", style: "font-size:9px" }, svg).textContent = d.weight + "%";
    });
    niceTicks(100, 4).forEach((t) => {
      if (t < 40) return;
      node("text", { x: x(t), y: h - 5, "text-anchor": "middle", class: "ax-text" }, svg).textContent = t;
    });
    bindTip(host);
  }

  /* 交付物缺口 */
  function drawFlags(rows) {
    const host = $("#chartFlags");
    const { svg, w, h } = chartBox(host);
    const live = rows.filter((r) => r.status !== "missing");
    const items = [
      { key: "缺 demo", label: "缺 demo", color: "var(--amber)" },
      { key: "缺 AI 日志", label: "缺 AI 日志", color: "var(--violet)" },
      { key: "缺数据", label: "缺数据", color: "var(--accent)" },
      { key: "缺 README", label: "缺 README", color: "var(--muted)" },
    ].map((it) => ({ ...it, n: live.filter((r) => r.flags.includes(it.key)).length }));
    const M = { t: 8, r: 44, b: 6, l: 82 };
    const iw = w - M.l - M.r;
    const rowH = (h - M.t - M.b) / items.length;
    const x = scale([0, 100], [M.l, M.l + iw]);
    items.forEach((it, i) => {
      const rate = live.length ? (it.n / live.length) * 100 : 0;
      const yy = M.t + i * rowH + rowH * 0.22;
      const bh = Math.max(9, rowH * 0.4);
      node("text", { x: M.l - 8, y: yy + bh / 2 + 4, "text-anchor": "end", class: "ax-text-l" }, svg).textContent = it.label;
      node("rect", { x: M.l, y: yy, width: iw, height: bh, rx: 4, class: "bar-track" }, svg);
      node("rect", { x: M.l, y: yy, width: Math.max(1, x(rate) - M.l), height: bh, rx: 4, fill: it.color, opacity: .82,
        "data-tip": `<b>${it.label}</b><br>${it.n} 份 / ${live.length} 份 = ${pct1(rate)}` }, svg);
      node("text", { x: M.l + iw + 6, y: yy + bh / 2 + 4, class: "ax-text" }, svg).textContent = pct1(rate);
    });
    const agg = aggregate(rows);
    $("#noteFlags").innerHTML = `当前视图 <b>${agg.flagged}</b> 份命中至少一项红旗，占已交 <b>${pct1(agg.live ? (agg.flagged / agg.live) * 100 : 0)}</b>。`;
    bindTip(host);
  }

  /* 班级 × 评审人 */
  function drawClass(rows) {
    const host = $("#chartClass");
    const { svg, w, h } = chartBox(host);
    const M = { t: 16, r: 10, b: 26, l: 36 };
    const iw = w - M.l - M.r, ih = h - M.t - M.b;
    const y = scale([50, 90], [M.t + ih, M.t]);
    [50, 60, 70, 80, 90].forEach((t) => {
      node("line", { x1: M.l, x2: M.l + iw, y1: y(t), y2: y(t), class: "ax-line" }, svg);
      node("text", { x: M.l - 6, y: y(t) + 3, "text-anchor": "end", class: "ax-text" }, svg).textContent = t;
    });
    const scored = rows.filter((r) => r.total != null);
    const groups = ["A", "B", "C"];
    const bw = iw / groups.length;
    groups.forEach((c, i) => {
      const rs = scored.filter((r) => r.class === c);
      const avg = rs.length ? rs.reduce((a, b) => a + b.total, 0) / rs.length : null;
      const cx = M.l + i * bw + bw / 2;
      const bwid = Math.min(64, bw * 0.44);
      if (avg != null) {
        node("rect", { x: cx - bwid / 2, y: y(avg), width: bwid, height: M.t + ih - y(avg), rx: 4, class: "bar bar-dim",
          "data-tip": `<b>${c} 班</b><br>均分 ${fmt1(avg)}（n=${rs.length}）` }, svg);
        node("text", { x: cx, y: y(avg) - 6, "text-anchor": "middle", class: "grid-text" }, svg).textContent = fmt1(avg);
      }
      const rv = D.reviewers.find((r) => r.id === (D.byClass.find((b) => b.class === c) || {}).reviewer);
      if (rv && rv.avg != null) {
        const yy = y(rv.avg);
        node("path", { d: `M${cx} ${yy - 6} L${cx + 6} ${yy} L${cx} ${yy + 6} L${cx - 6} ${yy} Z`, fill: "var(--text)", opacity: .85,
          "data-tip": `<b>${rv.name}（${rv.id}）</b><br>均分 ${fmt1(rv.avg)} · n=${rv.n}` }, svg);
      }
      node("text", { x: cx, y: h - 8, "text-anchor": "middle", class: "ax-text-l" }, svg).textContent = c + " 班";
    });
    const cvr = D.classVsReviewer;
    $("#noteClass").innerHTML = `班级均分极差 <b>${fmt1(cvr.classSpread)}</b> 分，评审人均分极差 <b>${fmt1(cvr.reviewerSpread)}</b> 分；同一评审人跨班只差 <b>${fmt1(cvr.withinReviewerSpread)}</b> 分。`;
    bindTip(host);
  }

  /* 迟交 vs 按时：五维度中位对比 */
  function drawLate(rows) {
    const host = $("#chartLate");
    const { svg, w, h } = chartBox(host);
    const M = { t: 14, r: 8, b: 34, l: 34 };
    const iw = w - M.l - M.r, ih = h - M.t - M.b;
    const y = scale([50, 95], [M.t + ih, M.t]);
    [50, 60, 70, 80, 90].forEach((t) => {
      node("line", { x1: M.l, x2: M.l + iw, y1: y(t), y2: y(t), class: "ax-line" }, svg);
      node("text", { x: M.l - 6, y: y(t) + 3, "text-anchor": "end", class: "ax-text" }, svg).textContent = t;
    });
    const scored = rows.filter((r) => r.total != null && r.scores);
    const groupW = iw / 5;
    D.dims.forEach((d, i) => {
      const cx = M.l + i * groupW + groupW / 2;
      const series = [
        { key: "ok", label: "按时", cls: "bar-ontime", rs: scored.filter((r) => !r.is_late) },
        { key: "late", label: "迟交", cls: "bar-late", rs: scored.filter((r) => r.is_late) },
      ];
      const bwid = Math.min(16, groupW * 0.26);
      series.forEach((s, k) => {
        const vals = s.rs.map((r) => r.scores[d.key]).filter((v) => v != null).sort((a, b) => a - b);
        const med = vals.length ? vals[Math.floor((vals.length - 1) / 2)] : null;
        const x0 = cx - bwid - 2 + k * (bwid + 4);
        if (med != null) {
          node("rect", { x: x0, y: y(med), width: bwid, height: M.t + ih - y(med), rx: 3, class: "bar " + s.cls,
            "data-tip": `<b>${d.label} · ${s.label}</b><br>中位 ${fmt1(med)}（n=${vals.length}）` }, svg);
        }
      });
      node("text", { x: cx, y: h - 18, "text-anchor": "middle", class: "ax-text", style: "font-size:9.5px" }, svg).textContent = d.label;
    });
    const late = D.late;
    $("#noteLate").innerHTML = `按时组中位 <b>${fmt1(late.onTime.median)}</b>，迟交组 <b>${fmt1(late.late.median)}</b>；相关系数只有 <b>${late.corr}</b>——迟交不是质量信号。`;
    bindTip(host);
  }

  /* 口径页：三种分母 */
  function drawDenominator() {
    const host = $("#chartDenominator");
    if (!host) return;
    const { svg, w, h } = chartBox(host);
    const M = { t: 8, r: 46, b: 6, l: 150 };
    const iw = w - M.l - M.r;
    const a = D.alt;
    const items = [
      { label: "仅已截止 C1–C5", v: a.rateExcludeInProgress, color: "var(--accent)" },
      { label: "含进行中 C6", v: a.rateRoster, color: "var(--violet)" },
      { label: "全员（含退课）", v: a.rateAllStudents, color: "var(--amber)" },
    ];
    const rowH = (h - M.t - M.b) / items.length;
    const x = scale([60, 100], [M.l, M.l + iw]);
    items.forEach((it, i) => {
      const yy = M.t + i * rowH + rowH * 0.22;
      const bh = Math.max(10, rowH * 0.42);
      node("text", { x: M.l - 10, y: yy + bh / 2 + 4, "text-anchor": "end", class: "ax-text-l" }, svg).textContent = it.label;
      node("rect", { x: M.l, y: yy, width: iw, height: bh, rx: 4, class: "bar-track" }, svg);
      node("rect", { x: M.l, y: yy, width: Math.max(1, x(it.v) - M.l), height: bh, rx: 4, fill: it.color, opacity: .82,
        "data-tip": `<b>${it.label}</b><br>提交率 ${pct1(it.v)}` }, svg);
      node("text", { x: M.l + iw + 6, y: yy + bh / 2 + 4, class: "ax-text" }, svg).textContent = pct1(it.v);
    });
    bindTip(host);
  }

  /* 真实数据：每目录 commit 数 */
  function drawCommits() {
    const host = $("#chartCommits");
    if (!host || !D.real) return;
    const { svg, w, h } = chartBox(host);
    const items = D.real.items.filter((i) => i.kind === "delivery").sort((a, b) => b.commits - a.commits);
    const M = { t: 6, r: 40, b: 6, l: 116 };
    const iw = w - M.l - M.r;
    const rowH = (h - M.t - M.b) / items.length;
    const max = Math.max(...items.map((i) => i.commits));
    const x = scale([0, max], [M.l, M.l + iw]);
    items.forEach((it, i) => {
      const yy = M.t + i * rowH + rowH * 0.2;
      const bh = Math.max(8, rowH * 0.5);
      const opacity = it.squashed ? 0.92 : 0.5;
      node("text", { x: M.l - 8, y: yy + bh / 2 + 4, "text-anchor": "end", class: "ax-text", style: "font-size:9.5px" }, svg)
        .textContent = it.folder.length > 14 ? it.folder.slice(0, 13) + "…" : it.folder;
      node("rect", { x: M.l, y: yy, width: Math.max(2, x(it.commits) - M.l), height: bh, rx: 3,
        fill: it.squashed ? "var(--accent)" : "var(--violet)", opacity,
        "data-tip": `<b>${it.folder}</b><br>${it.commits} commits · ${it.files} 文件 · ${it.kb} KB<br>跨度 ${it.span_hours} h${it.squashed ? "<br>⚠ 疑似一次性推送" : ""}` }, svg);
      node("text", { x: M.l + iw + 6, y: yy + bh / 2 + 4, class: "ax-text" }, svg).textContent = it.commits;
    });
    bindTip(host);
  }

  /* ---------------------------------------------------------------- 渲染：KPI */
  function renderKpis() {
    const agg = aggregate(scopedRows());
    const host = $("#kpis");
    host.innerHTML = "";
    const cards = [
      {
        label: "提交率", value: pct1(agg.rate), sub: `${agg.live} / ${agg.expected} 份`, cls: agg.rate >= 85 ? "" : "warn",
        tip: `分子：有效提交 ${agg.live}（同生同挑战只算最后一条）<br>分母：${state.cls === "all" ? roster.length : roster.filter((s) => s.class === state.cls).length} 位在读 × ${state.challenge === "all" ? CH.length : 1} 个挑战 = ${agg.expected}`,
      },
      {
        label: "按时率", value: pct1(agg.onTimeRate), sub: `${agg.onTime} 份 ≤ 截止时间`, cls: "",
        tip: `分子：按时提交 ${agg.onTime}<br>分母：应交 ${agg.expected}（与提交率同分母，便于比较）`,
      },
      {
        label: "迟交", value: agg.late, sub: `占已交 ${pct1(agg.live ? (agg.late / agg.live) * 100 : 0)}`, cls: "warn",
        tip: `迟交 = submitted_at 晚于截止时间；迟交仍算已交，不并入未交。`,
      },
      {
        label: "待评审", value: agg.pending, sub: `已评审 ${agg.scored.length} 份`, cls: "",
        tip: `待评审不进均分分母：缺失不等于 0 分。`,
      },
      {
        label: "中位分", value: fmt1(agg.median), sub: `均分 ${fmt1(agg.avg)}`, cls: "",
        tip: `仅统计已评审且已给分的记录；中位数比均值更抗长尾。`,
      },
      {
        label: "红旗率", value: pct1(agg.live ? (agg.flagged / agg.live) * 100 : 0), sub: `${agg.flagged} 份命中`, cls: agg.live && agg.flagged / agg.live > 0.45 ? "bad" : "",
        tip: `红旗 = 缺 README / demo / 数据 / AI 日志任一；一份可命中多条，按份计。`,
      },
    ];
    cards.forEach((c) => {
      const n = el("article", "kpi " + (c.cls || ""));
      n.innerHTML = `<div class="k-label">${c.label}<span class="hint" data-tip="${c.tip}">?</span></div>
        <div class="k-value">${c.value}</div>
        <div class="k-sub">${c.sub}</div>`;
      host.appendChild(n);
    });
    bindTip(host);
  }

  /* ---------------------------------------------------------------- 渲染：筛选器 */
  function chip(label, active, count, onClick, title) {
    const b = el("button", "chip", label + (count == null ? "" : ` <b>${count}</b>`));
    b.setAttribute("aria-pressed", String(active));
    if (title) b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }

  function renderFilters() {
    const chHost = $("#fChallenge");
    chHost.innerHTML = "";
    chHost.appendChild(chip("全部", state.challenge === "all", null, () => { state.challenge = "all"; state.page = 1; render(); }));
    CH.forEach((c) => {
      const rate = D.byChallenge.find((x) => x.id === c.id).rate;
      chHost.appendChild(chip(`${c.id}`, state.challenge === c.id, rate + "%", () => {
        state.challenge = state.challenge === c.id ? "all" : c.id; state.page = 1; render();
      }, c.name));
    });

    const clsHost = $("#fClass");
    clsHost.innerHTML = "";
    clsHost.appendChild(chip("全部", state.cls === "all", null, () => { state.cls = "all"; state.page = 1; render(); }));
    ["A", "B", "C"].forEach((c) => {
      const n = roster.filter((s) => s.class === c).length;
      clsHost.appendChild(chip(`${c} 班`, state.cls === c, n, () => {
        state.cls = state.cls === c ? "all" : c; state.page = 1; render();
      }));
    });

    const stHost = $("#fStatus");
    stHost.innerHTML = "";
    ["all", "ok", "late", "missing", "pending", "flag", "returned"].forEach((k) => {
      stHost.appendChild(chip(STATUS_LABEL[k], state.status === k, null, () => {
        state.status = k; state.flag = "all"; state.page = 1; render();
      }));
    });
  }

  function renderScope() {
    const rows = scopedRows();
    const agg = aggregate(rows);
    const flags = [];
    if (state.challenge !== "all") flags.push("挑战 " + state.challenge);
    if (state.cls !== "all") flags.push(state.cls + " 班");
    if (state.status !== "all") flags.push(STATUS_LABEL[state.status] + (state.flag !== "all" ? "（" + state.flag + "）" : ""));
    if (state.q) flags.push("搜索「" + state.q + "」");
    const label = flags.length ? flags.join(" · ") : "全部数据";
    $("#scope").innerHTML = `当前视图：<b>${label}</b><span class="sep">|</span>已交 <b>${agg.live}</b> · 未交 <b>${agg.missing}</b><span class="sep">|</span>分母 <b>${agg.expected}</b>（${state.cls === "all" ? roster.length : roster.filter((s) => s.class === state.cls).length} 人 × ${state.challenge === "all" ? CH.length : 1} 挑战）`;

  }

  /* ---------------------------------------------------------------- 渲染：洞察 */
  function renderInsights() {
    const host = $("#insightList");
    host.innerHTML = "";
    D.insights.forEach((it) => {
      const card = el("article", "insight");
      card.dataset.level = it.level;
      card.innerHTML = `
        <div class="i-top">
          <span class="tag">${it.tag}</span>
          <span class="level level-${it.level}">${it.level}置信</span>
          <span class="i-id">${it.id}</span>
        </div>
        <h3>${it.title}</h3>
        <p class="claim">${it.claim}</p>
        <div class="evidence">
          ${it.evidence.map((e) => `<div><div class="ev-l">${e.label}</div><div class="ev-v">${e.value}</div></div>`).join("")}
        </div>
        <div class="caveat"><b>注意</b> · ${it.caveat}</div>
        <div class="action"><b>该做什么</b> · ${it.action}</div>
        <div class="i-foot"><button class="btn small" data-apply>应用到看板 →</button></div>`;
      card.querySelector("[data-apply]").addEventListener("click", () => applyFilter(it.filter));
      host.appendChild(card);
    });
    $("#insightCount").textContent = D.insights.length;
  }

  function applyFilter(f) {
    if (!f) return;
    if (f.challenge) state.challenge = f.challenge;
    if (f.flag) { state.status = "flag"; state.flag = f.flag; }
    if (f.late) state.status = "late";
    if (f.cls) state.cls = f.cls;
    state.page = 1;
    setTab("overview");
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ---------------------------------------------------------------- 渲染：学生表 */
  function sortedRows() {
    const rows = scopedRows();
    const { key, dir } = state.sort;
    return rows.slice().sort((a, b) => {
      let av = a[key], bv = b[key];
      if (key === "flag_count") { av = a.flags.length; bv = b.flags.length; }
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv), "zh") * dir;
    });
  }

  function statusBadge(r) {
    if (r.status === "missing") return '<span class="badge badge-miss">未交</span>';
    if (!r.reviewed) return '<span class="badge badge-pend">待评审</span>';
    if (r.is_late) return '<span class="badge badge-late">迟交</span>';
    if (r.status === "returned") return '<span class="badge badge-flag">已退回</span>';
    return '<span class="badge badge-ok">按时</span>';
  }

  function renderTable() {
    const rows = sortedRows();
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / state.size));
    state.page = clamp(state.page, 1, pages);
    const slice = rows.slice((state.page - 1) * state.size, state.page * state.size);
    const body = $("#studentBody");
    body.innerHTML = "";
    if (!slice.length) {
      body.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:36px;color:var(--muted)">当前筛选下没有记录 —— 换个条件试试</td></tr>';
    }
    slice.forEach((r) => {
      const tr = document.createElement("tr");
      const early = r.status === "missing" ? "—" : (r.early_hours >= 0 ? "早 " + fmt1(r.early_hours) + "h" : `<span style="color:var(--amber)">晚 ${fmt1(r.late_hours)}h</span>`);
      tr.innerHTML = `
        <td class="num">${r.student_id}</td>
        <td>${r.student_name}</td>
        <td>${r.class}</td>
        <td class="num">${r.challenge_id}</td>
        <td class="num">${r.submitted_at ? r.submitted_at.slice(5, 16).replace("T", " ") : "—"}</td>
        <td class="num">${early}</td>
        <td class="num">${r.reviewer || "—"}</td>
        <td class="num">${r.total == null ? "—" : fmt1(r.total)}</td>
        <td>${r.flags.length ? `<span class="badge badge-flag">${r.flags.length}</span>` : '<span class="badge badge-plain">0</span>'}</td>
        <td><button class="btn ghost small" data-open>详情</button></td>`;
      tr.querySelector("[data-open]").addEventListener("click", (e) => { e.stopPropagation(); openDrawer(r.student_id); });
      tr.addEventListener("click", () => openDrawer(r.student_id));
      body.appendChild(tr);
    });

    const pager = $("#pager");
    pager.innerHTML = "";
    const prev = el("button", "", "上一页");
    prev.disabled = state.page <= 1;
    prev.addEventListener("click", () => { state.page--; renderTable(); });
    const next = el("button", "", "下一页");
    next.disabled = state.page >= pages;
    next.addEventListener("click", () => { state.page++; renderTable(); });
    pager.appendChild(prev);
    pager.appendChild(el("span", "", `第 ${state.page} / ${pages} 页 · 共 ${total} 条`));
    pager.appendChild(next);
    $("#tableSort").textContent = `按 ${state.sort.key} ${state.sort.dir > 0 ? "升序" : "降序"} · 点击表头切换`;
  }

  /* ---------------------------------------------------------------- 渲染：口径 / 真实数据 */
  function renderDictionary() {
    const body = $("#dictBody");
    body.innerHTML = D.dictionary.map((d) => `<tr>
        <td><b>${d.label}</b><div class="muted" style="font-size:11px">${d.key}</div></td>
        <td>${d.formula}</td><td>${d.denominator}</td><td>${d.edge}</td><td class="muted">${d.why}</td>
      </tr>`).join("");

    const cleanMap = [
      ["撤回的记录（status=withdrawn）", "dropped_withdrawn", "剔除：不算已交，也不算未交"],
      ["重复提交（attempt_no > 1）", "dropped_duplicate_attempt", "按 (学生, 挑战) 保留最后一条"],
      ["时区为 UTC 的时间戳", "tz_normalized", "统一换算到 +08:00 再判迟交"],
      ["总分与分项之和不符", "total_recomputed", "按分项加权重算"],
      ["姓名首尾空白", "trimmed_names", "trim 后与学号对齐"],
    ];
    const log = D.meta.log || {};
    $("#cleanBody").innerHTML = cleanMap.map(([name, key, rule]) => {
      const v = log[key] || 0;
      return `<tr><td>${name}</td><td class="num">${v}</td><td class="muted">${rule}</td></tr>`;
    }).join("");

    const a = D.alt, k = D.kpis, cvr = D.classVsReviewer;
    const realBig = D.real
      ? D.real.items.filter((i) => i.kind === "delivery").slice().sort((x, y) => y.commits - x.commits)[0]
      : null;
    const traps = [
      `<b>分母换一换，数字就「变好」。</b>同一批数据，提交率能报 ${pct1(a.rateExcludeInProgress)}、${pct1(a.rateRoster)}、${pct1(a.rateAllStudents)} 三个值，差别只在分母算到哪一层。看板把分母写进每个 KPI 的悬停提示，就是防止这种自欺。`,
      `<b>迟交不是未交。</b>${pct1(k.lateShare)} 的提交是迟交的；如果把它并进「未交」，完成率会从 ${pct1(k.rate)} 掉到 ${pct1(k.onTimeRate)}，看起来像崩了，其实作业都在。`,
      `<b>git 时间不是提交时间。</b>真实数据页里 ${realBig ? realBig.folder + " 的 " + realBig.commits + " 条 commit 全挤在 " + realBig.span_hours + " 小时内" : "多个目录的 commit 挤在几小时内"}——那是推送，不是迭代。要判迟交只能用平台的提交事件。`,
      `<b>时区能翻转结论。</b>GitHub 返回 UTC，本地截止是 23:59（+08:00）。不换算，晚上 8 点交的作业会被判成「次日凌晨」——数据里 ${(D.meta.log && D.meta.log.tz_normalized) || 2} 条 UTC 记录就是这么翻的。`,
      `<b>缺失值不是 0 分。</b>${a.pendingCount} 份待评审若按 0 分计入，均分从 ${fmt1(a.avgReviewed)} 掉到 ${fmt1(a.avgZeroFilled)}；未交更不是 0，而是没有数据。`,
      `<b>归因要看混淆变量。</b>班级均分差 ${fmt1(cvr.classSpread)} 分，但评审人之间就差 ${fmt1(cvr.reviewerSpread)} 分，且评审人与班级约 88% 绑定——班差暂时不能当学情差。`,
    ];
    $("#traps").innerHTML = traps.map((t) => `<li>${t}</li>`).join("");
  }

  function renderReal() {
    if (!D.real) return;
    const items = D.real.items.filter((i) => i.kind === "delivery");
    const squashed = items.filter((i) => i.squashed).length;
    const totalCommits = items.reduce((a, b) => a + b.commits, 0);
    const host = $("#realKpis");
    host.innerHTML = "";
    [
      { label: "真实交付目录", value: items.length, sub: "每个目录 = 一次挑战交付" },
      { label: "commit 总数", value: totalCommits, sub: `其中 ${squashed} 个目录疑似一次性推送` },
      { label: "总文件数", value: items.reduce((a, b) => a + b.files, 0).toLocaleString("zh-CN"), sub: "来自 git tree，非估算" },
      { label: "抓取时间", value: (D.real.fetched_at || "").slice(0, 10), sub: "GitHub REST API" },
      { label: "数据来源", value: "真实", sub: "可逐条核对，非合成" },
      { label: "时区处理", value: "+08:00", sub: "GitHub 原始为 UTC" },
    ].forEach((c) => {
      const n = el("article", "kpi");
      n.innerHTML = `<div class="k-label">${c.label}</div><div class="k-value">${c.value}</div><div class="k-sub">${c.sub}</div>`;
      host.appendChild(n);
    });

    $("#realBody").innerHTML = items.map((i) => `<tr>
      <td><b>${i.folder}</b></td>
      <td class="num">${i.commits}</td>
      <td class="num">${i.files}</td>
      <td class="num">${i.kb} KB</td>
      <td class="num">${(i.first_commit || "").slice(0, 16).replace("T", " ")} → ${(i.last_commit || "").slice(0, 16).replace("T", " ")}</td>
      <td class="num">${i.span_hours} h</td>
      <td>${i.squashed ? '<span class="badge badge-late">疑似一次性推送</span>' : '<span class="badge badge-ok">有迭代</span>'}</td>
    </tr>`).join("");
  }

  /* ---------------------------------------------------------------- 学生抽屉 */
  function medianOf(arr) {
    if (!arr.length) return null;
    const s = arr.slice().sort((a, b) => a - b);
    return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
  }

  function openDrawer(studentId) {
    const rows = byStudent.get(studentId) || [];
    const stu = D.students.find((s) => s.id === studentId);
    if (!stu) return;
    const live = rows.filter((r) => r.status !== "missing");
    const scored = rows.filter((r) => r.total != null);
    const flags = live.flatMap((r) => r.flags.map((f) => ({ f, ch: r.challenge_id })));
    const late = live.filter((r) => r.is_late);

    $("#drawerName").textContent = stu.name;
    $("#drawerMeta").innerHTML = `${stu.id} · ${stu.class} 班 · ${stu.status} · 评审 ${live[0] ? live[0].reviewer : "—"}`;

    const cohort = submittedRows.filter((r) => r.total != null && r.class === stu.class).map((r) => r.total);
    const cohortMed = medianOf(cohort);
    const mean = scored.length ? scored.reduce((a, b) => a + b.total, 0) / scored.length : null;

    const advice = [];
    const miss = rows.filter((r) => r.status === "missing");
    if (miss.length) advice.push(`还有 ${miss.length} 个挑战未交：${miss.map((m) => m.challenge_id).join("、")}。`);
    if (flags.length) advice.push(`补齐红旗项：${[...new Set(flags.map((x) => x.f))].join("、")}。`);
    if (late.length) advice.push(`迟交 ${late.length} 次，排期是最省力的改进点。`);
    if (mean != null && cohortMed != null && mean < cohortMed - 5) advice.push(`均分低于班级中位 ${fmt1(cohortMed - mean)} 分，优先看最低维度。`);
    if (scored.some((r) => !r.reviewed)) advice.push(`有 ${scored.filter((r) => !r.reviewed).length} 份待评审，分数还会变。`);
    if (!advice.length) advice.push("没有红旗、没有迟交，保持即可。");

    const dimRows = D.dims.map((d) => {
      const vals = scored.map((r) => r.scores && r.scores[d.key]).filter((v) => v != null);
      const v = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      const coh = submittedRows.filter((r) => r.scores && r.class === stu.class).map((r) => r.scores[d.key]);
      const cm = medianOf(coh);
      return `<div class="d-row">
        <span class="name">${d.label}</span>
        <span class="num">${v == null ? "—" : fmt1(v)} <span style="opacity:.5">/ ${fmt1(cm)}</span></span>
      </div>
      <div class="d-bar"><i style="width:${v == null ? 0 : clamp(v, 0, 100)}%"></i></div>`;
    }).join("");

    const chRows = rows.map((r) => `<div class="d-row">
        <span class="badge badge-plain" style="min-width:30px;text-align:center">${r.challenge_id}</span>
        <span class="name">${r.status === "missing" ? "未提交" : r.submitted_at.slice(5, 16).replace("T", " ")} ${r.is_late ? `<span style="color:var(--amber)">迟 ${fmt1(r.late_hours)}h</span>` : ""}</span>
        ${statusBadge(r)}
        <span class="num">${r.total == null ? "—" : fmt1(r.total)}</span>
      </div>`).join("");

    $("#drawerBody").innerHTML = `
      <div class="d-stat">
        <div><div class="l">已交 / 应交</div><div class="v">${live.length} / ${rows.length}</div></div>
        <div><div class="l">迟交</div><div class="v">${late.length}</div></div>
        <div><div class="l">均分</div><div class="v">${fmt1(mean)}</div></div>
        <div><div class="l">红旗</div><div class="v">${flags.length}</div></div>
      </div>
      <div class="d-sec"><h4>六个挑战</h4>${chRows}</div>
      <div class="d-sec"><h4>维度得分（灰字为班级中位）</h4>${dimRows}</div>
      <div class="d-sec"><h4>建议</h4><div class="advice">${advice.map((a) => `<div>${a}</div>`).join("")}</div></div>
    `;
    $("#drawer").classList.add("open");
    $("#drawer").setAttribute("aria-hidden", "false");
    $("#scrim").hidden = false;
  }

  function closeDrawer() {
    $("#drawer").classList.remove("open");
    $("#drawer").setAttribute("aria-hidden", "true");
    $("#scrim").hidden = true;
  }

  /* ---------------------------------------------------------------- 导出 */
  function exportCsv() {
    const rows = sortedRows();
    const cols = ["student_id", "student_name", "class", "challenge_id", "submitted_at", "early_hours", "is_late", "attempts", "status", "reviewer", "reviewed", "total", "flags"];
    const head = cols.join(",");
    const body = rows.map((r) => cols.map((c) => {
      let v = r[c];
      if (Array.isArray(v)) v = v.join("|");
      if (v == null) return "";
      return `"${String(v).replace(/"/g, '""')}"`;
    }).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + head + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `c6a-视图-${state.challenge}-${state.cls}-${state.status}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  /* ---------------------------------------------------------------- 主题 / 选项卡 */
  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    $("#btnTheme").textContent = t === "light" ? "深色" : "浅色";
    try { localStorage.setItem("c6a-theme", t); } catch (e) {}
    requestAnimationFrame(render);
  }
  function initTheme() {
    let t = "dark";
    try { t = localStorage.getItem("c6a-theme") || "dark"; } catch (e) {}
    document.documentElement.dataset.theme = t;
    $("#btnTheme").textContent = t === "light" ? "深色" : "浅色";
  }

  function setTab(tab) {
    state.tab = tab;
    $$("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== tab; });
    const i = location.hash.indexOf("?");
    const qs = i >= 0 ? location.hash.slice(i) : "";
    if (location.hash !== "#" + tab + qs) history.replaceState(null, "", "#" + tab + qs);
  }

  /* 深链：把筛选、主题、抽屉、演示模式全塞进 hash，截图与复现都用同一套参数。
     形如 #students?c=C6&k=A&s=late&open=20251052xxx&theme=light&tour=1 */
  function parseHash() {
    const raw = location.hash.replace(/^#/, "");
    const [tab, qs] = raw.split("?");
    const p = new URLSearchParams(qs || "");
    if (p.get("c")) state.challenge = p.get("c");
    if (p.get("k")) state.cls = p.get("k");
    if (p.get("s")) state.status = p.get("s");
    if (p.get("f")) state.flag = p.get("f");
    if (p.get("q")) state.q = p.get("q");
    if (p.get("theme") === "light" || p.get("theme") === "dark") {
      document.documentElement.dataset.theme = p.get("theme");
      $("#btnTheme").textContent = p.get("theme") === "light" ? "深色" : "浅色";
    }
    return { tab, open: p.get("open"), tour: p.get("tour") };
  }

  /* ---------------------------------------------------------------- 主渲染 */
  function render() {
    const rows = scopedRows();
    renderFilters();
    renderScope();
    renderKpis();
    if (state.tab === "overview") {
      drawTimeline(rows);
      drawChallenges(rows);
      drawHist(rows);
      drawDims(rows);
      drawFlags(rows);
      drawClass(rows);
      drawLate(rows);
    }
    if (state.tab === "students") renderTable();
    if (state.tab === "dictionary") { drawDenominator(); }
    if (state.tab === "real") drawCommits();
    bindTip(document);
  }

  function syncControls() {
    $("#q").value = state.q;
  }

  /* ---------------------------------------------------------------- 演示模式 */
  const TOUR = [
    {
      title: "先看结论：80.3% 的提交率，但只有 64.3% 按时",
      text: "首屏六个数字对应 rubric 关心的六件事。注意「提交率」下面的分母：636 = 106 位在读 × 6 个挑战，右上角问号里写着同样的式子。",
      apply: () => { resetFilters(); setTab("overview"); },
    },
    {
      title: "时间线告诉你峰值在哪一天",
      text: "48.5% 的作业挤在截止前 24 小时，10 月 25 日一天交了 52 份。评审排班如果不跟着这个形状走，最后两天一定爆。",
      apply: () => { resetFilters(); setTab("overview"); },
    },
    {
      title: "点一条洞察，把结论推回看板",
      text: "7 条洞察每一条都有「证据 / 注意 / 该做什么」。点「应用到看板」，筛选条件会被自动带回总览。",
      apply: () => { resetFilters(); setTab("insights"); },
    },
    {
      title: "按挑战下钻：C6 只有 34% 完成",
      text: "因为 C6 还在进行中。分母是否包含进行中的挑战，会让同一个提交率差出 9 个百分点——这就是口径页第 2 个坑。",
      apply: () => { resetFilters(); state.challenge = "C6"; setTab("overview"); },
    },
    {
      title: "最后看口径：每个数字都能被追问",
      text: "10 个指标的公式、分母、边界情况全写在页面上；红色提醒的 6 个坑，是这次做数据时真踩过的。",
      apply: () => { resetFilters(); setTab("dictionary"); },
    },
  ];
  let tourIdx = 0;
  function startTour() {
    tourIdx = 0;
    $("#tour").hidden = false;
    showTour();
  }
  function showTour() {
    const s = TOUR[tourIdx];
    s.apply();
    render();
    $("#tourStep").textContent = `${tourIdx + 1} / ${TOUR.length}`;
    $("#tourTitle").textContent = s.title;
    $("#tourText").textContent = s.text;
    $("#tourPrev").disabled = tourIdx === 0;
    $("#tourNext").textContent = tourIdx === TOUR.length - 1 ? "结束" : "下一步";
  }
  function endTour() { $("#tour").hidden = true; }

  function resetFilters() {
    state.challenge = "all"; state.cls = "all"; state.status = "all"; state.flag = "all"; state.q = ""; state.page = 1;
    syncControls();
  }

  /* ---------------------------------------------------------------- 事件绑定 */
  function bind() {
    $$("#tabs button").forEach((b) => b.addEventListener("click", () => {
      setTab(b.dataset.tab);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));

    $("#q").addEventListener("input", (e) => {
      state.q = e.target.value.trim();
      state.page = 1;
      render();
    });
    $("#btnReset").addEventListener("click", () => { resetFilters(); render(); });
    $("#btnExport").addEventListener("click", exportCsv);
    $("#btnExport2").addEventListener("click", exportCsv);
    $("#btnTheme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));
    $("#btnTour").addEventListener("click", startTour);
    $("#tourExit").addEventListener("click", endTour);
    $("#tourPrev").addEventListener("click", () => { if (tourIdx > 0) { tourIdx--; showTour(); } });
    $("#tourNext").addEventListener("click", () => {
      if (tourIdx === TOUR.length - 1) return endTour();
      tourIdx++; showTour();
    });

    $("#drawerClose").addEventListener("click", closeDrawer);
    $("#scrim").addEventListener("click", closeDrawer);

    $$("#studentTable th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : 1 };
        $$("#studentTable th").forEach((x) => x.classList.remove("sorted"));
        th.classList.add("sorted");
        renderTable();
      });
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeDrawer(); endTour(); }
      if (e.target.matches("input, textarea")) return;
      if (e.key === "/") { e.preventDefault(); $("#q").focus(); }
      if (e.key === "t" || e.key === "T") setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
      const map = { 1: "overview", 2: "insights", 3: "students", 4: "dictionary", 5: "real" };
      if (map[e.key]) { setTab(map[e.key]); render(); }
    });

    let rt;
    window.addEventListener("resize", () => {
      clearTimeout(rt);
      rt = setTimeout(() => { if (state.tab === "overview") render(); }, 160);
    });
  }

  /* ---------------------------------------------------------------- 启动 */
  function init() {
    initTheme();
    $("#genAt").textContent = (D.meta.generated_at || "").slice(0, 10);
    const h = parseHash();
    const valid = ["overview", "insights", "students", "dictionary", "real"];
    setTab(valid.includes(h.tab) ? h.tab : "overview");
    renderInsights();
    renderDictionary();
    renderReal();
    bind();
    syncControls();
    render();
    window.scrollTo(0, 0);
    if (h.open && byStudent.has(h.open)) openDrawer(h.open);
    if (h.tour) startTour();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
