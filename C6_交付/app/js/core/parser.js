/*!
 * PromptGate · core/parser
 * 把一段 prompt 文本解析成结构化模型：行、代码围栏、小节、占位符、其他风格的占位符。
 * 纯函数，无 DOM 依赖 —— 规则引擎与测试都基于它。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.parser = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VAR_RE = /\{\{\s*([^{}\n]{0,60}?)\s*\}\}/g;
  var DOLLAR_RE = /\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}/g;
  var SINGLE_BRACE_RE = /(^|[^${])\{([A-Za-z_][A-Za-z0-9_]{0,30})\}/g;
  var BRACKET_RE = /\[([A-Z][A-Z0-9_]{1,30})\]/g;
  var FENCE_RE = /^\s*(`{3,}|~{3,})\s*([^\s`~]*)\s*$/;

  function normalize(text) {
    return String(text == null ? '' : text).replace(/\r\n?/g, '\n');
  }

  /** 判断行首缩进层级（用于把「输出格式」段落识别为块）。 */
  function indentOf(text) {
    var m = /^(\s*)/.exec(text);
    return m ? m[1].replace(/\t/g, '    ').length : 0;
  }

  /**
   * 解析主入口。
   * @param {string} input
   * @returns {object} model
   */
  function parsePrompt(input) {
    var text = normalize(input);
    var rawLines = text.split('\n');
    var lines = [];
    var fence = null;
    var fenceCount = 0;
    var fenceUnclosed = false;
    var lastFenceLine = 0;

    for (var i = 0; i < rawLines.length; i++) {
      var t = rawLines[i];
      var line = {
        no: i + 1,
        text: t,
        blank: t.trim() === '',
        kind: 'text',
        inFence: false,
        indent: indentOf(t)
      };

      var m = FENCE_RE.exec(t);
      if (m) {
        fenceCount++;
        lastFenceLine = line.no;
        if (!fence) {
          fence = { marker: m[1].charAt(0), size: m[1].length, lang: m[2] || '', start: line.no };
          line.kind = 'fence';
          line.inFence = true;
          line.fence = 'open';
        } else if (m[1].charAt(0) === fence.marker && m[1].length >= fence.size) {
          fence.end = line.no;
          line.kind = 'fence';
          line.inFence = true;
          line.fence = 'close';
          fence = null;
        } else {
          // 围栏内部的 ``` 视为内容
          line.kind = 'code';
          line.inFence = true;
        }
        lines.push(line);
        continue;
      }

      if (fence) {
        line.kind = 'code';
        line.inFence = true;
      } else {
        var h = /^(#{1,6})\s+(\S.*)$/.exec(t);
        if (h) {
          line.kind = 'heading';
          line.level = h[1].length;
          line.title = h[2].trim();
        } else if (/^\s*([-*+]|\d+[.)])\s+/.test(t)) {
          line.kind = 'list';
        } else if (line.blank) {
          line.kind = 'blank';
        }
      }
      lines.push(line);
    }

    if (fence) {
      fenceUnclosed = true;
      fence.unclosed = true;
    }

    // 小节：按 heading 切分（无标题时整篇视为一个隐式小节）
    var sections = [];
    var current = null;
    lines.forEach(function (l) {
      if (l.kind === 'heading') {
        if (current) current.end = l.no - 1;
        current = { title: l.title || '(无标题)', level: l.level, start: l.no, end: l.no };
        sections.push(current);
      } else if (!current) {
        current = { title: '(开头)', level: 0, start: l.no, end: l.no };
        sections.push(current);
      } else {
        current.end = l.no;
      }
    });

    // 双花括号占位符
    var variables = [];
    var byName = Object.create(null);
    lines.forEach(function (l) {
      VAR_RE.lastIndex = 0;
      var mm;
      while ((mm = VAR_RE.exec(l.text)) !== null) {
        var rawName = mm[1];
        var name = String(rawName || '').trim();
        var v = byName[name];
        if (!v) {
          v = {
            name: name,
            raw: mm[0],
            count: 0,
            lines: [],
            columns: [],
            empty: name === '',
            valid: /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)
          };
          byName[name] = v;
          variables.push(v);
        }
        v.count++;
        if (v.lines.indexOf(l.no) === -1) v.lines.push(l.no);
        v.columns.push(mm.index + 1);
      }
    });

    // 其他风格占位符（用于一致性检查）
    var otherStyles = { dollar: collect(DOLLAR_RE), singleBrace: collectSingleBrace(), bracket: collect(BRACKET_RE) };

    function collect(re) {
      var out = [];
      lines.forEach(function (l) {
        re.lastIndex = 0;
        var mm;
        while ((mm = re.exec(l.text)) !== null) {
          out.push({ name: mm[1], line: l.no, raw: mm[0] });
        }
      });
      return out;
    }

    function collectSingleBrace() {
      var out = [];
      lines.forEach(function (l) {
        if (l.inFence) return;
        SINGLE_BRACE_RE.lastIndex = 0;
        var mm;
        while ((mm = SINGLE_BRACE_RE.exec(l.text)) !== null) {
          out.push({ name: mm[2], line: l.no, raw: mm[2] });
          SINGLE_BRACE_RE.lastIndex = mm.index + mm[0].length;
        }
      });
      return out;
    }

    var codeBlocks = [];
    var open = null;
    lines.forEach(function (l) {
      if (l.kind === 'fence' && l.fence === 'open') {
        open = { lang: '', start: l.no, lines: [] };
      } else if (l.kind === 'code' && open) {
        open.lines.push(l.text);
      } else if (l.kind === 'fence' && l.fence === 'close' && open) {
        open.end = l.no;
        open.content = open.lines.join('\n');
        codeBlocks.push(open);
        open = null;
      }
    });
    if (open) {
      // 未闭合的围栏按「一直延续到文末」处理，与 Markdown 渲染器行为一致
      open.end = lines.length;
      open.unclosed = true;
      open.content = open.lines.join('\n');
      codeBlocks.push(open);
    }

    var urls = [];
    var URL_RE = /https?:\/\/[^\s)"'<>]+/g;
    lines.forEach(function (l) {
      URL_RE.lastIndex = 0;
      var mm;
      while ((mm = URL_RE.exec(l.text)) !== null) {
        urls.push({ url: mm[0], line: l.no });
      }
    });

    var totalChars = text.length;
    var nonSpaceChars = text.replace(/\s/g, '').length;
    var cjkChars = (text.match(/[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g) || []).length;
    var latinWords = (text.replace(/[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g, ' ')
      .match(/[A-Za-z0-9_'’-]+/g) || []).length;

    return {
      text: text,
      lines: lines,
      lineCount: lines.length,
      sections: sections,
      variables: variables,
      variableIndex: byName,
      otherStyles: otherStyles,
      placeholderStyles: {
        doubleBrace: variables.length,
        dollar: otherStyles.dollar.length,
        singleBrace: otherStyles.singleBrace.length,
        bracket: otherStyles.bracket.length
      },
      codeBlocks: codeBlocks,
      fenceCount: fenceCount,
      fenceUnclosed: fenceUnclosed,
      lastFenceLine: lastFenceLine,
      urls: urls,
      stats: {
        chars: totalChars,
        charsNoSpace: nonSpaceChars,
        cjkChars: cjkChars,
        latinWords: latinWords,
        lines: lines.length,
        nonBlankLines: lines.filter(function (l) { return !l.blank; }).length,
        maxLineChars: lines.reduce(function (a, l) { return Math.max(a, l.text.length); }, 0),
        headings: sections.filter(function (s) { return s.level > 0; }).length
      },
      lineAt: function (no) {
        return lines[Math.min(lines.length - 1, Math.max(0, no - 1))] || null;
      }
    };
  }

  return { parsePrompt: parsePrompt, VAR_RE: VAR_RE, renderTemplate: renderTemplate };

  /**
   * 变量渲染：把 {{name}} 替换成填好的值。
   * 这就是「变量契约」的验证手段 —— 渲染一遍，才知道 prompt 会长成什么样。
   * @param {string} text
   * @param {object} values {name: string}
   * @returns {{text:string, missing:string[], used:string[]}}
   */
  function renderTemplate(text, values) {
    var vals = values || {};
    var used = [];
    var missing = [];
    var out = normalize(text).replace(VAR_RE, function (m, rawName) {
      var name = String(rawName || '').trim();
      if (used.indexOf(name) === -1) used.push(name);
      if (Object.prototype.hasOwnProperty.call(vals, name) && vals[name] !== '') return String(vals[name]);
      if (missing.indexOf(name) === -1) missing.push(name);
      return m;
    });
    return { text: out, missing: missing, used: used };
  }

}));
