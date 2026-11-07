"""`analyze.profile` 对 `skill_owner` 空白名的回归测试。

为什么单独一个文件：这是跨模块边界（CLI strip、库调用不一定 strip）的
问题，放在 explain 的测试里会让人误以为是渲染问题。这里只钉住一件事：
`profile()` 自己必须把归属表规范化，不能把 `" Aster "` 和 `"Aster"`
当成两个人。
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from duolog.analyze import profile  # noqa: E402
from duolog.merge import merge  # noqa: E402
from duolog.model import Entry  # noqa: E402


def _entry(eid, author, text, tags=()):
    return Entry(eid=eid, author=author, clock=1, tags=tuple(tags), text=text, line=1)


def _items():
    """Aster 是 SEL-1 的拥有者，Bramble 在自己的条目里也用了 SEL-1。"""
    entries = [
        _entry("E-100", "Aster", "拥有者自己的条目", ("技能:SEL-1",)),
        _entry("E-101", "Bramble", "使用者的条目", ("技能:SEL-1",)),
    ]
    return merge(entries).items


class SkillOwnerStripTest(unittest.TestCase):
    """归属名带空白不能变成伪迁移或幽灵作者。"""

    def test_padded_owner_does_not_create_self_transfer(self):
        prof = profile(_items(), {"SEL-1": " Aster "})
        self.assertEqual(prof.authors, ("Aster", "Bramble"))
        self.assertEqual(len(prof.transfers), 1)
        edge = prof.transfers[0]
        self.assertEqual((edge.src, edge.dst, edge.skill), ("Aster", "Bramble", "SEL-1"))
        self.assertNotIn(" Aster ", prof.share)
        self.assertNotIn(" Aster ", prof.skill_tags)
        self.assertAlmostEqual(sum(prof.share.values()), 1.0, places=4)

    def test_padded_owner_is_not_a_phantom_author(self):
        # 只有 Aster 写过日志、且 Aster 是 SEL-1 拥有者：不应出现自迁移边，
        # 也不应因为 " Aster " 多出一个 0% 的作者。
        entries = [_entry("E-102", "Aster", "只有我", ("技能:SEL-1",))]
        prof = profile(merge(entries).items, {"SEL-1": " Aster "})
        self.assertEqual(prof.authors, ("Aster",))
        self.assertEqual(prof.transfers, ())
        self.assertEqual(prof.share, {"Aster": 1.0})
        self.assertEqual(prof.skill_tags["Aster"], {"SEL-1": 1})

    def test_padded_skill_key_is_normalized_too(self):
        prof = profile(_items(), {" SEL-1 ": " Aster "})
        self.assertEqual(len(prof.transfers), 1)
        self.assertEqual(prof.transfers[0].src, "Aster")

    def test_blank_owner_means_unconfigured(self):
        prof = profile(_items(), {"SEL-1": "   "})
        self.assertEqual(prof.authors, ("Aster", "Bramble"))
        self.assertEqual(prof.transfers, ())
        self.assertEqual(set(prof.share), {"Aster", "Bramble"})
        # 没有拥有者只影响迁移判定；条目自带的技能标签仍按人计数。
        self.assertEqual(prof.skill_tags["Aster"], {"SEL-1": 1})
        self.assertEqual(prof.skill_tags["Bramble"], {"SEL-1": 1})


if __name__ == "__main__":
    unittest.main()
