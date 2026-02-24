"""
加载 .secrets/mapping.yaml 或 config/mapping.example.yaml，解析多源与分发配置。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .config_loader import get_mapping_path


def load_mapping() -> dict[str, Any]:
    """加载 YAML，返回原始字典。"""
    path = get_mapping_path()
    if not path.is_file():
        return {"sources": [], "alpha_usernames": [], "summary_days_back": 2}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_sources(mapping: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """返回 sources 列表，每项含 group_id, topic_id, name, usernames, bot_token_env_key, target_chat_ids, bark_on_message。"""
    m = mapping if mapping is not None else load_mapping()
    sources = m.get("sources") or []
    # 归一化：topic_id 可为 None（普通群）
    out = []
    for s in sources:
        s = dict(s)
        s.setdefault("topic_id")
        s.setdefault("usernames", [])
        s.setdefault("target_chat_ids", [])
        s.setdefault("bark_on_message", False)
        s.setdefault("name", str(s.get("group_id", "")))
        out.append(s)
    return out


def get_alpha_usernames(mapping: dict[str, Any] | None = None) -> list[str]:
    """大佬名单，用于深度萃取。"""
    m = mapping if mapping is not None else load_mapping()
    return list(m.get("alpha_usernames") or [])


def get_summary_days_back(mapping: dict[str, Any] | None = None) -> int:
    """复盘抓取最近几天。"""
    m = mapping if mapping is not None else load_mapping()
    return int(m.get("summary_days_back") or 2)


def get_stocks_config(mapping: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Longbridge 监控股票列表，每项 symbol, high, low。"""
    m = mapping if mapping is not None else load_mapping()
    return list(m.get("stocks") or [])


def get_brief_config(mapping: dict[str, Any] | None = None) -> dict[str, Any]:
    """15min 简报配置：brief_rsi_overbought, brief_rsi_oversold, brief_target_chat_id_env_key。"""
    m = mapping if mapping is not None else load_mapping()
    return {
        "brief_rsi_overbought": int(m.get("brief_rsi_overbought") or 70),
        "brief_rsi_oversold": int(m.get("brief_rsi_oversold") or 30),
        "brief_target_chat_id_env_key": m.get("brief_target_chat_id_env_key") or "BRIEF_TARGET_CHAT_ID",
    }


def source_key(group_id: int, topic_id: int | None) -> str:
    """用于从 sources 中查找的 key。"""
    return f"{group_id}_{topic_id or 0}"
