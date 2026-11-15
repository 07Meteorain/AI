"""mapping.py：编号前缀、别名、歧义、孤立目录。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from submitgate import mapping as mp
from submitgate.challenge import load_challenge

from util import make_record, write_course, write_files


def _challenges(root: Path, ids: list[str]):
    records = {sid: make_record(sid) for sid in ids}
    course = write_course(root / "course", records)
    return [load_challenge(course / sid / "challenge.json") for sid in ids]


class FolderIdTest(unittest.TestCase):
    def test_prefix_does_not_confuse_c3_and_c3c(self):
        self.assertEqual(mp.folder_id("C3_交付"), "C3")
        self.assertEqual(mp.folder_id("C3C_交付"), "C3C")
        self.assertEqual(mp.folder_id("C2A_C9_交付"), "C2A")
        self.assertEqual(mp.folder_id("C4B_公众号文章生成技能"), "C4B")
        self.assertEqual(mp.folder_id("C10H_安装记录"), "C10H")
        self.assertIsNone(mp.folder_id("其他目录"))


class BuildMappingTest(unittest.TestCase):
    def test_exact_and_alias_and_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            challenges = _challenges(root, ["C3", "C3C", "C9"])
            repo = root / "repo"
            write_files(repo / "C3_交付", {"a.md": "x"})
            write_files(repo / "C3C_交付", {"a.md": "x"})
            write_files(repo / "C2A_C9_交付", {"a.md": "x"})
            write_files(repo / "C4A_交付", {"a.md": "x"})
            mapping = mp.build_mapping(challenges, repo, {"C9": "C2A_C9_交付"})
        self.assertEqual(mapping.get("C3").name, "C3_交付")
        self.assertEqual(mapping.get("C3C").name, "C3C_交付")
        self.assertEqual(mapping.get("C9").name, "C2A_C9_交付")
        self.assertIn("C9 按 mapping.json 声明映射到 C2A_C9_交付/", mapping.notes)
        self.assertEqual([p.name for p in mapping.orphans], ["C4A_交付"])

    def test_missing_alias_target_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            challenges = _challenges(root, ["C9"])
            repo = root / "repo"
            repo.mkdir()
            mapping = mp.build_mapping(challenges, repo, {"C9": "C2A_C9_交付"})
        self.assertIsNone(mapping.get("C9"))
        self.assertTrue(any("不存在" in note for note in mapping.notes))

    def test_ambiguity_picks_first_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            challenges = _challenges(root, ["C5"])
            repo = root / "repo"
            write_files(repo / "C5_交付", {"a.md": "x"})
            write_files(repo / "C5_副本", {"a.md": "x"})
            mapping = mp.build_mapping(challenges, repo)
        self.assertIn("C5", mapping.ambiguous)
        self.assertTrue(any("命中多个目录" in note for note in mapping.notes))

    def test_no_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            challenges = _challenges(root, ["C7"])
            repo = root / "repo"
            repo.mkdir()
            mapping = mp.build_mapping(challenges, repo)
        self.assertIsNone(mapping.get("C7"))


class AliasFileTest(unittest.TestCase):
    def test_load_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mapping.json"
            path.write_text(json.dumps({"aliases": {"c9": "C2A_C9_交付"}}), encoding="utf-8")
            aliases = mp.load_aliases(path)
        self.assertEqual(aliases, {"C9": "C2A_C9_交付"})

    def test_missing_file_is_empty(self):
        self.assertEqual(mp.load_aliases(Path("does-not-exist.json")), {})
        self.assertEqual(mp.load_aliases(None), {})


if __name__ == "__main__":
    unittest.main()
