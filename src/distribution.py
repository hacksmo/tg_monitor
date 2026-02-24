"""
分发矩阵：根据来源配置，用对应 Bot 将消息转发到目标群组，并可选 Bark。
"""
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

from .bark_notifier import push_bark
from .config_loader import get_bark_key, get_bot_token


# Telegram 单条消息最大长度
TELEGRAM_MAX_LENGTH = 4096


async def dispatch(
    bot_clients: dict[str, "TelegramClient"],
    source: dict,
    title: str,
    text: str,
    use_bark: bool = True,
) -> None:
    """
    将一条消息按 source 配置分发：用 source["bot_token_env_key"] 对应的 Bot
    发送到 source["target_chat_ids"]；若 source["bark_on_message"] 且 use_bark，则发 Bark。
    bot_clients: key 为 bot_token_env_key（如 BOT_1_TOKEN），value 为已 start 的 TelegramClient。
    """
    bark_key = get_bark_key() if use_bark else None
    if source.get("bark_on_message") and bark_key and title and text:
        await push_bark(bark_key, title, text)

    token_key = source.get("bot_token_env_key")
    if not token_key:
        return
    bot = bot_clients.get(token_key)
    if not bot:
        return
    target_ids = source.get("target_chat_ids") or []
    if not target_ids:
        return

    # 分块发送长消息
    if len(text) > TELEGRAM_MAX_LENGTH:
        chunks = []
        buf = ""
        for line in text.split("\n"):
            if len(buf) + len(line) + 1 > TELEGRAM_MAX_LENGTH:
                if buf:
                    chunks.append(buf)
                buf = line + "\n"
            else:
                buf += line + "\n"
        if buf:
            chunks.append(buf)
    else:
        chunks = [text]

    for chat_id in target_ids:
        try:
            for i, chunk in enumerate(chunks):
                prefix = f"📩 ({i+1}/{len(chunks)})\n\n" if len(chunks) > 1 else ""
                await bot.send_message(int(chat_id), prefix + chunk, parse_mode="md")
                if i < len(chunks) - 1:
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"[分发] 发送到 {chat_id} 失败: {e}")
