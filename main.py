#!/usr/bin/env python3
"""
Telegram 智能情报系统 - 异步主入口。
多源监听、多 Bot 分发、12h Gemini 复盘、Longbridge 监控、15min 简报，各模块不互相阻塞。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# 确保项目根在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config_loader import (
    load_env,
    get_proxy,
    get_telegram_credentials,
    get_gemini_api_key,
    get_obsidian_vault,
    get_bot_token,
)
from src.mapping_loader import load_mapping, get_sources, get_stocks_config
from src.telegram_listener import run_listener
from src.tasks import schedule_summary_every_12h, run_summary_job
from src.longbridge_monitor import _run_quote_subscribe
from src.investment_brief import run_brief_once


class _TelethonNoiseFilter(logging.Filter):
    """过滤 Telethon 中已知的无害警告日志。"""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        msg = record.getMessage()
        if msg.startswith("Server closed the connection: 0 bytes read on a total of 8 expected bytes"):
            # Telegram 服务端主动断开连接的正常行为，不需要在控制台刷屏
            return False
        return True


async def _create_bot_clients(api_id: int, api_hash: str, proxy: dict | None) -> dict:
    """根据 mapping 中出现的 bot_token_env_key 创建已连接的 Bot Client 字典。"""
    from telethon import TelegramClient

    mapping = load_mapping()
    sources = get_sources(mapping)
    keys = set()
    for s in sources:
        k = s.get("bot_token_env_key")
        if k:
            keys.add(k)
    bots = {}
    for i, key in enumerate(keys):
        token = get_bot_token(key)
        if not token:
            continue
        session_name = f".secrets/bot_{i}" if os.path.isdir(".secrets") else f"bot_{i}"
        client = TelegramClient(session_name, api_id, api_hash, proxy=proxy)
        await client.start(bot_token=token)
        bots[key] = client
        print(f"[Bot] 已启动: {key}")
    return bots


async def _brief_loop(user_client, bot_clients, api_key, proxy, interval_minutes: int = 15):
    """每 interval_minutes 分钟执行一次简报检查（仅 RSI 触发时发送）。"""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await run_brief_once(user_client, bot_clients, api_key, proxy, recent_alpha_messages=None)
        except Exception as e:
            print(f"[简报] 本轮异常: {e}")


async def main():
    # 1. 加载配置
    load_env(required_keys=["API_ID", "API_HASH", "GEMINI_API_KEY"])
    # 2. 配置 Telethon 日志：过滤已知无害的“Server closed the connection”警告
    telethon_logger = logging.getLogger("telethon")
    telethon_logger.addFilter(_TelethonNoiseFilter())
    telethon_logger.setLevel(logging.ERROR)

    api_id, api_hash = get_telegram_credentials()
    api_key = get_gemini_api_key()
    proxy = get_proxy()
    vault = get_obsidian_vault()
    mapping = load_mapping()
    sources = get_sources(mapping)

    # 2. 用户端（监听）
    session_path = ".secrets/market_monitor" if os.path.isdir(".secrets") else "market_monitor"
    user_client = __import__("telethon").TelegramClient(
        session_path, api_id, api_hash, proxy=proxy
    )
    await user_client.start()
    if not await user_client.is_user_authorized():
        print("登录失败，请检查 session 或重新登录。")
        return
    print("[主程序] 用户端已连接")

    # 3. Bot 客户端（分发）
    bot_clients = await _create_bot_clients(api_id, api_hash, proxy)

    # 4. 多源监听 + 分发（注册 handler 后由 run_until_disconnected 保持连接）
    async def run_listener_forever():
        await run_listener(user_client, bot_clients, sources)
        await user_client.run_until_disconnected()

    listener_task = asyncio.create_task(run_listener_forever())

    # 5. 12h 复盘任务
    summary_task = schedule_summary_every_12h(user_client, api_key, proxy, mapping, vault)

    # 6. Longbridge 行情监控（在线程中运行，不阻塞）
    stocks = get_stocks_config(mapping)
    print(f"SUCCESS: 成功加载了 {len(stocks)} 只股票: {[s['symbol'] for s in stocks]}")
    lb_task = None
    if stocks and os.getenv("LONGBRIDGE_APP_KEY") or os.getenv("LONGPORT_APP_KEY"):
        try:
            from src.config_loader import get_bark_key
            lb_task = asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _run_quote_subscribe(stocks, get_bark_key()),
            )
            print("[主程序] Longbridge 监控已启动（后台线程）")
        except Exception as e:
            print(f"[主程序] Longbridge 启动失败: {e}")

    # 7. 15min 简报循环（每 15 分钟检查 RSI，触发则发简报）
    brief_task = asyncio.create_task(_brief_loop(user_client, bot_clients, api_key, proxy, 15))

    print("[主程序] 所有任务已挂载，运行中...")
    try:
        await asyncio.gather(listener_task, summary_task, brief_task)
    except asyncio.CancelledError:
        pass
    finally:
        if lb_task and not lb_task.done():
            lb_task.cancel()
        summary_task.cancel()
        brief_task.cancel()
        await user_client.disconnect()
        for b in bot_clients.values():
            await b.disconnect()
        print("[主程序] 已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已手动停止")
