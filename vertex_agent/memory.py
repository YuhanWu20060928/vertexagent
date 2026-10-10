from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"notes": []})

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"notes": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("记忆内容为空")
        with self._lock:
            data = self._read()
            notes = data.setdefault("notes", [])
            for note in notes:
                if note.get("text") == text:
                    note["time"] = _now()
                    self._write(data)
                    return "这条记忆已存在，已更新时间"
            notes.append({"time": _now(), "text": text[:1000]})
            if len(notes) > 80:
                del notes[:-80]
            self._write(data)
        return "已记住"

    def search(self, query: str) -> list[dict]:
        query = query.strip().lower()
        notes = self._read().get("notes") or []
        if not query:
            return notes[-8:]
        hits = [note for note in notes if query in note.get("text", "").lower()]
        return hits[-8:]

    def summary(self) -> str:
        notes = self._read().get("notes") or []
        if not notes:
            return ""
        return "\n".join(f"- {note.get('text', '')}" for note in notes[-12:])


class SessionStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
        if safe != session_id or not safe:
            raise ValueError("非法会话编号")
        return self.directory / f"{safe}.json"

    def list_sessions(self) -> list[dict]:
        items = []
        for path in self.directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append(
                {
                    "id": data.get("id") or path.stem,
                    "title": data.get("title") or "未命名",
                    "updated": data.get("updated") or "",
                }
            )
        items.sort(key=lambda item: item["updated"], reverse=True)
        return items

    def load(self, session_id: str) -> dict | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session: dict) -> None:
        path = self._path(session["id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
