from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
MATLAB_LOCAL_MODEL = "matlab-r2024b"
MATLAB_COMPILE_MODEL = "matlab-r2024b:latest"


def model_base(model: str) -> str:
    """去掉 Ollama 的 :latest，便于和页面上的模型名对齐。"""
    name = (model or "").strip().lower()
    if name.endswith(":latest"):
        name = name[: -len(":latest")]
    return name


def is_matlab_model(model: str) -> bool:
    return model_base(model) == MATLAB_LOCAL_MODEL


def is_page_model(model: str) -> bool:
    """操作页保留 DeepSeek V4.1 Pro、DeepSeek V4.1 Flash 和 qwen3.5。"""
    from vertex_agent.secrets import is_deepseek_model

    if is_deepseek_model(model):
        return True
    name = model_base(model)
    return name == "qwen3.5" or name.startswith("qwen3.5:")


@dataclass
class AppConfig:
    host: str
    port: int
    base_url: str
    model: str
    general_model: str
    temperature: float
    num_ctx: int
    num_predict: int
    timeout_sec: float
    max_steps: int
    self_edit: bool
    matlab: str
    project_root: Path
    workspace: Path
    data_dir: Path


def _read_yaml() -> dict:
    path = PROJECT_ROOT / "config.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _runtime_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_runtime_settings(updates: dict) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = _runtime_settings()
    for key, value in updates.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def load_config() -> AppConfig:
    raw = _read_yaml()
    server = raw.get("server") or {}
    llm = raw.get("llm") or {}
    agent = raw.get("agent") or {}
    matlab = raw.get("matlab") or {}
    runtime = _runtime_settings()

    workspace_setting = runtime.get("workspace") or raw.get("workspace") or "workspace"
    workspace = Path(workspace_setting)
    if not workspace.is_absolute():
        workspace = PROJECT_ROOT / workspace

    model = str(runtime.get("model") or llm.get("model") or "qwen2.5:7b")
    general_model = str(runtime.get("general_model") or "")
    if not general_model or is_matlab_model(general_model):
        general_model = "qwen2.5:7b" if is_matlab_model(model) else model

    return AppConfig(
        host=str(server.get("host") or "0.0.0.0"),
        port=int(server.get("port") or 8765),
        base_url=str(llm.get("base_url") or "http://127.0.0.1:11434").rstrip("/"),
        model=model,
        general_model=general_model,
        temperature=float(llm.get("temperature") if llm.get("temperature") is not None else 0.2),
        num_ctx=int(llm.get("num_ctx") or 8192),
        num_predict=int(llm.get("num_predict") or 4096),
        timeout_sec=float(llm.get("timeout_sec") or 300),
        max_steps=int(agent.get("max_steps") or 10),
        self_edit=bool(agent.get("self_edit", True)),
        matlab=str(matlab.get("executable") or ""),
        project_root=PROJECT_ROOT,
        workspace=workspace,
        data_dir=DATA_DIR,
    )


def resolve_chat_model(selected: str | None, requested: str | None) -> str:
    """本次对话用用户当场选中的模型，没有传入时用已保存的选择。"""
    model = (requested or "").strip() or (selected or "").strip()
    if not model or len(model) > 80 or any(ch in model for ch in "\\/\n\r"):
        raise ValueError("模型名称不合法")
    return model


CODE_LANGUAGES = {"python", "c", "cpp"}


def model_for_task(
    selected: str | None,
    requested: str | None,
    *,
    language: str = "",
    mode: str = "",
    general_model: str = "",
) -> str:
    """代码编程只接受 Python、C、C++。模型仍用用户选中的那一个。"""
    del general_model
    lang = (language or "").strip().lower()
    if (mode or "") == "workspace" and lang and lang not in CODE_LANGUAGES:
        raise ValueError("代码编程仅支持 Python、C 和 C++")
    chosen = resolve_chat_model(selected, requested)
    if not is_page_model(chosen):
        raise ValueError("模型只支持 DeepSeek V4.1 Pro、DeepSeek V4.1 Flash 和 qwen3.5")
    return chosen


def assert_workspace_allowed(workspace: Path, project_root: Path) -> Path:
    workspace = workspace.expanduser().resolve()
    project_root = project_root.resolve()
    if workspace == project_root or project_root.is_relative_to(workspace):
        raise ValueError("工作区不能包含 VertexAgent 程序目录，请指定单独的项目文件夹")
    return workspace
