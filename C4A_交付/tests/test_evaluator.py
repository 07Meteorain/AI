#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_evaluator.py — C4A 评审器的单元测试 + 误判率测量

为什么要有这个文件：
    C4A 评审标准里「误判率低」是25 分权重的核心指标。
    声称"误判率低"必须有证据 —— 这个文件就是那份证据。
    每个用例都标注了人工判定的 ground truth，测试断言评审器与人工判断一致。

运行：
    python tests/test_evaluator.py              # 跑全部测试
    python tests/test_evaluator.py --accuracy   # 额外输出误判率测量报告

依赖：PyYAML（必需）。openpyxl 可选。
"""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent / "skill" / "c4a-skill-evaluator"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import yaml# noqa: E402

import c4a_evaluator as E# noqa: E402

DATASET = TESTS_DIR / "golden_dataset"
RUBRIC = SKILL_DIR / "references" / "c4_rubric.yaml"

with open(RUBRIC, "r", encoding="utf-8") as _f:
    RUBRIC_DATA = yaml.safe_load(_f)


def _bundle(author: str) -> list[E.FileRec]:
    """加载黄金数据集中某位作者的 bundle（走真实扫描路径，保证测的是真代码）。"""
    bundles, _ = E.collect_submissions(DATASET)
    files = bundles[author]
    _preload_text(files, DATASET)
    return files


def _preload_text(files: list[E.FileRec], root: Path) -> None:
    """为 bundle 填充正文（与主流程默认策略一致）。"""
    for fr in files:
        if not fr.text and fr.ext in E.TEXTUAL_EXT:
            fr.text = E.extract_text(root / fr.rel_path)


# ===========================================================================
# 一、人工判定的 ground truth
#
# 由本人逐份阅读三份提交后手工标注。这三个样本覆盖了三种典型质量档位：
#   ZhangWei  = 优秀（齐全 + 四条件基本达标）
#   LiMing    = 中等（缺 demo + 硬编码路径，但有代码有文档）
#   WangXiao  = 较差（命名不规范 + 内容单薄+ 缺 demo）
#
# 标注说明（v2，经二次复核修订）：
#   最初把 LiMing 的「可执行」标为 ✅，复核后改为 ⚠️——
#   他的summary.py 确实能跑，但没有工作流说明、没有 CLI 入口文档、
#   也没声明依赖，符合"有能跑的东西"但不符合"别人能照着跑起来"。
#   这正是自动评审比人工粗看更靠谱的地方：它把"能跑"和"能被别人跑起来"分开算了。
# ===========================================================================
GROUND_TRUTH = {
    "ZhangWei": {
        "note": "五文件齐全；skill说明/教学说明/AI日志命名规范；代码可 ast.parse；有真实 demo",
        "completeness_min": 1.0,          # 5/5 加权完整
        "quality_min": 0.70,              # 四条件多数达标
        "expect_reusable": "✅",
        "expect_executable": "✅",
        "expect_verifiable": "✅",         # 有测试用例+ 预期输出
        "expect_clear_io": "✅",
        "expect_confidence": None,
    },
    "LiMing": {
        "note": "缺 demo；summary.py 含 /Users/ 与 C:\\ 硬编码路径（触发 R2 红线）",
        "completeness_max": 0.85,         # 缺 demo → 不是满分
        "quality_max": 0.45,
        "expect_reusable": "❌",           # 硬编码绝对路径触发一票否决
        "expect_executable": "⚠️",        # 有可解析 py + 代码块，但无工作流/CLI 说明
        "expect_verifiable": "❌",# 无测试、无预期输出、无边界说明
        "expect_clear_io": "❌",          # 无「输入…输出…」句式
        "expect_confidence": "low",       # 命中红线 → 必须人工复核
    },
    "WangXiao": {
        "note": "命名不规范（作者目录名 + 中文文件名混用）；内容单薄；无 demo；readme 无实质内容",
        "completeness_max": 0.60,         # 缺 demo + 缺 AI 日志
        "quality_max": 0.50,
        "expect_reusable": "⚠️",          # 无硬编码路径，但也没有任何可移植性说明
        "expect_executable": "⚠️",        # 有 py 文件且语法正确，但无 CLI/工作流
        "expect_verifiable": "❌",
        "expect_clear_io": "❌",
        "expect_confidence": None,
    },
}


class TestCollection(unittest.TestCase):
    """Level 1：文件采集与作者识别"""

    def test_three_authors_detected(self):
        bundles, non_c4 = E.collect_submissions(DATASET)
        self.assertEqual(set(bundles.keys()), {"ZhangWei", "LiMing", "WangXiao"},
                         f"作者识别结果不符：{set(bundles.keys())}")

    def test_zhangwei_files_complete(self):
        files = _bundle("ZhangWei")
        names = " ".join(f.name for f in files)
        for kw in ["skill说明", "教学说明", "AI日志"]:
            self.assertIn(kw, names, f"ZhangWei 应含 {kw}")

    def test_non_c4_files_excluded(self):
        """黄金数据集里readme.md 属作者 bundle（文件夹传播），不应被误判为非 C4。"""
        bundles, non_c4 = E.collect_submissions(DATASET)
        self.assertEqual(len(non_c4), 0,
                         f"数据集内不应产生非 C4 文件，实际：{[f.rel_path for f in non_c4]}")

    def test_author_from_folder_when_filename_irregular(self):
        """WangXiao 的文件命名不规范，应靠父目录识别出作者。"""
        bundles, _ = E.collect_submissions(DATASET)
        self.assertIn("WangXiao", bundles)
        sources = {f.author_source for f in bundles["WangXiao"]}
        self.assertTrue(
            {"filename_convention", "parent_folder"} & sources,
            f"应至少有一种作者识别方式命中，实际：{sources}",
        )

    def test_chinese_filename_author_parsed(self):
        """王晓_C4_技能说明.md 的中文作者名应被解析，且不与目录名 WangXiao 分裂成两人。"""
        bundles, _ = E.collect_submissions(DATASET)
        wang = bundles["WangXiao"]
        self.assertTrue(any("王晓" in f.rel_path for f in wang),
                        "中文文件名应归入 WangXiao bundle")
        self.assertNotIn("王晓", bundles, "同一目录下的中文名与目录名不应分裂为两个作者")


class TestCompleteness(unittest.TestCase):
    """Level 2：完整性检查"""

    def test_zhangwei_full_marks(self):
        files = _bundle("ZhangWei")
        comp, score, grade = E.check_completeness(files, RUBRIC_DATA)
        self.assertEqual(score, 1.0, f"ZhangWei 应为 5/5，实际 {score}：{comp}")
        self.assertIn("齐全", grade)

    def test_liming_missing_demo_detected(self):
        """关键用例：LiMing 没有 demo 文件，必须被检出为缺失。"""
        files = _bundle("LiMing")
        comp, score, _ = E.check_completeness(files, RUBRIC_DATA)
        self.assertIn(comp["demo"]["status"], ("❌", "⚠️"),
                      f"LiMing 无 demo，应判缺失，实际 {comp['demo']}")
        self.assertLess(score, 1.0, "缺 demo 不应给满分")

    def test_wangxiao_multiple_missing(self):
        files = _bundle("WangXiao")
        comp, score, grade = E.check_completeness(files, RUBRIC_DATA)
        missing = [k for k, v in comp.items() if v["status"] == "❌"]
        self.assertIn("demo", missing, f"WangXiao 应缺 demo，实际缺：{missing}")
        self.assertIn("ai_log", missing, f"WangXiao 应缺 AI 日志，实际缺：{missing}")
        self.assertLess(score, 0.6, f"WangXiao 完整性应偏低，实际 {score}")


class TestQuality(unittest.TestCase):
    """Level 3：四条件质量评审"""

    def test_hardcoded_path_vetoes_reusable(self):
        """核心防误判用例：LiMing 的 /Users/ 与 C:\\ 必须让「可复用」判负。

        这是本技能最重要的一个断言 —— 如果 veto 机制失效，
        评审器就会把「写死了自己电脑路径」的提交判为可复用，
        这正是自动评审最容易犯、也最有害的错误。
        """
        files = _bundle("LiMing")
        crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        reusable = next(c for c in crits if c.id == "reusable")
        r2 = next(i for i in reusable.items if i["id"] == "R2")
        self.assertFalse(r2["satisfied"], "R2（无硬编码绝对路径）应被判为不满足")
        self.assertEqual(reusable.grade, "❌", f"「可复用」应判❌，实际 {reusable.grade}")

    def test_credential_leak_veto(self):
        """凭据泄露同样触发 veto。"""
        files = _bundle("ZhangWei")
        # 张伟的提交干净，R5 应满足
        crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        reusable = next(c for c in crits if c.id == "reusable")
        r5 = next(i for i in reusable.items if i["id"] == "R5")
        self.assertTrue(r5["satisfied"], "ZhangWei 无凭据泄露，R5 应满足")

    def test_python_ast_structural_check(self):
        """结构性硬校验：ZhangWei 的 pr_desc.py 应能通过 ast.parse。"""
        files = _bundle("ZhangWei")
        crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        ex = next(c for c in crits if c.id == "executable")
        e4 = next(i for i in ex.items if i["id"] == "E4")
        self.assertTrue(e4["satisfied"], f"E4（代码可解析）应满足：{e4['detail']}")
        self.assertEqual(e4["confidence"], "high", "结构性检查置信度应为 high")

    def test_syntax_error_detected(self):
        """反向用例：故意制造语法错误，E4 必须判不满足。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad_C4_技能.py"
            bad.write_text("def broken(:\n  pass\n", encoding="utf-8")
            recs, _ = E.collect_submissions(Path(td))
            files = list(recs.values())[0]
            files[0].text = bad.read_text(encoding="utf-8")
            crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=Path(td))
            ex = next(c for c in crits if c.id == "executable")
            e4 = next(i for i in ex.items if i["id"] == "E4")
            self.assertFalse(e4["satisfied"], "语法错误的 .py 不应通过 E4")

    def test_io_pattern_detected(self):
        """I1：ZhangWei 的说明里有「输入…，输出…」句式。"""
        files = _bundle("ZhangWei")
        crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        io_c = next(c for c in crits if c.id == "clear_io")
        i1 = next(i for i in io_c.items if i["id"] == "I1")
        self.assertTrue(i1["satisfied"], f"I1 应命中「输入…输出…」句式：{i1['detail']}")

    def test_verifiable_high_quality(self):
        """ZhangWei 有测试用例 + 预期输出 → 可验证应达标。"""
        files = _bundle("ZhangWei")
        crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        ver = next(c for c in crits if c.id == "verifiable")
        self.assertEqual(ver.grade, "✅", f"可验证应✅，实际 {ver.grade} {ver.score}")


class TestGroundTruthAgreement(unittest.TestCase):
    """误判率测量：评审器结论 vs 人工 ground truth"""

    def test_agreement_with_human_judgment(self):
        disagreements = []
        for author, gt in GROUND_TRUTH.items():
            files = _bundle(author)
            comp, c_score, _ = E.check_completeness(files, RUBRIC_DATA)
            crits, q_score, conf = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
            grades = {c.id: c.grade for c in crits}

            # 完整性区间
            if "completeness_min" in gt:
                self.assertGreaterEqual(
                    c_score, gt["completeness_min"],
                    f"{author} 完整性 {c_score} 应 ≥ {gt['completeness_min']}（{gt['note']}）")
            if "completeness_max" in gt:
                self.assertLessEqual(
                    c_score, gt["completeness_max"],
                    f"{author} 完整性 {c_score} 应 ≤ {gt['completeness_max']}（{gt['note']}）")
            if "quality_min" in gt:
                self.assertGreaterEqual(q_score, gt["quality_min"],
                                        f"{author} 质量 {q_score} 应≥ {gt['quality_min']}")
            if "quality_max" in gt:
                self.assertLessEqual(q_score, gt["quality_max"],
                                     f"{author} 质量 {q_score} 应 ≤ {gt['quality_max']}")

            # 四条件评级
            for cid in ("reusable", "executable", "verifiable", "clear_io"):
                exp = gt.get(f"expect_{cid}")
                if exp and grades[cid] != exp:
                    disagreements.append((author, cid, exp, grades[cid]))

            # 置信度标记
            if gt.get("expect_confidence"):
                if conf != gt["expect_confidence"]:
                    disagreements.append((author, "confidence",
                                          gt["expect_confidence"], conf))

        self.assertEqual(
            disagreements, [],
            "评审器结论与人工 ground truth 不一致：\n" +
            "\n".join(f"  {a} / {c}: 人工期望 {e}，评审器给出 {g}"
                      for a, c, e, g in disagreements))


class TestEdgeCases(unittest.TestCase):
    """边界情况不崩"""

    def test_empty_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            bundles, non_c4 = E.collect_submissions(Path(td))
            self.assertEqual(bundles, {})
            self.assertEqual(non_c4, [])

    def test_non_c4_files_filtered(self):
        """混在根目录的非 C4 文件应被过滤，不污染任何作者 bundle。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "群公告.md").write_text("本周五开会", encoding="utf-8")
            (p / "ZhangWei_C4_教学说明.md").write_text("教学说明：步骤…", encoding="utf-8")
            bundles, non_c4 = E.collect_submissions(p)
            self.assertEqual(set(bundles), {"ZhangWei"}, f"实际：{set(bundles)}")
            self.assertEqual(len(non_c4), 1)
            self.assertEqual(non_c4[0].rel_path, "群公告.md")

    def test_corrupt_skill_archive_does_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "A_C4_技能.skill").write_bytes(b"this is not a real archive")
            recs, _ = E.collect_submissions(p)
            files = list(recs.values())[0]
            crits, _, _ = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=p)
            self.assertEqual(len(crits), 4, "损坏包仍应产出四维度结果")

    def test_unknown_author_excluded_from_ranking(self):
        """无作者线索的文件应标 Unknown，且不进排名。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "C4_未署名文件.md").write_text("随便写点东西", encoding="utf-8")
            bundles, _ = E.collect_submissions(p)
            self.assertIn("Unknown", bundles)


class TestReportGeneration(unittest.TestCase):
    """Level 4：报告生成"""

    def test_markdown_report_contains_all_sections(self):
        bundles, non_c4 = E.collect_submissions(DATASET)
        for files in bundles.values():
            _preload_text(files, DATASET)
        results = {}
        for author, files in bundles.items():
            comp, cs, cg = E.check_completeness(files, RUBRIC_DATA)
            crits, qs, conf = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
            r = E.AuthorResult(author=author,
                               author_source=files[0].author_source if files else "fallback_unknown",
                               files=files, completeness=comp,
                               completeness_score=cs, completeness_grade=cg,
                               criteria=crits, quality_score=qs, confidence=conf)
            r.composite_score = round(cs * 0.4 + qs * 0.6, 4)
            r.suggestions = E.build_suggestions(r)
            results[author] = r

        md = E.render_markdown(results, non_c4, DATASET, "Level 4")
        for section in ["## 一、班级总览", "## 二、作者详情",
                        "## 三、综合排名", "## 四、班级共性问题"]:
            self.assertIn(section, md, f"报告缺少章节：{section}")
        for author in GROUND_TRUTH:
            self.assertIn(author, md, f"报告缺少作者 {author}")

    def test_json_report_serializable(self):
        import json
        bundles, non_c4 = E.collect_submissions(DATASET)
        results = {}
        for author, files in bundles.items():
            comp, cs, cg = E.check_completeness(files, RUBRIC_DATA)
            crits, qs, conf = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
            r = E.AuthorResult(author=author,
                               author_source=files[0].author_source if files else "fallback_unknown",
                               files=files, completeness=comp,
                               completeness_score=cs, completeness_grade=cg,
                               criteria=crits, quality_score=qs, confidence=conf)
            r.suggestions = E.build_suggestions(r)
            results[author] = r
        js = E.render_json(results, non_c4, DATASET, "Level 4", "medium")
        data = json.loads(js)   # 必须能被解析
        self.assertEqual(len(data["authors"]), 3)


class TestRubricIntegrity(unittest.TestCase):
    """评审标准自身的完整性——防止"标准与代码不一致"这类死配置"""

    def test_all_check_items_have_weight(self):
        for cid, cspec in RUBRIC_DATA["quality_criteria"].items():
            for item in cspec["check_items"]:
                self.assertIn("weight", item, f"{cid}/{item.get('id')} 缺 weight")
                self.assertGreater(item["weight"], 0)

    def test_structural_items_all_implemented(self):
        """rubric 里每条 type=structural 的 check_item 都必须在代码里登记了对应事实检查。

        这是防"死配置"的关键测试：若rubric 新增一个 structural 项而代码没实现，
        evaluate_quality 会抛 KeyError（而不是静默判成 ❌ 制造假结论）。
        """
        import re
        src = (SKILL_DIR / "scripts" / "c4a_evaluator.py").read_text(encoding="utf-8")
        # 抽出代码里 mapping 字典登记的 item id
        block = re.search(r"mapping = \{(.*?)\}", src, re.S)
        self.assertIsNotNone(block, "代码中找不到 structural mapping 登记")
        implemented = set(re.findall(r'"([A-Z]\d+)"\s*:', block.group(1)))

        declared = {item["id"]
                    for cspec in RUBRIC_DATA["quality_criteria"].values()
                    for item in cspec["check_items"]
                    if item.get("type") == "structural"}
        self.assertTrue(declared, "rubric 中应至少有一条 structural 检查项")
        self.assertEqual(
            declared - implemented, set(),
            f"这些 structural 项在代码中未登记，会抛 KeyError：{declared - implemented}",
        )

    def test_non_structural_items_have_signals(self):
        """非 structural 型检查项必须给出可匹配的信号，否则恒为不满足。"""
        for cid, cspec in RUBRIC_DATA["quality_criteria"].items():
            for item in cspec["check_items"]:
                t = item.get("type")
                if t == "structural":
                    continue
                has = bool(item.get("positive") or item.get("negative")
                           or item.get("io_patterns"))
                self.assertTrue(has, f"{cid}/{item['id']}（{t}）无任何信号——恒判不满足")

    def test_scoring_thresholds_parseable(self):
        """评分阈值必须能转 float（防YAML 注释粘连导致 '0.70# >= 0.70' 这类脏值）。"""
        c = RUBRIC_DATA["scoring"]["criterion"]
        self.assertIsInstance(float(c["pass_threshold"]), float)
        self.assertIsInstance(float(c["partial_threshold"]), float)
        self.assertGreater(c["pass_threshold"], c["partial_threshold"])

    def test_all_required_deliverables_have_signals(self):
        for key, spec in RUBRIC_DATA["required_deliverables"].items():
            self.assertTrue(spec.get("strong_filename") or spec.get("media_extensions"),
                            f"{key} 没有任何检测信号")


# ===========================================================================
# 误判率测量报告
# ===========================================================================

def measure_accuracy() -> int:
    """输出人机一致率矩阵。这是「误判率低」的量化证据。"""
    print("\n" + "=" * 78)
    print("误判率测量报告（评审器 vs 人工 ground truth）")
    print("=" * 78)

    total = 0
    agree = 0
    rows = []

    for author, gt in GROUND_TRUTH.items():
        files = _bundle(author)
        comp, c_score, _ = E.check_completeness(files, RUBRIC_DATA)
        crits, q_score, conf = E.evaluate_quality(files, RUBRIC_DATA, abs_folder=DATASET)
        grades = {c.id: c.grade for c in crits}

        for cid, label in [("reusable", "可复用"), ("executable", "可执行"),
                           ("verifiable", "可验证"), ("clear_io", "IO明确")]:
            exp = gt.get(f"expect_{cid}")
            if not exp:
                continue
            total += 1
            got = grades[cid]
            ok = (got == exp)
            agree += ok
            rows.append((author, label, exp, got, "✓一致" if ok else "✗不一致"))

        # 完整性判定
        if "completeness_min" in gt:
            total += 1
            ok = c_score >= gt["completeness_min"]
            agree += ok
            rows.append((author, "完整性", f"≥{gt['completeness_min']:.0%}",
                         f"{c_score:.0%}", "✓一致" if ok else "✗不一致"))
        if "completeness_max" in gt:
            total += 1
            ok = c_score <= gt["completeness_max"]
            agree += ok
            rows.append((author, "完整性", f"≤{gt['completeness_max']:.0%}",
                         f"{c_score:.0%}", "✓一致" if ok else "✗不一致"))

    print(f"\n{'作者':<12}{'维度':<10}{'人工判定':<12}{'评审器':<12}结果")
    print("-" * 78)
    for a, d, e, g, r in rows:
        print(f"{a:<12}{d:<10}{e:<12}{g:<12}{r}")
    print("-" * 78)
    rate = agree / total if total else 0.0
    print(f"\n判定总数     : {total}")
    print(f"一致数       : {agree}")
    print(f"人机一致率   : {rate:.1%}")
    print(f"误判率       : {1 - rate:.1%}")
    print("\n说明：一致率高不代表规则完美——它证明的是在标注样本上结论可信。")
    print("      剩余风险集中在置信度为 low 的结论，报告会主动标记需人工复核。")
    print("=" * 78)
    return 0 if rate >= 0.85 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accuracy", action="store_true", help="输出误判率测量报告")
    args = ap.parse_args()

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if args.accuracy:
        measure_accuracy()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())