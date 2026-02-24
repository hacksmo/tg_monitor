"""
15 分钟异动投资简报：拉取 NVDA/SPY 15m K 线，计算 RSI，超买/超卖时结合最近大佬言论用 Gemini 生成简报并发送到指定群组。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd

from . import gemini_service
from .config_loader import get_bot_token
from .mapping_loader import get_brief_config, load_mapping


# 简报用标的（可配置扩展）
BRIEF_SYMBOLS = ["NVDA.US", "SPY.US"]


def _get_quote_context():
    """获取 Longbridge QuoteContext 与 Period。"""
    try:
        from longbridge.openapi import QuoteContext, Config, Period, AdjustType
        ctx = QuoteContext(Config.from_env())
        return ctx, Period, AdjustType
    except ImportError:
        # 未安装 longbridge SDK 时，直接返回空，让上层跳过简报逻辑
        return None, None, None


def _fetch_15m_candles(symbol: str, count: int = 100) -> list[dict] | None:
    """拉取 15 分钟 K 线，返回 [{"close": float, "timestamp": int}, ...]。"""
    ret = _get_quote_context()
    if ret[0] is None:
        return None
    ctx, Period, AdjustType = ret
    try:
        # Period.Minute15 或 Min_15 视 SDK 版本而定；最后 fallback 为 15
        period = getattr(Period, "Minute15", None) or getattr(Period, "Min_15", None) or 15

        # 为避免 offset 接口的 time 参数类型差异，这里改用按日期区间拉取最近几天数据
        end_d = date.today()
        start_d = end_d - timedelta(days=3)
        resp = ctx.history_candlesticks_by_date(
            symbol,
            period,
            AdjustType.NoAdjust,
            start_d,
            end_d,
        )
        if not resp or not getattr(resp, "candlesticks", None):
            return None
        cands = list(resp.candlesticks)
        if len(cands) > count:
            cands = cands[-count:]

        out = []
        for c in cands:
            out.append({
                "close": float(getattr(c, "close", 0) or 0),
                "open": float(getattr(c, "open", 0) or 0),
                "high": float(getattr(c, "high", 0) or 0),
                "low": float(getattr(c, "low", 0) or 0),
                "timestamp": getattr(c, "timestamp", 0),
            })
        return out
    except Exception as e:
        print(f"[简报] 拉取 {symbol} K 线失败: {e}")
        return None


def _compute_rsi(series: pd.Series, length: int = 14) -> float | None:
    """用 pandas 计算 RSI（与 pandas_ta 逻辑一致），返回最后一根 K 线的 RSI。"""
    try:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / length, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / length, adjust=False).mean()
        # 避免除零：无亏损时 RSI 视为 100
        avg_loss_safe = avg_loss.replace(0, 1e-10)
        rs = avg_gain / avg_loss_safe
        rsi = 100.0 - (100.0 / (1.0 + rs))
        if rsi.empty or pd.isna(rsi.iloc[-1]):
            return None
        return float(rsi.iloc[-1])
    except Exception as e:
        print(f"[简报] RSI 计算失败: {e}")
        return None


async def run_brief_once(
    user_client: Any,
    bot_clients: dict[str, Any],
    api_key: str,
    proxy: dict | None,
    recent_alpha_messages: list[dict] | None = None,
    mapping: dict[str, Any] | None = None,
) -> bool:
    """
    执行一次 15min 简报逻辑：拉取 NVDA/SPY 15m，算 RSI，若超买或超卖则生成简报并发送到配置的目标群组。
    recent_alpha_messages: 最近大佬言论；若为 None 则从 user_client 按 mapping 拉取最近 2 天。
    返回是否发送了简报。
    """
    import os
    from .mapping_loader import get_sources, get_alpha_usernames, get_summary_days_back
    from .telegram_fetch import fetch_messages

    m = mapping or load_mapping()
    brief_cfg = get_brief_config(m)
    overbought = brief_cfg["brief_rsi_overbought"]
    oversold = brief_cfg["brief_rsi_oversold"]

    # 若无传入则拉取大佬言论
    if recent_alpha_messages is None:
        alpha_list = get_alpha_usernames(m)
        sources = get_sources(m)
        days = get_summary_days_back(m)
        recent_alpha_messages = []
        for s in sources:
            msgs = await fetch_messages(
                user_client,
                s.get("group_id"),
                s.get("topic_id"),
                alpha_list or s.get("usernames") or [],
                days,
            )
            recent_alpha_messages.extend(msgs)
        recent_alpha_messages.sort(key=lambda x: x.get("时间", ""))

    alpha_texts = [msg.get("内容", "")[:300] for msg in recent_alpha_messages[-50:]]
    triggered = []

    for symbol in BRIEF_SYMBOLS:
        candles = _fetch_15m_candles(symbol, 80)
        if not candles:
            continue
        df = pd.DataFrame(candles)
        close = df["close"]
        rsi = _compute_rsi(close, 14)
        if rsi is None:
            continue
        if rsi >= overbought:
            triggered.append(f"{symbol} RSI 超买({rsi:.1f})")
        elif rsi <= oversold:
            triggered.append(f"{symbol} RSI 超卖({rsi:.1f})")

    if not triggered:
        print("[简报] RSI 未触发，本次不生成简报")
        return False

    rsi_status = "; ".join(triggered)
    print(f"[简报] 触发: {rsi_status}")
    brief = await gemini_service.generate_brief_15min(alpha_texts, rsi_status, api_key, proxy)
    if not brief:
        return False

    # 发送到固定群组 Topic：默认群 -1003863583323 的 Topic 2，可用环境变量覆盖
    chat_id = int(os.getenv("SUMMARY_CHAT_ID", "-1003863583323"))
    topic_id = int(os.getenv("BRIEF_TOPIC_ID", "2"))

    if bot_clients:
        for token_key, bot in bot_clients.items():
            token = get_bot_token(token_key)
            if not token:
                continue
            try:
                await bot.send_message(chat_id, brief, reply_to=topic_id, parse_mode="md")
                print(f"[简报] 已发送到群组 {chat_id} 的 Topic {topic_id}")
                return True
            except Exception as e:
                print(f"[简报] 发送失败: {e}")
    return True
