from __future__ import annotations

import ast
import difflib
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path

LOCK = threading.RLock()

SECRET_NAMES = {
    ".env",
    ".env.local",
    "credentials.json",
    "id_rsa",
    "id_rsa.pub",
}
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    "_runs",
    "data",
    "backups",
}
AGENT_FILES = {"config.yaml", "README.md", "requirements.txt", "start.ps1"}
AGENT_PREFIXES = ("vertex_agent/", "tests/")


class EditError(Exception):
    pass


def now_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"e-{stamp}"


def resolve_inside(root: Path, relative: str) -> Path:
    if not relative or relative.strip() in {".", "./"}:
        return root.resolve()
    raw = relative.strip().replace("\\", "/")
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise EditError("请使用相对路径")
    if ":" in raw:
        raise EditError("路径不合法")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise EditError("路径不能包含 ..")
    if any(part.lower() in SECRET_NAMES for part in parts):
        raise EditError("拒绝访问敏感文件")
    target = root.resolve().joinpath(*parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise EditError("路径越界")
    return target


def assert_agent_target(project_root: Path, target: Path) -> str:
    relative = target.resolve().relative_to(project_root.resolve()).as_posix()
    if relative == "data" or relative.startswith("data/"):
        raise EditError("不能修改 data 目录")
    if relative in AGENT_FILES or relative.startswith(AGENT_PREFIXES):
        return relative
    raise EditError("该文件不在可自主修改的 Agent 源码范围内")


def unified_diff(path: str, before: str, after: str, limit: int = 200) -> str:
    diff = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    if len(diff) > limit:
        hidden = len(diff) - limit
        diff = diff[:limit] + [f"... 其余 {hidden} 行差异已省略"]
    return "\n".join(diff)


def newline_style(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def python_syntax_error(source: str, filename: str) -> str | None:
    try:
        ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return f"{filename}:{exc.lineno}: {exc.msg}"
    return None


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


class EditLog:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "self_edits.jsonl"
        self.backup_root = data_dir / "backups"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict) -> None:
        with LOCK:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list_entries(self, limit: int = 40) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        items = []
        for line in lines[-limit:]:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        items.reverse()
        return items

    def get(self, edit_id: str) -> dict | None:
        if not self.path.exists():
            return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("id") == edit_id:
                return item
        return None

    def backup_file(self, edit_id: str, absolute: Path, relative_key: str) -> tuple[str | None, bool]:
        created = not absolute.exists()
        if created:
            return None, True
        destination = self.backup_root / edit_id / relative_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(absolute, destination)
        return str(destination), False

    def restore(self, entry: dict, absolute: Path) -> str:
        if entry.get("created"):
            if absolute.exists():
                absolute.unlink()
            return "已删除新建文件"
        backup = entry.get("backup")
        if not backup or not Path(backup).exists():
            raise EditError("找不到备份，无法回滚")
        absolute.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, absolute)
        return "已从备份恢复"
