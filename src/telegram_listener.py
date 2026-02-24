"""
多源 Telethon 监听：根据 mapping 的 sources 注册 NewMessage，按 topic_id 与 usernames 过滤后调用分发。
"""
from __future__ import annotations

from datetime import datetime
from telethon import TelegramClient, events

from .distribution import dispatch
from .mapping_loader import get_sources


def _in_topic(event, topic_id: int | None) -> bool:
    """判断消息是否属于指定 topic。"""
    if topic_id is None:
        return True
    reply_to = getattr(event.message, "reply_to", None)
    if not reply_to:
        return False
    top_id = getattr(reply_to, "reply_to_top_id", None)
    if top_id == topic_id:
        return True
    if getattr(reply_to, "reply_to_msg_id", None) == topic_id:
        return True
    return False


def _source_matches(source: dict, group_id: int, topic_id: int | None, username: str | None) -> bool:
    """同一 source 的 group_id/topic_id 需匹配；若配置了 usernames 则发言人需在名单内。"""
    if source.get("group_id") != group_id:
        return False
    src_topic = source.get("topic_id")
    if src_topic is not None and topic_id != src_topic:
        return False
    usernames = source.get("usernames") or []
    if usernames and username not in usernames:
        return False
    return True


async def run_listener(
    user_client: TelegramClient,
    bot_clients: dict[str, TelegramClient],
    sources: list[dict],
) -> None:
    """
    在 user_client 上注册多源监听，命中则调用 dispatch。
    sources 来自 get_sources(load_mapping())。
    """
    # 按 group_id 分组，避免重复注册同一群
    by_chat: dict[int, list[dict]] = {}
    for s in sources:
        gid = s.get("group_id")
        if gid is None:
            continue
        by_chat.setdefault(gid, []).append(s)

    if not by_chat:
        print("[监听] 未配置任何 source，跳过 NewMessage 注册")
        return

    chat_ids = list(by_chat.keys())

    @user_client.on(events.NewMessage(chats=chat_ids))
    async def handler(event):
        group_id = event.chat_id
        reply_to = getattr(event.message, "reply_to", None)
        topic_id = getattr(reply_to, "reply_to_top_id", None) if reply_to else None
        sender = await event.get_sender()
        username = getattr(sender, "username", None) or ""
        nickname = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
        text = event.message.text or ""

        for source in by_chat.get(group_id, []):
            if not _in_topic(event, source.get("topic_id")):
                continue
            if not _source_matches(source, group_id, topic_id, username):
                continue
            time_str = datetime.now().strftime("%H:%M:%S")
            print(f"[{time_str}] 命中来源 {source.get('key', group_id)} @{username}: {text[:30]}...")
            title = f"大佬【{nickname}】发言"
            await dispatch(bot_clients, source, title, text, use_bark=True)
            break  # 一个消息只匹配一个 source

    print(f"[监听] 已注册群组: {chat_ids}")
