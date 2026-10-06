#!/usr/bin/env python3
"""C4D 命令行入口：本地大模型 Agent 的一站式运行脚本。

用法
----
    python -m sias_local_agent.cli doctor              # 环境自检
    python -m sias_local_agent.cli run --task map      # 生成地图
    python -m sias_local_agent.cli run --task plan     # 规划行程
    python -m sias_local_agent.cli run --task chat     # 自由问答
    python -m sias_local_agent.cli chat                # 多轮对话模式
    python -m sias_local_agent.cli memory              # 查看记忆
    python -m sias_local_agent.cli bench               # 性能基准
    python -m sias_local_agent.cli compare             # 模型对比

所有子命令都会把完整日志写入 logs/ 目录，作为「模型输出日志」交付物。
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import LocalAgent
from .knowledge import KNOWLEDGE_BASE, SIAS_CENTER
from .llm import OllamaClient, OllamaError
from .map_view import build_map_html, normalize_locations, save_map
from .memory import MemoryStore

PKG_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PKG_ROOT / "logs"
OUT_DIR = PKG_ROOT / "output"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Tee:
    """同时输出到终端与日志文件。"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("a", encoding="utf-8")
        self.path = path

    def __call__(self, *args: Any) -> None:
        msg = " ".join(str(a) for a in args)
        print(msg)
        self.fh.write(f"[{_now()}] {msg}\n")
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def device_info() -> dict[str, Any]:
    """采集设备信息（挑战要求的四项证据之一）。"""
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
    try:
        import psutil  # type: ignore

        info["cpu_cores"] = psutil.cpu_count(logical=False)
        info["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor)[0].Name;"
                    "[math]::Round((Get-CimInstance Win32_ComputerSystem)"
                    ".TotalPhysicalMemory/1GB,1);"
                    "Get-CimInstance Win32_VideoController | "
                    "ForEach-Object { $_.Name }",
                ],
                capture_output=True, text=True, timeout=30,
            )
            lines = (out.stdout or "").strip().splitlines()
            if lines:
                info["cpu"] = lines[0].strip()
            if len(lines) > 1:
                info["ram_gb"] = float(lines[1].strip())
            if len(lines) > 2:
                info["gpu"] = [x.strip() for x in lines[2:] if x.strip()]
        except Exception:
            pass
    return info


def make_client(args: argparse.Namespace) -> OllamaClient:
    return OllamaClient(
        model=args.model,
        base_url=args.host,
        timeout=args.timeout,
        num_ctx=args.ctx,
        temperature=args.temperature,
    )


def make_memory(args: argparse.Namespace) -> MemoryStore:
    return MemoryStore(
        db_path=args.db, session_id=args.session
    )


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    """环境自检：本地模型是否可用。"""
    log = Tee(LOG_DIR / "doctor.log")
    dev = device_info()
    client = make_client(args)

    log("=" * 64)
    log("C4D 本地大模型 Agent —— 环境自检")
    log("=" * 64)
    log(f"时间: {_now()}")
    log("--- 设备信息 ---")
    for k, v in dev.items():
        log(f"  {k}: {v}")
    log("--- Ollama 服务 ---")
    log(f"  endpoint: {args.host}")

    if not client.is_available():
        log("  ✗ Ollama 服务不可用。请先运行 `ollama serve`，"
            "或重新安装 Ollama。")
        log.close()
        return 1

    models = client.list_models()
    log(f"  ✓ 服务可用，已安装模型: {', '.join(models) or '(空)'}")
    log(f"  当前使用: {args.model}")

    if args.model not in models:
        log(f"  ⚠ 警告：{args.model} 不在已安装列表，"
            f"运行时会自动尝试拉取。")

    log("--- 推理基准 ---")
    snap = client.health_snapshot()
    log(f"  模型: {snap['model']}")
    log(f"  tokens: {snap['tokens']}")
    log(f"  速度: {snap['tok_per_second']} tok/s")
    log(f"  耗时: {snap['total_ms']} ms")
    log(f"  输出: {snap['content'][:200]}")

    (LOG_DIR / "env_snapshot.json").write_text(
        json.dumps(
            {"device": dev, "models": models, "bench": snap,
             "checked_at": _now()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    log("✓ 自检通过")
    log.close()
    return 0


def _ensure_model_online(client: OllamaClient, log: Tee) -> bool:
    """首次使用时自动拉取模型（Ollama 会自动下载缺失模型）。"""
    if client.is_available() and client.model in client.list_models():
        return True
    log(f"模型 {client.model} 不在本地，尝试自动拉取（首次会下载数 GB）…")
    try:
        # 发一个极短请求触发 Ollama 的自动拉取
        client.chat([{"role": "user", "content": "hi"}])
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 模型拉取失败: {exc}")
        return False


def cmd_run(args: argparse.Namespace) -> int:
    """执行核心任务：地图生成 / 行程规划 / 自由问答。"""
    task = args.task
    name = f"{task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log = Tee(LOG_DIR / f"run_{task}.log")
    dev = device_info()
    client = make_client(args)
    mem = make_memory(args)

    log("=" * 64)
    log(f"C4D 本地 Agent 运行：{task}")
    log("=" * 64)
    log(f"时间: {_now()}")
    log(f"模型: {args.model}")
    log(f"端点: {args.host}  (本地推理，无云端 API)")
    log(f"设备: {dev.get('cpu', dev.get('processor'))} / "
        f"{dev.get('ram_gb')}GB RAM")
    log(f"会话: {args.session}  数据库: {args.db}")
    log(f"知识库条目: {len(KNOWLEDGE_BASE)}  基准中心: {SIAS_CENTER}")

    if not _ensure_model_online(client, log):
        log.close()
        return 1

    agent = LocalAgent(client, mem, max_steps=args.max_steps)
    t0 = time.time()

    if task == "map":
        log("-" * 64)
        log(f"任务: 让 Agent 生成 {args.count} 个地点的结构化数据")
        run = agent.generate_locations(count=args.count, focus=args.focus)
    elif task == "plan":
        log("-" * 64)
        log(f"任务: 规划 {args.count} 站行程（多工具调用 + 多步推理）")
        run = agent.plan_itinerary(site_count=args.count)
    else:
        log("-" * 64)
        log(f"任务: 自由问答 -> {args.question}")
        run = agent.chat(args.question or "请介绍一下西亚斯学院")

    log("-" * 64)
    log("推理轨迹:")
    for line in run.trace().splitlines():
        log("  " + line)
    log("-" * 64)
    log(f"结果: {run.summary()}")
    log(f"记忆: {mem.stats().summary()}")

    payload: dict[str, Any] = {
        "task": task,
        "model": args.model,
        "endpoint": args.host,
        "device": dev,
        "ok": run.ok,
        "error": run.error,
        "steps": [
            {
                "index": s.index, "kind": s.kind, "tool": s.tool_name,
                "args": s.args, "preview": s.result_preview[:300],
                "elapsed_s": s.elapsed_s,
                "tok_per_second": round(s.tok_per_second, 2),
                "tokens": s.tokens,
            }
            for s in run.steps
        ],
        "total_tokens": run.total_tokens,
        "total_seconds": run.total_seconds,
        "tool_calls": run.tool_calls,
        "tool_usage": agent.tool_usage(),
        "memory": mem.stats().summary(),
        "raw_final": run.final_text,
        "parsed": run.parsed,
        "generated_at": _now(),
    }

    if not run.ok:
        log(f"✗ 任务失败: {run.error}")
        (LOG_DIR / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.close()
        return 1

    # ---------- 地图任务：渲染 HTML ----------
    if task == "map":
        locs = normalize_locations(run.parsed)
        log(f"归一化后地点数: {len(locs)}")
        if not locs:
            log("✗ 未解析出有效地点，请查看日志中的模型原始输出")
            (LOG_DIR / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.close()
            return 1

        # 坐标合理性校验（多工具调用的本地校验环节）
        from .tools import tool_validate_coords

        bad = []
        for l in locs:
            chk = tool_validate_coords(l["lat"], l["lng"])
            if not chk["in_expected_region"]:
                bad.append((l["name_zh"], chk))
        log(f"坐标校验: {len(locs) - len(bad)}/{len(locs)} 位于合理区域")
        for nm, chk in bad:
            log(f"  ⚠ {nm}: {chk['verdict']}")

        avg_tps = (
            sum(s.tok_per_second for s in run.steps) / len(run.steps)
            if run.steps else 0
        )
        model_info = {
            "model": args.model,
            "runtime": f"Ollama @ {args.host}",
            "device": f"{dev.get('cpu', 'CPU')} / {dev.get('ram_gb')}GB / "
                      f"{', '.join(dev.get('gpu', []) or ['无独立GPU'])}",
            "tok_per_second": f"{avg_tps:.1f}",
            "tool_calls": run.tool_calls,
            "generated_at": _now(),
        }
        html_text = build_map_html(
            locs,
            subtitle=(
                f"由本地 {args.model} 通过 function calling + 结构化输出生成 "
                f"{len(locs)} 个地点；坐标取自随技能分发的本地知识库，"
                f"底图为腾讯地图（GCJ-02）。"
            ),
            model_info=model_info,
            run_info={
                "tool_calls": run.tool_calls,
                "total_tokens": run.total_tokens,
                "total_seconds": run.total_seconds,
                "trace": run.trace(),
            },
        )
        out = OUT_DIR / "sias_map.html"
        save_map(html_text, out)
        log(f"✓ 地图已生成: {out}")

        # 同步输出一份挑战清单命名的副本
        named = PKG_ROOT.parent / "姓名_C4D_map.html"
        save_map(html_text, named)
        log(f"✓ 地图副本: {named}")

        payload["locations"] = locs
        payload["map_html"] = str(out)
        payload["model_info"] = model_info
        (LOG_DIR / "locations.json").write_text(
            json.dumps(locs, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 行程任务：导出 JSON ----------
    if task == "plan":
        out = OUT_DIR / "itinerary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(run.parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"✓ 行程已保存: {out}")

    (LOG_DIR / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"完整日志: {LOG_DIR / f'{name}.json'}")
    log(f"总耗时: {time.time() - t0:.1f}s")
    log.close()
    mem.close()
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    """多轮交互对话：验证记忆确实生效。"""
    log = Tee(LOG_DIR / "chat.log")
    client = make_client(args)
    mem = make_memory(args)
    dev = device_info()

    log("=" * 64)
    log("C4D 多轮对话 Agent（验证记忆能力）")
    log("=" * 64)
    log(f"模型: {args.model}   设备 RAM: {dev.get('ram_gb')}GB")
    log(f"载入已有记忆: {mem.stats().summary()}")
    for f in mem.recall():
        log(f"  [长期记忆] {f['key']}: {f['value']}")

    if not _ensure_model_online(client, log):
        log.close()
        return 1

    agent = LocalAgent(client, mem, max_steps=args.max_steps)
    log("-" * 64)
    log("输入 quit 退出；输入 :remember k=v 手动写入长期记忆")
    log("-" * 64)

    transcript: list[dict[str, Any]] = []
    while True:
        try:
            user = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            log("\n(会话结束)")
            break
        if not user:
            continue
        if user.lower() in ("quit", "exit", "q"):
            break
        if user.startswith(":remember"):
            body = user[len(":remember"):].strip()
            if "=" in body:
                k, v = body.split("=", 1)
                mem.remember(k.strip(), v.strip())
                log(f"  ✓ 已记住: {k.strip()} = {v.strip()}")
            continue

        t0 = time.time()
        run = agent.chat(user)
        dt = time.time() - t0
        log(f"AI> {run.final_text[:900]}")
        log(f"  (tools={run.tool_calls} tokens={run.total_tokens} "
            f"{dt:.1f}s {mem.stats().summary()})")
        transcript.append(
            {"user": user, "agent": run.final_text,
             "tool_calls": run.tool_calls, "tokens": run.total_tokens,
             "seconds": round(dt, 2)}
        )

    (LOG_DIR / "chat_transcript.json").write_text(
        json.dumps(
            {"model": args.model, "device": dev,
             "turns": transcript, "memory": mem.stats().summary()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    log(f"✓ 对话记录: {LOG_DIR / 'chat_transcript.json'}")
    log.close()
    mem.close()
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    """查看 / 管理记忆库。"""
    mem = make_memory(args)
    st = mem.stats()
    print(f"会话 {args.session}: {st.summary()}")
    print("\n长期记忆:")
    for f in mem.recall():
        print(f"  - {f['key']} = {f['value']}  (conf={f['confidence']})")
    print("\n最近对话:")
    for t in mem.history(limit=10):
        role = t["role"]
        content = (t["content"] or "").replace("\n", " ")[:100]
        print(f"  [{role}] {content}")
    if args.clear:
        mem.clear()
        print("\n(已清空当前会话)")
    mem.close()
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """性能基准：多轮推理 tok/s。"""
    log = Tee(LOG_DIR / "bench.log")
    client = make_client(args)
    log("=" * 64)
    log("C4D 本地推理性能基准")
    log("=" * 64)
    dev = device_info()
    for k, v in dev.items():
        log(f"  {k}: {v}")
    log("-" * 64)

    if not client.is_available():
        log("✗ Ollama 服务不可用")
        log.close()
        return 1

    prompt = "请用大约200字介绍郑州西亚斯学院的办学特色。"
    results = []
    for i in range(args.rounds):
        t0 = time.time()
        resp = client.chat([{"role": "user", "content": prompt}])
        dt = time.time() - t0
        results.append(
            {
                "round": i + 1,
                "tokens": resp.eval_count,
                "tok_per_second": round(resp.tokens_per_second, 2),
                "wall_seconds": round(dt, 2),
                "model": resp.model,
            }
        )
        log(f"  第{i+1}轮: {resp.eval_count} tokens  "
            f"{resp.tokens_per_second:.2f} tok/s  {dt:.2f}s")

    if results:
        avg = sum(r["tok_per_second"] for r in results) / len(results)
        log("-" * 64)
        log(f"平均推理速度: {avg:.2f} tok/s")
        (LOG_DIR / "bench.json").write_text(
            json.dumps(
                {"model": args.model, "device": dev, "rounds": results,
                 "avg_tok_per_second": round(avg, 2), "at": _now()},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    log.close()
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """模型对比：同任务下不同尺寸 Gemma 4 的表现（Level 4 加分项）。"""
    log = Tee(LOG_DIR / "compare.log")
    log("=" * 64)
    log("C4D 模型对比（Agent 任务表现）")
    log("=" * 64)
    rows = []
    prompt = (
        "只输出 JSON：{\"locations\":[{\"name_zh\":\"...\",\"name_en\":\"...\","
        "\"description_zh\":\"...\",\"description_en\":\"...\","
        "\"latitude\":34.40,\"longitude\":113.73,\"category\":\"campus\"}]}。"
        "列出3个郑州西亚斯学院的地点，坐标用 34.40, 113.73 附近。"
    )
    for m in args.models:
        client = OllamaClient(model=m, base_url=args.host, timeout=args.timeout,
                              num_ctx=args.ctx)
        log("-" * 64)
        log(f"模型: {m}")
        if m not in client.list_models():
            log(f"  ⚠ 未安装，跳过（如需请先 `ollama pull {m}`）")
            continue
        # 关键：先卸载上一个模型，避免显存/内存不足导致加载失败
        # （实测：E2B 仍驻留时加载 E4B 报 unable to allocate CUDA_Host buffer）
        client.unload()
        time.sleep(2)
        try:
            t0 = time.time()
            data, resp = client.structured(
                [
                    {"role": "system", "content": "Always output valid JSON only."},
                    {"role": "user", "content": prompt},
                ]
            )
            dt = time.time() - t0
            locs = normalize_locations(data)
            row = {
                "model": m,
                "tokens": resp.eval_count,
                "tok_per_second": round(resp.tokens_per_second, 2),
                "wall_seconds": round(dt, 2),
                "json_ok": True,
                "parsed_locations": len(locs),
            }
            log(f"  ✓ JSON 合法, 解析出 {len(locs)} 个地点, "
                f"{row['tok_per_second']} tok/s")
        except Exception as exc:  # noqa: BLE001
            row = {"model": m, "json_ok": False, "error": str(exc)[:200]}
            log(f"  ✗ 失败: {str(exc)[:150]}")
        rows.append(row)

    (LOG_DIR / "model_compare.json").write_text(
        json.dumps({"results": rows, "at": _now()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("=" * 64)
    log(f"✓ 对比结果: {LOG_DIR / 'model_compare.json'}")
    log.close()
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sias_local_agent",
        description="C4D 本地大模型 Agent 技能（Gemma4 + Ollama，完全离线）",
    )
    p.add_argument("--model", default="gemma4:e4b", help="本地模型名")
    p.add_argument("--host", default="http://localhost:11434", help="Ollama 端点")
    p.add_argument("--db", default=str(PKG_ROOT / "data" / "memory.db"),
                   help="记忆数据库路径")
    p.add_argument("--session", default="default", help="会话 ID")
    p.add_argument("--ctx", type=int, default=8192, help="上下文长度")
    p.add_argument("--timeout", type=float, default=600.0, help="请求超时秒")
    p.add_argument("--temperature", type=float, default=0.3, help="采样温度")
    p.add_argument("--max-steps", type=int, default=6, help="Agent 最大推理步数")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境自检").set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="执行任务")
    r.add_argument("--task", choices=["map", "plan", "chat"], default="map")
    r.add_argument("--count", type=int, default=10, help="地点/站点数量")
    r.add_argument("--focus", default="校园与周边重要地点")
    r.add_argument("--question", default="")
    r.set_defaults(func=cmd_run)

    sub.add_parser("chat", help="多轮交互对话").set_defaults(func=cmd_chat)

    m = sub.add_parser("memory", help="查看记忆")
    m.add_argument("--clear", action="store_true")
    m.set_defaults(func=cmd_memory)

    b = sub.add_parser("bench", help="性能基准")
    b.add_argument("--rounds", type=int, default=3)
    b.set_defaults(func=cmd_bench)

    c = sub.add_parser("compare", help="模型对比")
    c.add_argument(
        "--models",
        nargs="+",
        default=["gemma4:e2b", "gemma4:e4b", "gemma4:12b"],
    )
    c.set_defaults(func=cmd_compare)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except OllamaError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())