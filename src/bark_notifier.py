"""
Bark API 封装：标题+内容推送到手机。
"""
from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx


async def push_bark(key: str | None, title: str, content: str, max_content_len: int = 100) -> bool:
    """
    发送 Bark 通知。key 为空则跳过。
    content 过长时自动截断并加省略号。
    """
    if not key or not key.strip():
        return False
    content_display = content[:max_content_len] + "..." if len(content) > max_content_len else content
    title_enc = quote(str(title))
    body_enc = quote(content_display)
    url = f"https://api.day.app/{key.strip()}/{title_enc}/{body_enc}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            ok = r.is_success
            if ok:
                print("[Bark] 推送成功")
            else:
                print(f"[Bark] 推送失败: {r.status_code}")
            return ok
    except Exception as e:
        print(f"[Bark] 推送失败: {e}")
        return False


def push_bark_sync(key: str | None, title: str, content: str, max_content_len: int = 100) -> bool:
    """同步版本，供非 async 上下文使用。"""
    if not key or not key.strip():
        return False
    content_display = content[:max_content_len] + "..." if len(content) > max_content_len else content
    title_enc = quote(str(title))
    body_enc = quote(content_display)
    url = f"https://api.day.app/{key.strip()}/{title_enc}/{body_enc}"
    try:
        r = httpx.get(url, timeout=10.0)
        return r.is_success
    except Exception as e:
        print(f"[Bark] 推送失败: {e}")
        return False
