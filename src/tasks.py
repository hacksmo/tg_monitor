"""
定时与触发任务：12h 复盘（拉取 + 双类型总结 + Obsidian + 推送到指定群组 Topic）。
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

from telethon import TelegramClient

from . import gemini_service
from . import obsidian_writer
from .config_loader import get_obsidian_vault
from .mapping_loader import (
    get_sources,
    get_alpha_usernames,
    get_summary_days_back,
    load_mapping,
)
from .telegram_fetch import fetch_messages


async def run_summary_job(
    user_client: TelegramClient,
    api_key: str,
    proxy: dict | None,
    mapping: dict[str, Any] | None = None,
    vault_root: str | None = None,
) -> None:
    """
    执行一次复盘任务：按每个 source 单独拉取消息，分别生成总结与大佬萃取，并写入 Obsidian + 推送到指定 Topic。
    """
    m = mapping or load_mapping()
    sources = get_sources(m)
    alpha_list = get_alpha_usernames(m)
    days_back = get_summary_days_back(m)
    vault = vault_root or get_obsidian_vault()
    now = datetime.now()

    # 统一推送到同一个总结群，Topic 由各 source 的配置决定
    chat_id = int(os.getenv("SUMMARY_CHAT_ID", "-1003863583323"))

    for s in sources:
        gid = s.get("group_id")
        if gid is None:
            continue
        group_name = s.get("name", str(gid))
        topic_id_src = s.get("topic_id")
        print(f"[复盘] 正在处理来源：{group_name} (group_id={gid}, topic_id={topic_id_src})")

        # 拉取该来源的消息
        msgs = await fetch_messages(
            user_client,
            gid,
            topic_id_src,
            s.get("usernames") or [],
            days_back,
        )
        msgs.sort(key=lambda x: x.get("时间", ""))

        # 1. 该来源的群聊总结
        if msgs:
            print(f"[复盘] {group_name} 共 {len(msgs)} 条消息，开始总结...")
            summary = await gemini_service.analyze_global_summary(msgs, api_key, proxy)
            if summary and vault:
                obsidian_writer.write_obsidian_md(
                    vault,
                    "Summary",
                    group_name,
                    summary,
                    at=now,
                    keywords=["复盘", "交易准则", "异动"],
                )
            if summary:
                # 每个 source 可在 mapping.yaml 中配置 summary_topic_id
                summary_topic_id = int(
                    s.get("summary_topic_id") or os.getenv("SUMMARY_TOPIC_ID", "4")
                )
                await _send_to_topic(
                    user_client,
                    summary,
                    chat_id,
                    summary_topic_id,
                    title=f"📊 {group_name} 群聊复盘",
                )
        else:
            print(f"[复盘] {group_name} 无新消息，跳过总结")

        # 2. 该来源下的大佬言论萃取（仍统一发到 ALPHA_TOPIC_ID）
        if alpha_list:
            alpha_messages = [m for m in msgs if _username_from_msg(m) in alpha_list]
        else:
            alpha_messages = []

        if alpha_messages and alpha_list:
            print(f"[复盘] {group_name} 大佬言论 {len(alpha_messages)} 条，开始萃取...")
            alpha_summary = await gemini_service.analyze_alpha_insights(
                alpha_messages, api_key, proxy
            )
            if alpha_summary and vault:
                obsidian_writer.write_obsidian_md(
                    vault,
                    "Alpha_Insights",
                    group_name,
                    alpha_summary,
                    at=now,
                    keywords=["大佬", "Alpha", "观点"],
                )
            if alpha_summary:
                alpha_topic_id = int(os.getenv("ALPHA_TOPIC_ID", "6"))
                await _send_to_topic(
                    user_client,
                    alpha_summary,
                    chat_id,
                    alpha_topic_id,
                    title=f"📌 {group_name} 大佬言论总结",
                )
        else:
            print(f"[复盘] {group_name} 无大佬言论或未配置 alpha_usernames，跳过萃取")


def _username_from_msg(m: dict) -> str:
    uid = m.get("发言人ID", "") or ""
    return uid.lstrip("@").strip()


async def _send_to_topic(
    client: TelegramClient,
    text: str,
    chat_id: int,
    topic_id: int,
    title: str | None = None,
) -> None:
    """发到指定群组 Topic，长消息分块。"""
    max_len = 4096
    try:
        header = f"{title}\n\n" if title else ""
        content = header + text
        if len(content) <= max_len:
            await client.send_message(chat_id, content, reply_to=topic_id, parse_mode="md")
        else:
            chunks = []
            buf = ""
            for line in content.split("\n"):
                if len(buf) + len(line) + 1 > max_len:
                    if buf:
                        chunks.append(buf)
                    buf = line + "\n"
                else:
                    buf += line + "\n"
            if buf:
                chunks.append(buf)
            for i, chunk in enumerate(chunks, 1):
                prefix = f"📊 总结 ({i}/{len(chunks)})\n\n" if len(chunks) > 1 else ""
                await client.send_message(
                    chat_id,
                    prefix + chunk,
                    reply_to=topic_id,
                    parse_mode="md",
                )
                if i < len(chunks):
                    await asyncio.sleep(1)
        print(f"[复盘] 已发送到群组 {chat_id} 的 Topic {topic_id}")
    except Exception as e:
        print(f"[复盘] 发送到 Topic 失败: {e}")


def schedule_summary_every_12h(
    user_client: TelegramClient,
    api_key: str,
    proxy: dict | None,
    mapping: dict[str, Any] | None = None,
    vault_root: str | None = None,
) -> asyncio.Task:
    """
    启动一个后台任务，每 12 小时执行一次 run_summary_job。
    返回 asyncio.Task，便于 main 里 cancel。
    """
    async def loop():
        while True:
            await run_summary_job(user_client, api_key, proxy, mapping, vault_root)
            await asyncio.sleep(12 * 3600)

    return asyncio.create_task(loop())
