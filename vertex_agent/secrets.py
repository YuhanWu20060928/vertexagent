from __future__ import annotations

import json
from pathlib import Path

KEY_NAME = "deepseek_key.json"
MODEL_ID = "deepseek-flash"
PRO_MODEL_ID = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
_FLASH_NAMES = {"deepseek-flash", "deepseek-v4.1-flash", "deepseek-v4-flash"}
_PRO_NAMES = {"deepseek-v4-pro", "deepseek-v4.1-pro", "deepseek-pro"}


def key_path(data_dir: Path) -> Path:
    return data_dir / KEY_NAME


def load_api_key(data_dir: Path) -> str:
    path = key_path(data_dir)
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    key = str(payload.get("api_key") or "").strip()
    return key


def save_api_key(data_dir: Path, api_key: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = key_path(data_dir)
    path.write_text(
        json.dumps({"api_key": api_key.strip(), "model": MODEL_ID, "base_url": BASE_URL}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_api_key(data_dir: Path) -> None:
    path = key_path(data_dir)
    if path.exists():
        path.unlink()


def mask_key(api_key: str) -> str:
    key = api_key.strip()
    if len(key) <= 10:
        return "已保存"
    return f"{key[:6]}…{key[-4:]}"


def key_status(data_dir: Path) -> dict:
    key = load_api_key(data_dir)
    return {
        "registered": bool(key),
        "hint": mask_key(key) if key else "",
        "model": MODEL_ID,
        "base_url": BASE_URL,
    }


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    bare = host.split("%", 1)[0].strip("[]")
    return bare in {"127.0.0.1", "::1", "localhost"}


def _deepseek_name(model: str) -> str:
    name = (model or "").strip().lower()
    for suffix in (":latest", ":cloud"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def is_deepseek_model(model: str) -> bool:
    name = _deepseek_name(model)
    return name in _FLASH_NAMES or name in _PRO_NAMES


def api_model_id(model: str) -> str:
    """页面上的 Pro / Flash 换成官方接口使用的模型名。"""
    if _deepseek_name(model) in _PRO_NAMES:
        return PRO_MODEL_ID
    return MODEL_ID
