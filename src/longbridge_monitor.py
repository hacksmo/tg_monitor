"""
Longbridge 行情监控：订阅股票清单，价格突破/跌破阈值时 Bark 推送。
使用 longbridge/openapi（或 longport/openapi），在独立线程或 run_in_executor 中运行以避免阻塞。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from .bark_notifier import push_bark_sync
from .config_loader import get_bark_key


def _get_config_from_env() -> Any:
    """从环境变量构建 Longbridge Config。"""
    try:
        from longbridge.openapi import Config
    except ImportError:
        try:
            from longport.openapi import Config
        except ImportError:
            return None
    return Config


def _run_quote_subscribe(stocks: list[dict], bark_key: str | None) -> None:
    """
    同步运行：订阅行情，在回调里判断突破/跌破并 Bark。
    stocks: [{"symbol": "NVDA.US", "high": 150, "low": 100}, ...]
    """
    ConfigClass = _get_config_from_env()
    if ConfigClass is None:
        print("[Longbridge] 未安装 longbridge 或 longport，跳过行情监控")
        return
    try:
        from longbridge.openapi import QuoteContext, SubType
    except ImportError:
        try:
            from longport.openapi import QuoteContext, SubType
        except ImportError:
            print("[Longbridge] 无法导入 QuoteContext")
            return

    config = ConfigClass.from_env()
    # 检查必要环境变量
    if not os.getenv("LONGBRIDGE_APP_KEY") and not os.getenv("LONGPORT_APP_KEY"):
        print("[Longbridge] 未配置 LONGBRIDGE_APP_KEY / LONGPORT_APP_KEY，跳过")
        return

    symbols = [s["symbol"] for s in stocks]
    thresholds = {s["symbol"]: (float(s.get("high", 1e9)), float(s.get("low", -1e9))) for s in stocks}

    last_alert: dict[str, str] = {}  # symbol -> "high"|"low" 避免重复轰炸

    def on_quote(symbol: str, event: Any):
        try:
            last_price = getattr(event, "last_done", None) or getattr(event, "last_price", None)
            if last_price is None:
                return
            try:
                p = float(last_price)
            except (TypeError, ValueError):
                return
            high_t, low_t = thresholds.get(symbol, (1e9, -1e9))
            key = f"{symbol}_{last_alert.get(symbol, '')}"
            if p >= high_t:
                if last_alert.get(symbol) != "high":
                    last_alert[symbol] = "high"
                    if bark_key:
                        push_bark_sync(bark_key, f"突破 {symbol}", f"价格 {p} >= 阈值 {high_t}")
            elif p <= low_t:
                if last_alert.get(symbol) != "low":
                    last_alert[symbol] = "low"
                    if bark_key:
                        push_bark_sync(bark_key, f"跌破 {symbol}", f"价格 {p} <= 阈值 {low_t}")
            else:
                last_alert[symbol] = ""
        except Exception as e:
            print(f"[Longbridge] 回调异常: {e}")

    ctx = QuoteContext(config)
    ctx.set_on_quote(on_quote)
    ctx.subscribe(symbols, [SubType.Quote])
    print(f"[Longbridge] 已订阅: {symbols}")
    # 阻塞直到进程结束（主程序用 run_in_executor 调用则不会阻塞事件循环）
    import time
    while True:
        time.sleep(60)


async def run_longbridge_loop(
    stocks: list[dict],
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Task:
    """
    在 executor 中运行 _run_quote_subscribe，避免阻塞。返回 Task（可 cancel）。
    """
    bark_key = get_bark_key()

    def run():
        _run_quote_subscribe(stocks, bark_key)

    # 使用 run_in_executor 在线程池中运行同步的 subscribe 循环
    # 注意：_run_quote_subscribe 内部是 while True sleep，所以会一直占一个线程
    task = asyncio.create_task(asyncio.to_thread(run))
    return task
