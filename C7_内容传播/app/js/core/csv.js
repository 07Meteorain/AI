// 极简 CSV 解析：够用来读回收的指标表（含引号转义、CRLF、BOM）。
// 不引第三方库的理由见 README「三个刻意的取舍」。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Csv = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function parse(text) {
    if (typeof text !== "string") return [];
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    var rows = [];
    var row = [];
    var field = "";
    var inQuotes = false;

    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (inQuotes) {
        if (ch === '"') {
          if (text[i + 1] === '"') {
            field += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          field += ch;
        }
        continue;
      }
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(field);
        field = "";
      } else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(field);
        field = "";
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else {
        field += ch;
      }
    }
    if (field !== "" || row.length) {
      row.push(field);
      if (row.length > 1 || row[0] !== "") rows.push(row);
    }

    if (!rows.length) return [];
    var header = rows.shift();
    return rows.map(function (cells) {
      var obj = {};
      header.forEach(function (h, idx) {
        obj[h.trim()] = cells[idx] === undefined ? "" : cells[idx].trim();
      });
      return obj;
    });
  }

  function toCsv(rows, columns) {
    if (!rows || !rows.length) return "";
    var cols = columns || Object.keys(rows[0]);
    var esc = function (v) {
      var s = v === null || v === undefined ? "" : String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return [cols.join(",")]
      .concat(
        rows.map(function (r) {
          return cols.map(function (c) {
            return esc(r[c]);
          }).join(",");
        })
      )
      .join("\n");
  }

  return { parse: parse, toCsv: toCsv };
});
