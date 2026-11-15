"""模型适配层（可选）。默认离线，不配置任何 key 也能完整运行。"""

from .provider import (
    ANSWER_PROMPT,
    SYSTEM_PROMPT,
    BaseProvider,
    LLMPlanner,
    OfflineProvider,
    OpenAICompatProvider,
    ProviderInfo,
    build_provider,
    tool_help,
)

__all__ = [
    "BaseProvider",
    "OfflineProvider",
    "OpenAICompatProvider",
    "LLMPlanner",
    "ProviderInfo",
    "build_provider",
    "tool_help",
    "SYSTEM_PROMPT",
    "ANSWER_PROMPT",
]
