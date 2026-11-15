"""submitgate — 挑战交付验收门禁。

把「平台要求的必需交付物 + 评分维度 + 红旗项」翻译成一次可复跑的文件系统检查，
输出学生自查用的缺口清单、助教抽查用的验收报告、以及一个双击即开的导航站。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

__version__ = "2.1.0"
__all__ = ["__version__"]
