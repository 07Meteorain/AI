#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会议纪要摘要（原型）"""

import sys
from pathlib import Path

# TODO: 接入大模型 API
MODEL_PATH = "C:\\Users\\lm\\meeting\\model.bin"


def summarize(text: str) -> str:
    """把会议文本截断为摘要（原型实现）。"""
    return text[:500]


def main() -> int:
    #硬编码路径，尚未参数化
    p = Path("C:/Users/lm/Desktop/meeting_notes.txt")
    if not p.exists():
        print("找不到文件")
        return 1
    print(summarize(p.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())