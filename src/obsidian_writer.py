"""
Obsidian 联动：按命名规则与目录分级写入 Markdown，带 YAML frontmatter。
命名格式：[类别]_[群聊名]_[YYYYMMDD_HHmm].md
目录：{OBSIDIAN_VAULT}/Trading_Intelligence/Summaries/ 与 Alpha_Insights/
"""
from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

# 类别与子目录对应
CATEGORY_DIR = {
    "Summary": "Summaries",
    "Alpha_Insights": "Alpha_Insights",
}


def _sanitize_name(s: str) -> str:
    """替换不宜做文件名的字符。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    return s.strip() or "unknown"


def build_obsidian_path(
    vault_root: str | Path,
    category: str,
    group_name: str,
    at: datetime | None = None,
) -> Path:
    """
    得到目标文件路径（不含写入）。类别为 Summary 或 Alpha_Insights。
    """
    vault = Path(vault_root)
    sub = CATEGORY_DIR.get(category, "Summaries")
    base = vault / "Trading_Intelligence" / sub
    base.mkdir(parents=True, exist_ok=True)
    t = at or datetime.now()
    time_str = t.strftime("%Y%m%d_%H%m")
    safe_name = _sanitize_name(group_name)
    filename = f"{category}_{safe_name}_{time_str}.md"
    return base / filename


def frontmatter_yaml(date: str, source: str, keywords: list[str] | None = None) -> str:
    """生成 YAML frontmatter 字符串。"""
    lines = [
        "---",
        f"date: {date}",
        f"source: {source}",
        "tags:",
    ]
    for kw in keywords or []:
        lines.append(f"  - {kw}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_obsidian_md(
    vault_root: str | Path,
    category: str,
    group_name: str,
    body: str,
    at: datetime | None = None,
    keywords: list[str] | None = None,
) -> Path:
    """
    写入一篇 Obsidian Markdown。body 为正文（不含 frontmatter）。
    返回写入的文件路径。
    """
    path = build_obsidian_path(vault_root, category, group_name, at)
    at = at or datetime.now()
    date_str = at.strftime("%Y-%m-%d %H:%M")
    fm = frontmatter_yaml(date_str, group_name, keywords)
    path.write_text(fm + body, encoding="utf-8")
    print(f"[Obsidian] 已写入: {path}")
    return path
