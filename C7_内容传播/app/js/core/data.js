// 本文件由 tools/gen_data_js.py 生成，请勿手改。
// 源数据：数据/title_rubric.json、数据/titles_scored.csv、数据/projection_params.csv、数据/repo_facts.csv
// 改了任何一个 CSV/JSON 都要重跑：python tools/gen_data_js.py
(function (root) {
  var DATA = {
  "meta": {
    "as_of_commit": "165f7d3d7d0ad5d6a2339402528e46bf42cecc81",
    "as_of_date": "2026-11-15",
    "total_commits": 127,
    "total_files": 1355,
    "total_tests": 464,
    "generator": "tools/gen_data_js.py"
  },
  "rubric": {
    "version": 1,
    "updated": "2026-11-15",
    "note": "标题评分是确定性的：同一份 JSON 驱动 Python(tools/title_score.py) 与 JS(app/js/core/titlescore.js)，两边必须给出完全相同的分数，由 tests/titlescore-parity.test.js 保证。改这里就要重跑 tools/title_score.py 与 node tools/gen_data_js.js。",
    "dimensions": [
      {
        "id": "hook",
        "label": "钩子强度",
        "max": 25
      },
      {
        "id": "specificity",
        "label": "具体性",
        "max": 20
      },
      {
        "id": "searchability",
        "label": "检索性",
        "max": 15
      },
      {
        "id": "platformFit",
        "label": "平台适配",
        "max": 20
      },
      {
        "id": "credibility",
        "label": "可信度",
        "max": 20
      }
    ],
    "hook": {
      "base": 8,
      "rules": [
        {
          "id": "hasDigits",
          "kind": "regex",
          "value": "[0-9]+",
          "points": 4,
          "cap": 4,
          "label": "含阿拉伯数字"
        },
        {
          "id": "hasQuestion",
          "kind": "regex",
          "value": "[？?]",
          "points": 3,
          "cap": 3,
          "label": "含疑问/设问"
        },
        {
          "id": "hasContrast",
          "kind": "words",
          "value": [
            "不是",
            "而是",
            "才",
            "反而",
            "却"
          ],
          "points": 3,
          "cap": 3,
          "label": "含反差/转折"
        },
        {
          "id": "hasStrong",
          "kind": "words",
          "value": [
            "最",
            "唯一",
            "十倍",
            "归零",
            "稀缺",
            "重要"
          ],
          "points": 3,
          "cap": 3,
          "label": "含强判断"
        },
        {
          "id": "hasCost",
          "kind": "words",
          "value": [
            "骗",
            "坑",
            "事故",
            "失败",
            "误伤",
            "坏",
            "冤枉",
            "假"
          ],
          "points": 4,
          "cap": 4,
          "label": "含代价/损失词"
        }
      ]
    },
    "specificity": {
      "base": 6,
      "rules": [
        {
          "id": "numberDensity",
          "kind": "regexCount",
          "value": "[0-9]+",
          "points": 2,
          "cap": 6,
          "label": "数字密度"
        },
        {
          "id": "domainTerms",
          "kind": "wordCount",
          "value": [
            "AI",
            "prompt",
            "DOI",
            "arXiv",
            "测试",
            "仓库",
            "流水线",
            "按钮",
            "文献",
            "引用"
          ],
          "points": 2,
          "cap": 6,
          "label": "领域术语"
        },
        {
          "id": "concreteObject",
          "kind": "words",
          "value": [
            "清单",
            "交付物",
            "挑战",
            "文章",
            "报告",
            "表格"
          ],
          "points": 2,
          "cap": 2,
          "label": "具体产物"
        }
      ]
    },
    "searchability": {
      "base": 5,
      "rules": [
        {
          "id": "keywords",
          "kind": "wordCount",
          "value": [
            "验收",
            "AI",
            "交付",
            "测试",
            "清单",
            "prompt",
            "方法",
            "可信",
            "文献",
            "引用",
            "流水线",
            "生成"
          ],
          "points": 3,
          "cap": 10,
          "label": "检索关键词覆盖"
        }
      ]
    },
    "platformFit": {
      "base": 0,
      "bands": [
        {
          "maxLength": 24,
          "minLength": 16,
          "score": 20,
          "label": "公众号最佳区间 16–24 字"
        },
        {
          "maxLength": 28,
          "minLength": 12,
          "score": 14,
          "label": "可接受 12–15 / 25–28 字"
        },
        {
          "maxLength": 34,
          "minLength": 8,
          "score": 8,
          "label": "偏短或偏长 8–11 / 29–34 字"
        },
        {
          "maxLength": 999,
          "minLength": 0,
          "score": 4,
          "label": "过长或过短"
        }
      ],
      "penalties": [
        {
          "id": "clickbait",
          "kind": "wordCount",
          "value": [
            "震惊",
            "必看",
            "速看",
            "99%",
            "所有人",
            "一定",
            "彻底",
            "完美",
            "最强"
          ],
          "points": -5,
          "cap": -10,
          "label": "标题党/绝对化用词"
        },
        {
          "id": "multiQuestion",
          "kind": "regexCount",
          "value": "[？?]",
          "points": -2,
          "cap": -4,
          "label": "连续多问号"
        }
      ]
    },
    "credibility": {
      "base": 20,
      "penalties": [
        {
          "id": "hype",
          "kind": "wordCount",
          "value": [
            "震惊",
            "必看",
            "速看",
            "99%",
            "所有人",
            "一定"
          ],
          "points": -6,
          "cap": -12,
          "label": "夸张承诺"
        },
        {
          "id": "absolutism",
          "kind": "wordCount",
          "value": [
            "彻底",
            "完美",
            "最强",
            "永远",
            "绝对"
          ],
          "points": -4,
          "cap": -8,
          "label": "绝对化表述"
        },
        {
          "id": "unsupported",
          "kind": "words",
          "value": [
            "十倍",
            "100倍",
            "全都"
          ],
          "points": -3,
          "cap": -3,
          "label": "无依据的倍数词"
        }
      ],
      "bonuses": [
        {
          "id": "groundedNumber",
          "kind": "regex",
          "value": "[0-9]+",
          "points": 2,
          "cap": 2,
          "label": "数字有出处感"
        }
      ]
    },
    "thresholds": {
      "strong": 75,
      "usable": 64,
      "weak": 52
    },
    "veto": {
      "words": [
        "震惊",
        "必看",
        "速看",
        "99%",
        "绝对",
        "史上最"
      ],
      "cap": 40,
      "label": "标题党/绝对化用词，一票否决"
    },
    "tieBreak": [
      "total:desc",
      "specificity:desc",
      "hook:desc",
      "id:asc"
    ]
  },
  "titles": [
    {
      "id": "E4",
      "formula": "方法论型",
      "title": "从 C1 到 C6：一个人怎么把 AI 协作做成流水线",
      "chars": 22,
      "hook": 12,
      "specificity": 14,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 77,
      "grade": "主推"
    },
    {
      "id": "B1",
      "formula": "反差型",
      "title": "AI 生成的东西 90% 的工夫花在证明它没骗你",
      "chars": 21,
      "hook": 16,
      "specificity": 10,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 77,
      "grade": "主推"
    },
    {
      "id": "D6",
      "formula": "身份型",
      "title": "我在 6 个挑战里踩过的 3 个坑和一张清单",
      "chars": 18,
      "hook": 16,
      "specificity": 12,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 76,
      "grade": "主推"
    },
    {
      "id": "A6",
      "formula": "数字型",
      "title": "12 条验收清单我每份交付物上线前都过一遍",
      "chars": 20,
      "hook": 12,
      "specificity": 10,
      "searchability": 14,
      "platformFit": 20,
      "credibility": 20,
      "total": 76,
      "grade": "主推"
    },
    {
      "id": "A2",
      "formula": "数字型",
      "title": "127 次提交、464 项测试：验收的三条硬结论",
      "chars": 22,
      "hook": 12,
      "specificity": 12,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 75,
      "grade": "主推"
    },
    {
      "id": "D2",
      "formula": "身份型",
      "title": "一个人做 6 个 AI 项目我靠什么保证不出事故",
      "chars": 20,
      "hook": 16,
      "specificity": 10,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 74,
      "grade": "可用"
    },
    {
      "id": "C1",
      "formula": "悬念型",
      "title": "为什么你的 AI 交付物看起来都对一查就有坑？",
      "chars": 21,
      "hook": 15,
      "specificity": 10,
      "searchability": 11,
      "platformFit": 18,
      "credibility": 20,
      "total": 74,
      "grade": "可用"
    },
    {
      "id": "A3",
      "formula": "数字型",
      "title": "131 个测试里最重要的那一条叫「合格样例零命中」",
      "chars": 24,
      "hook": 15,
      "specificity": 10,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 73,
      "grade": "可用"
    },
    {
      "id": "A5",
      "formula": "数字型",
      "title": "测试全绿但按钮是坏的这类 bug 最难抓",
      "chars": 18,
      "hook": 15,
      "specificity": 10,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 73,
      "grade": "可用"
    },
    {
      "id": "E6",
      "formula": "方法论型",
      "title": "交付物的第 90 分是把证明过程也交付出去",
      "chars": 19,
      "hook": 12,
      "specificity": 10,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 73,
      "grade": "可用"
    },
    {
      "id": "C4",
      "formula": "悬念型",
      "title": "你的验收清单里有没有一条「反向测试」？",
      "chars": 19,
      "hook": 11,
      "specificity": 10,
      "searchability": 14,
      "platformFit": 18,
      "credibility": 20,
      "total": 73,
      "grade": "可用"
    },
    {
      "id": "D4",
      "formula": "身份型",
      "title": "团队把 AI 接进流水线之前先把验收接进去",
      "chars": 19,
      "hook": 8,
      "specificity": 10,
      "searchability": 14,
      "platformFit": 20,
      "credibility": 20,
      "total": 72,
      "grade": "可用"
    },
    {
      "id": "B6",
      "formula": "反差型",
      "title": "我不是被 AI 骗了是被它的格式骗了",
      "chars": 16,
      "hook": 15,
      "specificity": 8,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 71,
      "grade": "可用"
    },
    {
      "id": "E2",
      "formula": "方法论型",
      "title": "把「看起来对」当红旗：一套 AI 交付验收方法",
      "chars": 21,
      "hook": 8,
      "specificity": 8,
      "searchability": 15,
      "platformFit": 20,
      "credibility": 20,
      "total": 71,
      "grade": "可用"
    },
    {
      "id": "C2",
      "formula": "悬念型",
      "title": "AI 编的参考文献格式为什么能一条不错？",
      "chars": 19,
      "hook": 11,
      "specificity": 10,
      "searchability": 11,
      "platformFit": 18,
      "credibility": 20,
      "total": 70,
      "grade": "可用"
    },
    {
      "id": "B2",
      "formula": "反差型",
      "title": "让 AI 多写点不是问题先让它能被验收",
      "chars": 17,
      "hook": 11,
      "specificity": 8,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 70,
      "grade": "可用"
    },
    {
      "id": "D1",
      "formula": "身份型",
      "title": "写给独立开发者：AI 交付的验收课",
      "chars": 16,
      "hook": 8,
      "specificity": 8,
      "searchability": 14,
      "platformFit": 20,
      "credibility": 20,
      "total": 70,
      "grade": "可用"
    },
    {
      "id": "E3",
      "formula": "方法论型",
      "title": "证据要能被重跑：AI 交付的可信度工程",
      "chars": 18,
      "hook": 8,
      "specificity": 8,
      "searchability": 14,
      "platformFit": 20,
      "credibility": 20,
      "total": 70,
      "grade": "可用"
    },
    {
      "id": "D3",
      "formula": "身份型",
      "title": "如果你也在用 AI 写论文先看这份引用核验流程",
      "chars": 21,
      "hook": 8,
      "specificity": 10,
      "searchability": 11,
      "platformFit": 20,
      "credibility": 20,
      "total": 69,
      "grade": "可用"
    },
    {
      "id": "C3",
      "formula": "悬念型",
      "title": "测试全绿功能是坏的：这种事怎么发生的？",
      "chars": 19,
      "hook": 15,
      "specificity": 8,
      "searchability": 8,
      "platformFit": 18,
      "credibility": 20,
      "total": 69,
      "grade": "可用"
    },
    {
      "id": "A4",
      "formula": "数字型",
      "title": "438 项自测之后我把验收拆成了三层",
      "chars": 17,
      "hook": 12,
      "specificity": 8,
      "searchability": 8,
      "platformFit": 20,
      "credibility": 20,
      "total": 68,
      "grade": "可用"
    },
    {
      "id": "E5",
      "formula": "方法论型",
      "title": "别让 AI 直觉验收 AI 产出",
      "chars": 12,
      "hook": 8,
      "specificity": 10,
      "searchability": 14,
      "platformFit": 14,
      "credibility": 20,
      "total": 66,
      "grade": "可用"
    },
    {
      "id": "B4",
      "formula": "反差型",
      "title": "工具的第一版不是用来抓错的是用来不冤枉人的",
      "chars": 21,
      "hook": 15,
      "specificity": 6,
      "searchability": 5,
      "platformFit": 20,
      "credibility": 20,
      "total": 66,
      "grade": "可用"
    },
    {
      "id": "C5",
      "formula": "悬念型",
      "title": "当生成不要钱你还在用「再读一遍」验收吗？",
      "chars": 20,
      "hook": 11,
      "specificity": 6,
      "searchability": 11,
      "platformFit": 18,
      "credibility": 20,
      "total": 66,
      "grade": "可用"
    },
    {
      "id": "B3",
      "formula": "反差型",
      "title": "最贵的 bug 不是跑不起来是跑起来了还看着对",
      "chars": 21,
      "hook": 14,
      "specificity": 6,
      "searchability": 5,
      "platformFit": 20,
      "credibility": 20,
      "total": 65,
      "grade": "可用"
    },
    {
      "id": "D5",
      "formula": "身份型",
      "title": "给非科班同学的 AI 交付自查表",
      "chars": 14,
      "hook": 8,
      "specificity": 8,
      "searchability": 11,
      "platformFit": 14,
      "credibility": 20,
      "total": 61,
      "grade": "备选"
    },
    {
      "id": "A1",
      "formula": "数字型",
      "title": "一个能打开的假 arXiv ID 让我重写了整套核验流程",
      "chars": 25,
      "hook": 12,
      "specificity": 8,
      "searchability": 5,
      "platformFit": 14,
      "credibility": 20,
      "total": 59,
      "grade": "备选"
    },
    {
      "id": "B5",
      "formula": "反差型",
      "title": "生成成本归零之后稀缺的是验得快",
      "chars": 15,
      "hook": 11,
      "specificity": 6,
      "searchability": 8,
      "platformFit": 14,
      "credibility": 20,
      "total": 59,
      "grade": "备选"
    },
    {
      "id": "E1",
      "formula": "方法论型",
      "title": "验收的三层：能跑能复算能截图",
      "chars": 14,
      "hook": 8,
      "specificity": 6,
      "searchability": 8,
      "platformFit": 14,
      "credibility": 20,
      "total": 56,
      "grade": "备选"
    },
    {
      "id": "C6",
      "formula": "悬念型",
      "title": "谁在为 AI 的产出兜底？",
      "chars": 11,
      "hook": 11,
      "specificity": 8,
      "searchability": 8,
      "platformFit": 6,
      "credibility": 20,
      "total": 53,
      "grade": "备选"
    },
    {
      "id": "F1",
      "formula": "对照(标题党)",
      "title": "震惊！AI 写的东西 99% 都是假的必看！",
      "chars": 19,
      "hook": 16,
      "specificity": 10,
      "searchability": 8,
      "platformFit": 10,
      "credibility": 10,
      "total": 40,
      "grade": "弃用"
    },
    {
      "id": "F2",
      "formula": "对照(标题党)",
      "title": "彻底解决 AI 幻觉！这套方法绝对完美",
      "chars": 17,
      "hook": 8,
      "specificity": 8,
      "searchability": 11,
      "platformFit": 10,
      "credibility": 12,
      "total": 40,
      "grade": "弃用"
    }
  ],
  "params": {
    "公众号": {
      "exposure": 860,
      "open_rate": 0.09,
      "click_rate": 1,
      "read_through": 0.42,
      "engage_rate": 0.035,
      "convert_rate": 0.016,
      "day1_weight": 0.46,
      "day2_weight": 0.21,
      "day3_weight": 0.12,
      "day4_weight": 0.07,
      "day5_weight": 0.06,
      "day6_weight": 0.04,
      "day7_weight": 0.04
    },
    "知乎": {
      "exposure": 4200,
      "open_rate": 1,
      "click_rate": 0.065,
      "read_through": 0.35,
      "engage_rate": 0.022,
      "convert_rate": 0.012,
      "day1_weight": 0.38,
      "day2_weight": 0.19,
      "day3_weight": 0.14,
      "day4_weight": 0.11,
      "day5_weight": 0.08,
      "day6_weight": 0.06,
      "day7_weight": 0.04
    },
    "小红书": {
      "exposure": 3600,
      "open_rate": 1,
      "click_rate": 0.11,
      "read_through": 0.28,
      "engage_rate": 0.06,
      "convert_rate": 0.008,
      "day1_weight": 0.55,
      "day2_weight": 0.17,
      "day3_weight": 0.1,
      "day4_weight": 0.07,
      "day5_weight": 0.05,
      "day6_weight": 0.03,
      "day7_weight": 0.03
    },
    "即刻": {
      "exposure": 1200,
      "open_rate": 1,
      "click_rate": 0.18,
      "read_through": 0.55,
      "engage_rate": 0.09,
      "convert_rate": 0.02,
      "day1_weight": 0.62,
      "day2_weight": 0.14,
      "day3_weight": 0.08,
      "day4_weight": 0.06,
      "day5_weight": 0.04,
      "day6_weight": 0.03,
      "day7_weight": 0.03
    }
  },
  "channels": [
    "公众号",
    "知乎",
    "小红书",
    "即刻"
  ],
  "facts": [
    {
      "scope": "C1_交付",
      "files": 840,
      "kb": 39999,
      "commits": 5,
      "tests_computed": 0,
      "tests_py": 0,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    },
    {
      "scope": "C2_交付",
      "files": 13,
      "kb": 449,
      "commits": 1,
      "tests_computed": 0,
      "tests_py": 0,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    },
    {
      "scope": "C2A_C9_交付",
      "files": 40,
      "kb": 742,
      "commits": 1,
      "tests_computed": 35,
      "tests_py": 35,
      "tests_js": 0,
      "declared_tests": 35,
      "declared_source": "C2A_C9_交付/README.md"
    },
    {
      "scope": "C2G_ParameterGolf",
      "files": 43,
      "kb": 1358,
      "commits": 50,
      "tests_computed": 0,
      "tests_py": 0,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    },
    {
      "scope": "C3_交付",
      "files": 20,
      "kb": 81,
      "commits": 1,
      "tests_computed": 12,
      "tests_py": 12,
      "tests_js": 0,
      "declared_tests": 12,
      "declared_source": "C3_交付/README.md"
    },
    {
      "scope": "C3C_交付",
      "files": 39,
      "kb": 293,
      "commits": 2,
      "tests_computed": 108,
      "tests_py": 108,
      "tests_js": 0,
      "declared_tests": 108,
      "declared_source": "C3C_交付/README.md"
    },
    {
      "scope": "C4A_交付",
      "files": 37,
      "kb": 550,
      "commits": 1,
      "tests_computed": 26,
      "tests_py": 26,
      "tests_js": 0,
      "declared_tests": 26,
      "declared_source": "C4A_交付/README.md"
    },
    {
      "scope": "C4B_公众号文章生成技能",
      "files": 18,
      "kb": 220,
      "commits": 2,
      "tests_computed": 0,
      "tests_py": 0,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    },
    {
      "scope": "C4C_交付",
      "files": 75,
      "kb": 69354,
      "commits": 3,
      "tests_computed": 0,
      "tests_py": 0,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    },
    {
      "scope": "C4D_交付",
      "files": 52,
      "kb": 1473,
      "commits": 2,
      "tests_computed": 38,
      "tests_py": 38,
      "tests_js": 0,
      "declared_tests": 38,
      "declared_source": "C4D_交付/README.md"
    },
    {
      "scope": "C5_交付",
      "files": 63,
      "kb": 203,
      "commits": 4,
      "tests_computed": 81,
      "tests_py": 81,
      "tests_js": 0,
      "declared_tests": 81,
      "declared_source": "C5_交付/README.md"
    },
    {
      "scope": "C5A_仓库分析",
      "files": 20,
      "kb": 215,
      "commits": 13,
      "tests_computed": 15,
      "tests_py": 15,
      "tests_js": 0,
      "declared_tests": 15,
      "declared_source": "C5A_仓库分析/README.md"
    },
    {
      "scope": "C6_交付",
      "files": 60,
      "kb": 919,
      "commits": 8,
      "tests_computed": 131,
      "tests_py": 0,
      "tests_js": 131,
      "declared_tests": 131,
      "declared_source": "C6_交付/README.md"
    },
    {
      "scope": "C6A_交付",
      "files": 35,
      "kb": 4603,
      "commits": 1,
      "tests_computed": 18,
      "tests_py": 18,
      "tests_js": 0,
      "declared_tests": null,
      "declared_source": ""
    }
  ]
};
  if (typeof module === 'object' && module.exports) module.exports = DATA;
  else root.C7DATA = DATA;
})(typeof self !== 'undefined' ? self : this);
