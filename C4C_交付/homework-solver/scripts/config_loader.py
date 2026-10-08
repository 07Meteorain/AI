#!/usr/bin/env python3
"""
配置文件加载：学生信息、课程偏好、模型选择。

对应CHALLENGE.md Level 4 的「配置系统」要求。

用法：
    #命令行覆盖
    python scripts/pipeline.py hw.md out/ --student "张三"

    # 或在config/config.yaml 里写好，一劳永逸
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = {
    "student": "Meteorain",
    "course": "Mathematics",
    "title": "Homework Solutions",
    "date_format": "%Y-%m-%d",

    # 求解引擎
    "solver": {
        "provider": "qwen",          # qwen | kimi | deepseek | claude
        "model": None,               # null = 用 provider 的推荐模型
        "temperature": 0.1,          # 低温度：数学题要确定性
        "max_tokens": 2048,
        "timeout": 60,
        "use_llm": True,
        "verify": True,
    },

    # 渲染偏好
    "render": {
        "cjk": "auto",               # auto | always | never
        "show_verification": True,   # 在PDF 里显示验证徽章
        "figures": True,             # matplotlib 作图
    },

    # 验证阈值
    "verify": {
        "substitution_tol": 1e-9,
        "cross_check_rel_tol": 1e-4,
        "eigen_residual_tol": 1e-6,
        "ode_residual_tol": 1e-8,
    },
}

# 环境变量 → 配置项的映射（方便 CI / 密钥管理）
ENV_OVERRIDES = {
    "C4C_PROVIDER": ("solver", "provider"),
    "C4C_MODEL": ("solver", "model"),
    "C4C_TEMPERATURE": ("solver", "temperature"),
    "C4C_STUDENT": ("student",),
    "C4C_COURSE": ("course",),
    "C4C_NO_LLM": ("solver", "use_llm"),
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = None, apply_env: bool = True) -> dict:
    """
    按优先级加载配置：
      默认值< config.yaml < config.json < 环境变量 < 命令行参数
    """
    cfg = dict(DEFAULT_CONFIG)

    # 1) YAML
    y = Path(path) if path else CONFIG_DIR / "config.yaml"
    if y.exists():
        try:
            import yaml
            cfg = _deep_merge(cfg, yaml.safe_load(y.read_text(encoding="utf-8")) or {})
        except Exception as e:
            print(f"[config] YAML 读取失败（忽略）：{e}")

    # 2) JSON
    j = CONFIG_DIR / "config.json"
    if j.exists():
        try:
            cfg = _deep_merge(cfg, json.loads(j.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[config] JSON 读取失败（忽略）：{e}")

    # 3) 环境变量
    if apply_env:
        for env, keys in ENV_OVERRIDES.items():
            val = os.environ.get(env)
            if val is None:
                continue
            node = cfg
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = _coerce(val)

    return cfg


def _coerce(v: str):
    low = v.lower()
    if low in ("1", "true", "yes", "on"):
        return True
    if low in ("0", "false", "no", "off"):
        return False
    if low in ("none", "null", ""):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(load_config(), ensure_ascii=False, indent=2))