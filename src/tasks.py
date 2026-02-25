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

import hashlib
import json
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent


def _load_summary_cache() -> dict[str, Any]:
    """从 .secrets/summary_cache.json 读取上次复盘的签名，用于避免重复调用 Gemini。"""
    cache_path = ROOT / ".secrets" / "summary_cache.json"
    if not cache_path.is_file():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[复盘] 读取缓存失败，忽略: {e}")
        return {}


def _save_summary_cache(cache: dict[str, Any]) -> None:
    """把本次复盘的签名写回 .secrets/summary_cache.json。"""
    cache_dir = ROOT / ".secrets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "summary_cache.json"
    try:
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[复盘] 写入缓存失败，忽略: {e}")


def _messages_signature(msgs: list[dict]) -> str:
    """根据消息内容生成签名，用于判断本次与上次是否相同。"""
    h = hashlib.sha256()
    # 只取最近 N 条，避免消息太多时哈希过慢
    tail = msgs[-500:] if len(msgs) > 500 else msgs
    for m in tail:
        line = f"{m.get('时间','')}|{m.get('发言人ID','')}|{m.get('内容','')}\n"
        h.update(line.encode("utf-8", errors="ignore"))
    return h.hexdigest()


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

    # 读取上次复盘缓存，避免重复对相同内容调用 Gemini
    cache = _load_summary_cache()

    for s in sources:
        gid = s.get("group_id")
        if gid is None:
            continue
        group_name = s.get("name", str(gid))
        topic_id_src = s.get("topic_id")
        print(f"[复盘] 正在处理来源：{group_name}")

        # 拉取该来源的消息
        msgs = await fetch_messages(
            user_client,
            gid,
            topic_id_src,
            s.get("usernames") or [],
            days_back,
        )
        msgs.sort(key=lambda x: x.get("时间", ""))

        # 计算本次消息内容签名
        src_key = s.get("key") or f"{gid}_{topic_id_src or 0}"
        sig = _messages_signature(msgs) if msgs else ""
        last = cache.get(src_key) or {}
        last_sig = last.get("signature")

        # 若消息签名与上次完全一致，则跳过 Gemini 调用（节假日或重启脚本时尤其有用）
        if msgs and sig and last_sig == sig:
            print(f"[复盘] {group_name} 内容与上次相同，跳过本轮 Gemini 复盘。")
            continue

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
                # 记录本次签名，方便下次跳过重复内容
                cache[src_key] = {
                    "signature": sig,
                    "updated_at": now.isoformat(timespec="seconds"),
                }
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

    # 所有来源处理完后，更新缓存
    _save_summary_cache(cache)


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
