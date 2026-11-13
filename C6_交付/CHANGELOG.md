# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。日期为本地时间。

## [1.0.0] — 2026-11-13

C6 交付版本。首个对外可用版本。

### 新增

- **Web 应用**（`app/`）：零依赖、零构建、可 `file://` 直接打开。
  - 15 条静态规则（PG001–PG015），分「安全 / 稳定性 / 可维护 / 成本」四类。
  - 变量契约：解析 `{{x}}`、统计出现次数与行号、命名检查、渲染预览。
  - 成本预算：8 个模型 × 输入/输出单价 × 调用量假设，价格可在线编辑。
  - 版本快照（最多 20 条，localStorage）＋ 行级 LCS diff。
  - 门禁阈值（error/warning/none）＋ 基线忽略（指纹不含行号）。
  - 导出 Markdown / JSON / SARIF 2.1.0。
  - PWA：`manifest.webmanifest` + Service Worker 预缓存，二次访问离线可用。
  - 深/浅色主题、窄屏适配、`prefers-reduced-motion`、打印样式。
- **CLI**（`tools/promptgate-cli.js`）：与 Web 共用同一套引擎，退出码 `0/1/2`。
  - `--format text|markdown|json|sarif`、`--fail-on`、`--disable`、`--baseline`、
    `--save-baseline`、`--out`、`--quiet`、`--list-rules`，支持 stdin。
- **文档生成**（`tools/gen_rules_doc.js`）：`docs/rules.md` 从规则定义生成，
  `--check` 用于 CI 的文档漂移检测。
- **测试**（`tests/`）：131 项，零第三方依赖（`node:test`）。
- **CI**（`.github/workflows/c6-ci.yml`）：测试 + 文档漂移检查。
- **部署**（`.github/workflows/c6-pages.yml`）：`app/` 自动发布到 GitHub Pages。
- **演示**（`demo/`）：演示脚本、7 张真实截图、CLI 实跑输出。

### 已知问题 / 取舍

- 规则为启发式静态分析，不评估 prompt 的**效果**。
- token 为估算（±20%），价格为 2026-11-01 快照。
- 版本数据仅存本地，不跨设备同步，上限 20 条。
- 窄屏（< 720px）隐藏行号槽并允许折行，牺牲「点行号跳转」。
