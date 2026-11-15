"""brain —— 一个可运行、可检索、会长大的「第二大脑」智能体。

五层架构（自下而上）：

    L1 接口层 interface/   人怎么跟它说话（CLI / REPL / 回执）
    L2 工具层 tools/       它能对外部世界做什么（带权限、超时、熔断）
    L3 循环层 loop/        它怎么一次一次把事情做完（规划→执行→观察→反思）
    L4 技能层 skills/      它把重复动作固化成了什么（SKILL.md + handler）
    L5 记忆层 memory/      它记得什么、记得多牢、怎么找回来（KSTAR 四层）

设计约束（写进代码，而不是写进 PPT）：

* 零第三方依赖：只用 Python 标准库，``git clone`` 后 ``python -m brain doctor``
  就能验证，不需要 pip install。
* 默认离线可跑：没有 API key 时用规则规划器，有 key 时同一套循环换成 LLM 规划器。
* 一切可追溯：每次运行落一条 trace，每条记忆有来源 ``source``。
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
