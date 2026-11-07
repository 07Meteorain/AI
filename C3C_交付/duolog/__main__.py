"""``python -m duolog`` 的执行入口。

为什么单独一个 ``__main__.py``：让这个包既能被导入（``from duolog.cli import main``），
又能直接执行（``python -m duolog merge ...``）。两者共用同一个 ``main``，
保证命令行行为与测试里调用的行为不会分叉。
"""

from __future__ import annotations

import sys

from duolog.cli import main

if __name__ == "__main__":
    sys.exit(main())
