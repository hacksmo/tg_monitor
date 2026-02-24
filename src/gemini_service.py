"""
Gemini 服务：全局群聊总结 + 大佬言论深度萃取。双 Prompt，支持代理与多模型回退。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pandas as pd

# 全局群聊总结 Prompt（交易准则、操作逻辑、异动提醒）
PROMPT_GLOBAL_SUMMARY = """你是一个美股交易丰富的交易员。

请对以下 Telegram 群组消息进行深度复盘分析（共 {num_messages} 条消息）：

{csv_content}

请按照以下维度进行总结，格式要精美，多用 Emoji，适合手机端阅读：

## 📊 【交易准则】
大佬交易下单前的逻辑和卖出逻辑是什么，加仓逻辑是什么，该如何去找股票背后的逻辑，过滤掉闲聊信息。

## 💡 【操作逻辑】
提取出他们提到具体的入场/止损理由。包括：
- 技术面信号
- 基本面逻辑
- 风险控制点

## 🚀 【异动提醒】
有没有提到某些冷门股或涨幅好的相关标的？列出值得关注的标的和原因。

请用 Markdown 格式输出，确保在 Telegram 中显示美观。"""

# 大佬言论深度萃取 Prompt
PROMPT_ALPHA_INSIGHTS = """你是一位资深美股交易员与情报分析师。

以下是一组你关注的「大佬」在群内的发言记录（共 {num_messages} 条），请做深度萃取与结构化提炼：

{csv_content}

请按以下结构输出 Markdown 报告，便于后续检索与决策参考：

## 🧠 核心观点提炼
用 3～5 条 bullet 概括大佬们在本周期内的主要观点与共识/分歧。

## 📐 逻辑与依据
他们提到的技术面、基本面或宏观依据（含具体标的、价位、逻辑链）。

## 🎯 标的与操作建议
提到的具体标的、仓位思路、止损/止盈思路；标注不确定性高的部分。

## ⚠️ 风险与注意
他们提到的风险点或对当前市场的警惕。

请用 Markdown 格式输出，保持简洁、可操作。"""


def _get_proxy_url(proxy: dict | None) -> str | None:
    if not proxy or "addr" not in proxy or "port" not in proxy:
        return None
    return f"http://{proxy['addr']}:{proxy['port']}"


def _set_proxy_env(proxy_url: str | None) -> tuple[str | None, str | None]:
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")
    if proxy_url:
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url
    return old_http, old_https


def _restore_proxy_env(old_http: str | None, old_https: str | None) -> None:
    if old_http is not None:
        os.environ["HTTP_PROXY"] = old_http
    else:
        os.environ.pop("HTTP_PROXY", None)
    if old_https is not None:
        os.environ["HTTPS_PROXY"] = old_https
    else:
        os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)


def _messages_to_dataframe(messages: list[dict[str, Any]]) -> pd.DataFrame:
    """与 stock_monitor 一致的消息结构转 DataFrame。"""
    return pd.DataFrame(messages)


def _truncate_content(df: pd.DataFrame, max_messages: int = 1000, max_content_len: int = 50000) -> str:
    if "内容" in df.columns:
        df = df.copy()
        df["内容"] = df["内容"].astype(str).apply(lambda x: x[:500] if len(x) > 500 else x)
    if len(df) > max_messages:
        df = df.head(max_messages)
    csv_content = df.to_string(index=False, max_rows=max_messages)
    if len(csv_content) > max_content_len:
        csv_content = csv_content[:max_content_len] + "\n... (内容已截断)"
    return csv_content


async def _generate_with_new_api(api_key: str, prompt: str) -> str | None:
    try:
        from google import genai as google_genai
    except ImportError:
        return None
    client = google_genai.Client(api_key=api_key)
    model_names = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro-preview"]
    max_retries = 3
    for model_name in model_names:
        for retry in range(max_retries):
            try:
                if retry > 0:
                    print(f"🔄 第 {retry + 1} 次重试...")
                print(f"🤖 尝试使用模型: {model_name}")
                response = client.models.generate_content(model=model_name, contents=prompt)
                summary = response.text
                print(f"✅ 成功使用模型: {model_name}")
                return summary
            except Exception as e:
                err = str(e)
                if "404" in err or "not found" in err.lower():
                    break
                if retry < max_retries - 1 and ("disconnected" in err.lower() or "timeout" in err.lower()):
                    await asyncio.sleep(2)
                    continue
                if retry == max_retries - 1:
                    break
    return None


async def _generate_with_old_api(api_key: str, prompt: str) -> str | None:
    try:
        import google.generativeai as genai_old
    except ImportError:
        return None
    genai_old.configure(api_key=api_key)
    model_names = ["gemini-2.5-pro", "gemini-3-pro-preview"]
    max_retries = 3
    for model_name in model_names:
        for retry in range(max_retries):
            try:
                if retry > 0:
                    print(f"🔄 第 {retry + 1} 次重试...")
                print(f"🤖 尝试使用模型: {model_name}")
                model = genai_old.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                summary = response.text
                print(f"✅ 成功使用模型: {model_name}")
                return summary
            except Exception as e:
                err = str(e)
                if "404" in err or "not found" in err.lower():
                    break
                if retry < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                break
    return None


async def analyze_global_summary(
    messages: list[dict[str, Any]],
    api_key: str,
    proxy: dict | None = None,
) -> str | None:
    """
    全局群聊总结。messages 格式与 stock_monitor 一致（时间、发言人ID、昵称、内容）。
    """
    if not messages:
        return None
    df = _messages_to_dataframe(messages)
    csv_content = _truncate_content(df)
    prompt = PROMPT_GLOBAL_SUMMARY.format(num_messages=len(df), csv_content=csv_content)
    proxy_url = _get_proxy_url(proxy)
    old_http, old_https = _set_proxy_env(proxy_url)
    if proxy_url:
        print(f"🔗 已配置代理: {proxy_url}")
    try:
        print("⏳ 正在分析（全局总结）...")
        summary = await _generate_with_new_api(api_key, prompt)
        if summary is None:
            summary = await _generate_with_old_api(api_key, prompt)
        if summary:
            print("✅ Gemini 全局总结完成")
        return summary
    finally:
        _restore_proxy_env(old_http, old_https)


async def analyze_alpha_insights(
    messages: list[dict[str, Any]],
    api_key: str,
    proxy: dict | None = None,
) -> str | None:
    """大佬言论深度萃取。"""
    if not messages:
        return None
    df = _messages_to_dataframe(messages)
    csv_content = _truncate_content(df)
    prompt = PROMPT_ALPHA_INSIGHTS.format(num_messages=len(df), csv_content=csv_content)
    proxy_url = _get_proxy_url(proxy)
    old_http, old_https = _set_proxy_env(proxy_url)
    try:
        print("⏳ 正在分析（大佬言论萃取）...")
        summary = await _generate_with_new_api(api_key, prompt)
        if summary is None:
            summary = await _generate_with_old_api(api_key, prompt)
        if summary:
            print("✅ Gemini 大佬言论萃取完成")
        return summary
    finally:
        _restore_proxy_env(old_http, old_https)


async def generate_brief_15min(
    recent_alpha_texts: list[str],
    rsi_status: str,
    api_key: str,
    proxy: dict | None = None,
) -> str | None:
    """
    生成《15min 异动投资建议简报》。recent_alpha_texts 为最近 N 条大佬言论摘要，rsi_status 描述 RSI 超买/超卖。
    """
    texts_block = "\n".join(f"- {t[:200]}" for t in recent_alpha_texts[:50])
    prompt = f"""你是一位美股短线交易顾问。当前 15 分钟级别出现技术异动：{rsi_status}。

以下为最近群内「大佬」言论摘要（供参考）：
{texts_block}

请生成一份简短的《15 分钟异动投资建议简报》（Markdown），包含：
1. 当前异动解读（1～2 句）
2. 与大佬观点结合后的操作建议（2～3 条）
3. 风险提示（1 条）

控制在 300 字以内，便于群内快速阅读。"""
    proxy_url = _get_proxy_url(proxy)
    old_http, old_https = _set_proxy_env(proxy_url)
    try:
        summary = await _generate_with_new_api(api_key, prompt)
        if summary is None:
            summary = await _generate_with_old_api(api_key, prompt)
        return summary
    finally:
        _restore_proxy_env(old_http, old_https)
