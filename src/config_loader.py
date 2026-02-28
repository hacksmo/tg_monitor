
import os
from pathlib import Path
from dotenv import find_dotenv, load_dotenv

# 项目根目录（本文件在 src/ 下）
ROOT = Path(__file__).resolve().parent.parent


def _find_env_path() -> str:
    """优先 .secrets/config.env，否则项目根 .env。"""
    secrets_env = ROOT / ".secrets" / "config.env"
    if secrets_env.is_file():
        return str(secrets_env)
    root_env = ROOT / ".env"
    if root_env.is_file():
        return str(root_env)
    return str(secrets_env)  # 仍返回期望路径，load_dotenv 会忽略不存在的文件


def load_env(required_keys: list[str] | None = None) -> None:
    """
    加载环境变量。required_keys 为必须存在的 key 列表，缺一则会抛错。
    若未传 required_keys，仅加载不校验。
    """
    path = _find_env_path()
    if not Path(path).is_file():
        path = find_dotenv() or str(ROOT / ".env")
    if path:
        load_dotenv(path, override=True)

    if required_keys:
        missing = [k for k in required_keys if not os.getenv(k)]
        if missing:
            raise ValueError(f"请在 .secrets/config.env 或 .env 中设置: {', '.join(missing)}")


def get_proxy() -> dict | None:
    """返回 Telethon 使用的代理字典，未配置则返回 None。"""
    return None


def get_telegram_credentials() -> tuple[int, str]:
    """(API_ID, API_HASH)。"""
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    if not api_id or not api_hash:
        raise ValueError("请设置 API_ID 和 API_HASH")
    return int(api_id), api_hash.strip()


def get_phone_number() -> str:
    phone_number = os.getenv("PHONE_NUMBER")
    if not phone_number:
        raise ValueError("缺少 PHONE_NUMBER")
    return phone_number


def get_gemini_api_key() -> str:
    """Gemini API Key。"""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("请设置 GEMINI_API_KEY 或 GOOGLE_API_KEY")
    return key.strip()


def get_bark_key() -> str | None:
    """Bark Key，可选。"""
    return (os.getenv("BARK_KEY") or "").strip() or None


def get_obsidian_vault() -> str | None:
    """Obsidian 库根路径，可选。"""
    return (os.getenv("OBSIDIAN_VAULT") or "").strip() or None


def get_bot_token(env_key: str) -> str | None:
    """根据 mapping 中的 bot_token_env_key 取 Bot Token。"""
    return (os.getenv(env_key) or "").strip() or None


def get_mapping_path() -> Path:
    """mapping 文件路径：优先 .secrets/mapping.yaml。"""
    p = ROOT / ".secrets" / "mapping.yaml"
    if p.is_file():
        return p
    return ROOT / "config" / "mapping.example.yaml"
