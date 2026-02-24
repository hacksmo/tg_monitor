"""
从 Telegram 拉取历史消息，供定时复盘与简报使用。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from telethon import TelegramClient


async def fetch_messages(
    client: TelegramClient,
    group_id: int,
    topic_id: int | None,
    usernames: list[str],
    days_back: int,
) -> list[dict]:
    """
    拉取指定群组/话题内最近 days_back 天的消息。若 usernames 非空则只保留这些用户的发言。
    返回与 stock_monitor 一致的结构：时间、发言人ID、昵称、内容。
    """
    cutoff = datetime.now().replace(tzinfo=None) - timedelta(days=days_back)
    out = []
    try:
        async for message in client.iter_messages(
            group_id,
            limit=None,
            reply_to=topic_id,
        ):
            if message.date.replace(tzinfo=None) < cutoff:
                break
            sender = await message.get_sender()
            username = getattr(sender, "username", None)
            if usernames and username not in usernames:
                continue
            out.append({
                "时间": message.date.strftime("%Y-%m-%d %H:%M:%S"),
                "发言人ID": f"@{username}" if username else "无ID",
                "昵称": f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip(),
                "内容": message.text or "",
            })
    except Exception as e:
        print(f"[拉取] {group_id} topic={topic_id} 失败: {e}")
    return out
