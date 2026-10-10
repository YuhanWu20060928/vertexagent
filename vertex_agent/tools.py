from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from vertex_agent.memory import MemoryStore
from vertex_agent.safety import (
    AGENT_FILES,
    AGENT_PREFIXES,
    SKIP_DIRS,
    EditError,
    EditLog,
    assert_agent_target,
    newline_style,
    normalize_newlines,
    now_id,
    python_syntax_error,
    read_text,
    resolve_inside,
    unified_diff,
    write_text,
)

MAX_READ_LINES = 220
MAX_OUTPUT = 12000


def _clip(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[输出已截断]"


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


class Toolbox:
    def __init__(
        self,
        project_root: Path,
        workspace: Path,
        data_dir: Path,
        memory: MemoryStore,
        matlab: str = "",
        self_edit: bool = True,
    ):
        self.project_root = project_root.resolve()
        self.workspace = workspace.resolve()
        self.data_dir = data_dir.resolve()
        self.memory = memory
        self.matlab = matlab
        self.self_edit = self_edit
        self.log = EditLog(self.data_dir)
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "_runs").mkdir(parents=True, exist_ok=True)

    def schemas(self) -> list[dict]:
        return [
            _schema(
                "list_files",
                "列出工作区或 Agent 源码中的文件。",
                {
                    "scope": _enum(["workspace", "agent"], "workspace 是用户项目，agent 是 VertexAgent 自身源码"),
                    "path": {"type": "string", "description": "相对目录，空字符串表示根目录"},
                },
                ["scope"],
            ),
            _schema(
                "read_file",
                "读取文本文件，左侧数字是行号。后续 apply_edit 的 old_string 不要包含这些行号。",
                {
                    "scope": _enum(["workspace", "agent"]),
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "description": "从 1 开始，默认 1"},
                    "end_line": {"type": "integer", "description": "含本行，默认最多再读 220 行"},
                },
                ["scope", "path"],
            ),
            _schema(
                "search_code",
                "在工作区或 Agent 源码里搜索字符串。",
                {
                    "scope": _enum(["workspace", "agent"]),
                    "query": {"type": "string"},
                    "path": {"type": "string", "description": "可选子目录"},
                },
                ["scope", "query"],
            ),
            _schema(
                "apply_edit",
                "把改动直接写入磁盘。这是自主改代码的唯一入口。kind=replace 做精确替换；kind=lines 按行号替换（含端点，end_line 小于 start_line 表示在该行前插入）；kind=write 只用于新建还不存在的文件，不能覆盖已有文件。",
                {
                    "scope": _enum(["workspace", "agent"]),
                    "path": {"type": "string"},
                    "kind": _enum(["replace", "lines", "write"]),
                    "old_string": {"type": "string", "description": "kind=replace 时的原文，必须唯一匹配"},
                    "new_string": {"type": "string", "description": "kind=replace 时的新文本"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "content": {"type": "string", "description": "kind=lines 或 write 的新内容"},
                    "reason": {"type": "string", "description": "为什么改"},
                },
                ["scope", "path", "kind", "reason"],
            ),
            _schema(
                "run_code",
                "运行工作区里的 Python、C 或 MATLAB。source 会写到临时文件再运行；path 运行已有文件。",
                {
                    "language": _enum(["python", "c", "cpp"]),
                    "path": {"type": "string", "description": "工作区内相对路径，可空"},
                    "source": {"type": "string", "description": "临时代码，可空"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "传给程序的参数"},
                },
                ["language"],
            ),
            _schema(
                "verify_code",
                "编译并运行工作区里的文件，返回自我验证是否通过。改完代码后必须调用，未通过就按报错再改。",
                {
                    "path": {"type": "string", "description": "工作区内相对路径"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "传给程序的参数"},
                },
                ["path"],
            ),
            _schema(
                "remember",
                "记住用户的代码风格、项目约定或长期偏好。",
                {"text": {"type": "string"}},
                ["text"],
            ),
            _schema(
                "recall",
                "检索长期记忆。query 为空时返回最近几条。",
                {"query": {"type": "string"}},
                [],
            ),
            _schema(
                "validate_agent",
                "检查 VertexAgent 的 Python 源码能否通过语法编译。修改自身代码后调用。",
                {},
                [],
            ),
        ]

    def execute(self, name: str, arguments: dict | str | None) -> str:
        args = _args(arguments)
        try:
            handler = getattr(self, f"tool_{name}", None)
            if handler is None:
                return _dump({"ok": False, "error": f"未知工具 {name}"})
            return handler(args)
        except EditError as exc:
            return _dump({"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - 把错误交回模型继续改
            return _dump({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def tool_list_files(self, args: dict) -> str:
        scope = args.get("scope") or "workspace"
        relative = str(args.get("path") or "")
        if scope == "agent" and not relative:
            rows = []
            for name in ("vertex_agent", "tests", *sorted(AGENT_FILES)):
                path = self.project_root / name
                if path.exists():
                    rows.append({"name": name, "type": "dir" if path.is_dir() else "file"})
            return _dump({"ok": True, "path": ".", "entries": rows})
        directory = self._directory(scope, relative)
        rows = []
        for path in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if path.name in SKIP_DIRS or path.name.startswith("."):
                continue
            rows.append({"name": path.name, "type": "dir" if path.is_dir() else "file"})
            if len(rows) >= 200:
                break
        return _dump({"ok": True, "path": relative or ".", "entries": rows})

    def tool_read_file(self, args: dict) -> str:
        path = self._file(args.get("scope") or "workspace", args["path"], must_exist=True)
        text = read_text(path)
        lines = text.splitlines()
        start = max(1, int(args.get("start_line") or 1))
        end = int(args.get("end_line") or (start + MAX_READ_LINES - 1))
        end = min(end, start + MAX_READ_LINES - 1, len(lines))
        if start > len(lines) and lines:
            raise EditError(f"起始行超出文件长度 {len(lines)}")
        chunk = lines[start - 1 : end]
        numbered = "\n".join(f"{index:4d}|{line}" for index, line in enumerate(chunk, start=start))
        return _dump(
            {
                "ok": True,
                "path": args["path"],
                "start_line": start,
                "end_line": end if lines else 0,
                "total_lines": len(lines),
                "content": numbered,
            }
        )

    def tool_search_code(self, args: dict) -> str:
        scope = args.get("scope") or "workspace"
        root = self._root(scope)
        relative = str(args.get("path") or "")
        if scope == "agent" and not relative:
            files = []
            for prefix in ("vertex_agent", "tests"):
                folder = self.project_root / prefix
                if folder.exists():
                    files.extend(_walk(folder))
            for name in AGENT_FILES:
                file = self.project_root / name
                if file.is_file():
                    files.append(file)
            return self._search_files(root, files, str(args.get("query") or ""))
        base = self._directory(scope, relative) if relative and (root / relative).is_dir() else self._file(scope, relative, True) if relative else root
        query = str(args.get("query") or "")
        if not query:
            raise EditError("query 为空")
        needle = query.lower()
        hits = []
        files = [base] if base.is_file() else _walk(base)
        for file in files:
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    hits.append(
                        {
                            "path": file.relative_to(root).as_posix(),
                            "line": number,
                            "text": line[:240],
                        }
                    )
                    if len(hits) >= 40:
                        return _dump({"ok": True, "hits": hits, "truncated": True})
        return _dump({"ok": True, "hits": hits, "truncated": False})

    def _search_files(self, root: Path, files: list[Path], query: str) -> str:
        if not query:
            raise EditError("query 为空")
        needle = query.lower()
        hits = []
        for file in files:
            if not file.is_file():
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    hits.append({"path": file.relative_to(root).as_posix(), "line": number, "text": line[:240]})
                    if len(hits) >= 40:
                        return _dump({"ok": True, "hits": hits, "truncated": True})
        return _dump({"ok": True, "hits": hits, "truncated": False})

    def tool_apply_edit(self, args: dict) -> str:
        scope = args.get("scope") or "workspace"
        if scope == "agent" and not self.self_edit:
            raise EditError("配置已关闭自主修改 Agent 源码")
        kind = args.get("kind")
        relative = str(args.get("path") or "")
        reason = str(args.get("reason") or "未说明")[:300]
        path = self._file(scope, relative, must_exist=(kind != "write"))
        before = read_text(path) if path.exists() else ""
        if kind == "replace":
            after = _replace(before, str(args.get("old_string") or ""), str(args.get("new_string") or ""))
        elif kind == "lines":
            after = _replace_lines(
                before,
                int(args.get("start_line") or 0),
                int(args.get("end_line") or 0),
                str(args.get("content") if args.get("content") is not None else ""),
            )
        elif kind == "write":
            if path.exists():
                raise EditError("文件已存在。请改用 replace 或 lines，不要整文件覆盖")
            if "content" not in args or args.get("content") is None:
                raise EditError("write 需要 content")
            after = str(args.get("content"))
            if after and not after.endswith("\n"):
                after += "\n"
        else:
            raise EditError("kind 必须是 replace、lines 或 write")
        if len(after) > 200_000:
            raise EditError("文件过大")
        return self._commit(scope, path, relative.replace("\\", "/"), before, after, kind, reason)

    def save_text(self, relative: str, content: str) -> str:
        path = self._file("workspace", relative, must_exist=False)
        before = read_text(path) if path.exists() else ""
        after = str(content)
        if after and not after.endswith("\n"):
            after += "\n"
        if len(after) > 200_000:
            raise EditError("文件过大")
        return self._commit("workspace", path, relative.replace("\\", "/"), before, after, "write", "编译调试页保存")

    def read_raw(self, scope: str, relative: str) -> str:
        path = self._file(scope, relative, must_exist=True)
        text = read_text(path)
        if len(text) > 200_000:
            raise EditError("文件过大")
        return _dump({"ok": True, "scope": scope, "path": relative.replace("\\", "/"), "content": text})

    def save_scoped(self, scope: str, relative: str, content: str) -> str:
        if scope not in {"workspace", "agent"}:
            raise EditError("scope 必须是 workspace 或 agent")
        if scope == "agent" and not self.self_edit:
            raise EditError("当前禁止修改系统源码")
        path = self._file(scope, relative, must_exist=False)
        before = read_text(path) if path.exists() else ""
        after = str(content)
        if after and not after.endswith("\n"):
            after += "\n"
        if len(after) > 200_000:
            raise EditError("文件过大")
        reason = "用户端保存系统源码" if scope == "agent" else "编译调试页保存"
        return self._commit(scope, path, relative.replace("\\", "/"), before, after, "write", reason)

    def check_source(self, scope: str, relative: str) -> str:
        if scope == "workspace":
            return self.run_saved(relative, "compile")
        self._file("agent", relative, must_exist=True)
        syntax = json.loads(self.tool_validate_agent({}))
        if not syntax.get("ok"):
            errors = "\n".join(syntax.get("errors") or [])
            return _dump({"ok": False, "command": "检查系统 Python 语法", "stdout": "", "stderr": errors, "language": "python"})
        ran = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], self.project_root, 90)
        return _dump({"command": "python -m unittest discover -s tests -q", "language": "python", **ran, "ok": ran["returncode"] == 0})

    def build_action(self, scope: str, relative: str, action: str, args: list[str] | None = None) -> str:
        program_args = _program_args(args)
        if action == "verify":
            return self.verify_saved(scope, relative, program_args)
        if scope == "agent":
            return self._agent_action(relative, action, program_args)
        return self.run_saved(relative, action, program_args)

    def verify_saved(self, scope: str, relative: str, args: list[str] | None = None) -> str:
        compiled = json.loads(self.build_action(scope, relative, "compile", args))
        if not compiled.get("ok"):
            compiled["ok"] = False
            compiled["diagnosis"] = "自我验证未通过：编译失败"
            compiled["command"] = f"自我验证 {relative}"
            return _dump(compiled)
        if scope == "agent" and compiled.get("language") == "text":
            compiled["diagnosis"] = "这个文件不需要运行验证"
            compiled["command"] = f"自我验证 {relative}"
            return _dump(compiled)
        if scope == "workspace" and _language_of(self._file("workspace", relative, must_exist=True)) == "solidworks":
            compiled["diagnosis"] = "宏只做检查，不会启动"
            compiled["command"] = f"自我验证 {relative}"
            return _dump(compiled)
        follow = "debug" if scope == "agent" else "run"
        ran = json.loads(self.build_action(scope, relative, follow, args))
        ok, diagnosis = _verify_verdict(ran)
        stdout = "\n".join(part for part in (compiled.get("stdout"), ran.get("stdout")) if part)
        stderr = "\n".join(part for part in (compiled.get("stderr"), ran.get("stderr")) if part)
        return _dump(
            {
                "ok": ok,
                "returncode": ran.get("returncode", 0 if ok else 1),
                "command": f"自我验证 {relative}",
                "stdout": stdout,
                "stderr": stderr,
                "language": ran.get("language") or compiled.get("language") or "",
                "diagnosis": diagnosis,
            }
        )

    def publish_release(self, note: str) -> str:
        text = str(note or "").strip()
        if not text:
            raise EditError("写一句版本说明")
        if len(text) > 200:
            raise EditError("版本说明过长")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self.project_root / "data" / "releases" / stamp
        dest.mkdir(parents=True, exist_ok=False)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        for name in ("vertex_agent", "tests"):
            source = self.project_root / name
            if source.is_dir():
                shutil.copytree(source, dest / name, ignore=ignore)
        for name in AGENT_FILES:
            source = self.project_root / name
            if source.is_file():
                shutil.copy2(source, dest / name)
        write_text(dest / "版本说明.txt", text + "\n")
        shown = dest.relative_to(self.project_root).as_posix()
        return _dump({"ok": True, "command": f"发布为新版本 {stamp}", "stdout": shown, "stderr": "", "message": text})

    def run_saved(self, relative: str, action: str, args: list[str] | None = None) -> str:
        path = self._file("workspace", relative, must_exist=True)
        language = _language_of(path)
        if language not in {"python", "c", "cpp"}:
            raise EditError("代码编程仅支持 Python、C 和 C++")
        program_args = _program_args(args)
        if action == "compile":
            return self._compile_only(path, relative, language)
        if action == "debug" and language in {"c", "cpp"}:
            return self._debug_native(path, language, program_args)
        if action == "debug" and language == "python":
            command = [sys.executable, "-u", "-X", "dev", str(path), *program_args]
            result = _run(command, self.workspace, 30)
            return _dump({"command": " ".join(command), "language": language, **result, "ok": result["returncode"] == 0})
        if language == "python":
            command = [sys.executable, "-u", str(path), *program_args]
            result = _run(command, self.workspace, 30)
            return _dump({"command": " ".join(command), "language": language, **result, "ok": result["returncode"] == 0})
        if language == "c":
            result = self._run_c(path, program_args)
            result["command"] = f"gcc -std=c11 -Wall -O2 {relative}"
            result["language"] = language
            return _dump({**result, "ok": result.get("returncode") == 0})
        if language == "cpp":
            result = self._run_cpp(path, program_args)
            result["command"] = f"g++ -std=c++17 -Wall -O2 {relative}"
            result["language"] = language
            return _dump({**result, "ok": result.get("returncode") == 0})
        raise EditError("代码编程仅支持 Python、C 和 C++")

    def _agent_action(self, relative: str, action: str, program_args: list[str]) -> str:
        path = self._file("agent", relative, must_exist=True)
        if path.suffix.lower() != ".py":
            return _dump({"ok": True, "command": relative, "stdout": "这个文件不用编译。", "stderr": "", "language": "text"})
        if action == "compile":
            problem = python_syntax_error(read_text(path), relative)
            return _dump(
                {
                    "ok": not problem,
                    "returncode": 1 if problem else 0,
                    "command": f"{sys.executable} -m py_compile {relative}",
                    "stdout": "" if problem else "语法检查通过",
                    "stderr": problem or "",
                    "language": "python",
                }
            )
        if Path(relative).name in {"server.py", "__main__.py"}:
            return _dump({"ok": False, "command": relative, "stdout": "", "stderr": "这是正在运行的服务入口，不要再启动一份。", "language": "python"})
        if action == "run":
            command = [sys.executable, "-u", str(path), *program_args]
            result = _run(command, self.project_root, 30)
            return _dump({"command": " ".join(command), "language": "python", **result, "ok": result["returncode"] == 0})
        ran = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], self.project_root, 90)
        return _dump({"command": "python -m unittest discover -s tests -q", "language": "python", **ran, "ok": ran["returncode"] == 0})

    def _compile_only(self, path: Path, relative: str, language: str) -> str:
        if language == "python":
            problem = python_syntax_error(read_text(path), relative)
            return _dump(
                {
                    "ok": not problem,
                    "returncode": 1 if problem else 0,
                    "command": f"{sys.executable} -m py_compile {relative}",
                    "stdout": "" if problem else "语法检查通过",
                    "stderr": problem or "",
                    "language": language,
                }
            )
        if language == "matlab":
            return self._check_matlab(path, relative)
        compiler, standard, label = ("gcc", "c11", "gcc") if language == "c" else ("g++", "c++17", "g++")
        binary = shutil.which(compiler)
        if not binary:
            raise EditError(f"没有找到 {label}")
        command = [binary, f"-std={standard}", "-Wall", "-Wextra", "-fsyntax-only", str(path)]
        result = _run(command, self.workspace, 30)
        return _dump({"command": " ".join(command), "language": language, **result, "ok": result["returncode"] == 0})

    def _debug_native(self, source: Path, language: str, program_args: list[str]) -> str:
        compiler, standard = ("gcc", "c11") if language == "c" else ("g++", "c++17")
        binary = shutil.which(compiler)
        if not binary:
            raise EditError(f"没有找到 {compiler}")
        output = self.workspace / "_runs" / f"{source.stem}_{uuid.uuid4().hex[:6]}.exe"
        compile_cmd = [binary, f"-std={standard}", "-Wall", "-g", "-O0", str(source), "-o", str(output)]
        compiled = _run(compile_cmd, self.workspace, 30)
        if compiled["returncode"] != 0:
            return _dump({"command": " ".join(compile_cmd), "language": language, **compiled, "ok": False})
        try:
            ran = _run([str(output), *program_args], self.workspace, 15)
        finally:
            output.unlink(missing_ok=True)
        return _dump(
            {
                "command": " ".join(compile_cmd),
                "language": language,
                "returncode": ran["returncode"],
                "stdout": ran["stdout"],
                "stderr": (compiled["stderr"] + "\n" + ran["stderr"]).strip(),
                "ok": ran["returncode"] == 0,
            }
        )

    def _run_cpp(self, source: Path, program_args: list[str]) -> dict:
        gxx = shutil.which("g++")
        if not gxx:
            raise EditError("没有找到 g++")
        output = self.workspace / "_runs" / f"{source.stem}_{uuid.uuid4().hex[:6]}.exe"
        compiled = _run([gxx, "-std=c++17", "-Wall", "-O2", str(source), "-o", str(output)], self.workspace, 30)
        if compiled["returncode"] != 0:
            return compiled
        try:
            return _run([str(output), *program_args], self.workspace, 15)
        finally:
            output.unlink(missing_ok=True)

    def _matlab_bin(self) -> str | None:
        candidate = self.matlab if self.matlab and Path(self.matlab).exists() else shutil.which("matlab")
        if not candidate:
            return None
        direct = Path(candidate).resolve().parent / "win64" / "MATLAB.exe"
        if direct.exists():
            return str(direct)
        return candidate

    def _run_matlab_file(self, source: Path, relative: str, program_args: list[str] | None = None) -> str:
        matlab = self._matlab_bin()
        if not matlab:
            return _dump({"ok": False, "returncode": 1, "command": "matlab -batch", "stdout": "", "stderr": "没有找到 MATLAB。", "language": "matlab"})
        result = self._run_matlab(source, program_args)
        result["language"] = "matlab"
        result["command"] = f"matlab -batch {relative}"
        return _dump({**result, "ok": result.get("returncode") == 0})

    def _check_solidworks(self, path: Path, relative: str, action: str) -> str:
        text = read_text(path).strip()
        problem = "" if text else "宏文件是空的。"
        installed = Path(r"C:\Program Files\SOLIDWORKS Corp").exists()
        note = "SolidWorks 宏只做检查，不会启动 SolidWorks。"
        if not installed:
            note = "没有找到 SolidWorks。宏只做检查，不会启动。"
        if action == "run":
            note = "不会启动 SolidWorks。"
        return _dump(
            {
                "ok": not problem,
                "returncode": 1 if problem else 0,
                "command": f"检查 SolidWorks 宏 {relative}",
                "stdout": note,
                "stderr": problem,
                "language": "solidworks",
            }
        )

    def tool_run_code(self, args: dict) -> str:
        language = str(args.get("language") or "").lower()
        program_args = [str(item) for item in (args.get("args") or [])][:8]
        if any(len(item) > 200 or "\n" in item for item in program_args):
            raise EditError("参数不合法")
        source = args.get("source")
        relative = str(args.get("path") or "")
        if source:
            suffix = {"python": ".py", "c": ".c", "cpp": ".cpp"}.get(language)
            if not suffix:
                raise EditError("language 必须是 python、c 或 cpp")
            folder = self.workspace / "_runs" / uuid.uuid4().hex[:8]
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"snippet{suffix}"
            write_text(path, str(source if str(source).endswith("\n") else str(source) + "\n"))
            temporary = True
        elif relative:
            path = self._file("workspace", relative, must_exist=True)
            temporary = False
        else:
            raise EditError("需要 path 或 source")
        try:
            if language == "python":
                result = _run([sys.executable, "-u", str(path), *program_args], self.workspace, 30)
            elif language == "c":
                result = self._run_c(path, program_args)
            elif language == "cpp":
                result = self._run_cpp(path, program_args)
            else:
                raise EditError("language 必须是 python、c 或 cpp")
        finally:
            if temporary:
                shutil.rmtree(path.parent, ignore_errors=True)
        return _dump({"ok": result["returncode"] == 0, **result})

    def tool_verify_code(self, args: dict) -> str:
        relative = str(args.get("path") or "").strip()
        if not relative:
            raise EditError("需要 path")
        program_args = [str(item) for item in (args.get("args") or [])][:8]
        return self.verify_saved("workspace", relative, program_args)

    def tool_remember(self, args: dict) -> str:
        message = self.memory.add(str(args.get("text") or ""))
        return _dump({"ok": True, "message": message})

    def tool_recall(self, args: dict) -> str:
        notes = self.memory.search(str(args.get("query") or ""))
        return _dump({"ok": True, "notes": notes})

    def tool_validate_agent(self, args: dict) -> str:
        errors = []
        package = self.project_root / "vertex_agent"
        for path in sorted(package.rglob("*.py")):
            source = read_text(path)
            problem = python_syntax_error(source, path.relative_to(self.project_root).as_posix())
            if problem:
                errors.append(problem)
        if errors:
            return _dump({"ok": False, "errors": errors})
        return _dump({"ok": True, "message": "Python 语法检查通过"})

    def rollback(self, edit_id: str) -> dict:
        entry = self.log.get(edit_id)
        if not entry or not entry.get("ok"):
            raise EditError("找不到可回滚的记录")
        scope = entry["scope"]
        path = self._file(scope, entry["path"], must_exist=False)
        if scope == "agent":
            assert_agent_target(self.project_root, path if path.is_absolute() else self.project_root / entry["path"])
        message = self.log.restore(entry, path)
        syntax = None
        if path.exists() and path.suffix == ".py" and scope == "agent":
            syntax = python_syntax_error(read_text(path), entry["path"])
            if syntax:
                raise EditError(f"回滚后的文件仍有语法错误：{syntax}")
        result = {"ok": True, "message": message, "path": entry["path"], "edit_id": edit_id}
        self.log.append({**entry, "id": now_id(), "kind": "rollback", "reason": f"回滚 {edit_id}", "ok": True, "diff": ""})
        return result

    def _directory(self, scope: str, relative: str) -> Path:
        root = self._root(scope)
        directory = resolve_inside(root, relative) if relative else root
        if scope == "agent":
            rel = directory.resolve().relative_to(self.project_root).as_posix()
            if rel not in {"vertex_agent", "tests"} and not rel.startswith(AGENT_PREFIXES):
                raise EditError("该目录不在 Agent 源码范围内")
        if not directory.exists():
            raise EditError("目录不存在")
        if not directory.is_dir():
            raise EditError("这不是目录")
        return directory

    def _root(self, scope: str) -> Path:
        if scope == "workspace":
            return self.workspace
        if scope == "agent":
            return self.project_root
        raise EditError("scope 必须是 workspace 或 agent")

    def _file(self, scope: str, relative: str, must_exist: bool) -> Path:
        if not relative:
            raise EditError("path 为空")
        root = self._root(scope)
        path = resolve_inside(root, relative)
        if scope == "agent":
            assert_agent_target(self.project_root, path)
        if must_exist and not path.exists():
            raise EditError("文件不存在")
        if path.exists() and path.is_dir():
            raise EditError("这是目录，不是文件")
        return path

    def _commit(self, scope: str, path: Path, relative: str, before: str, after: str, kind: str, reason: str) -> str:
        if scope == "agent":
            relative = assert_agent_target(self.project_root, path)
        if before == after:
            return _dump({"ok": True, "message": "内容没有变化", "path": relative, "diff": ""})
        edit_id = now_id()
        backup_key = f"{scope}/{relative}"
        backup, created = self.log.backup_file(edit_id, path, backup_key)
        write_text(path, after)
        syntax = None
        if path.suffix == ".py":
            syntax = python_syntax_error(read_text(path), relative)
        if syntax and scope == "agent":
            self.log.restore({"backup": backup, "created": created}, path)
            entry = _entry(edit_id, scope, relative, kind, reason, False, "", backup, created, False)
            entry["error"] = syntax
            self.log.append(entry)
            return _dump({"ok": False, "error": f"语法错误，已回滚：{syntax}", "path": relative})
        diff = unified_diff(relative, before, after)
        restart = scope == "agent" and path.suffix == ".py" and Path(relative).name != "prompts.py"
        entry = _entry(edit_id, scope, relative, kind, reason, True, diff, backup, created, restart)
        if syntax:
            entry["warning"] = syntax
        self.log.append(entry)
        result = {
            "ok": True,
            "edit_id": edit_id,
            "path": relative,
            "scope": scope,
            "diff": diff,
            "restart_required": restart,
        }
        if syntax and scope == "workspace":
            result["warning"] = f"文件已写入，但 Python 语法未通过：{syntax}"
        return _dump(result)

    def _run_c(self, source: Path, program_args: list[str]) -> dict:
        gcc = shutil.which("gcc")
        if not gcc:
            raise EditError("没有找到 gcc")
        output = self.workspace / "_runs" / f"{source.stem}_{uuid.uuid4().hex[:6]}.exe"
        compiled = _run([gcc, "-std=c11", "-Wall", "-O2", str(source), "-o", str(output)], self.workspace, 30)
        if compiled["returncode"] != 0:
            return compiled
        try:
            return _run([str(output), *program_args], self.workspace, 15)
        finally:
            output.unlink(missing_ok=True)

    def _check_matlab(self, source: Path, relative: str) -> str:
        folder = _matlab_quote(source.parent.resolve().as_posix())
        name = _matlab_quote(source.name)
        statement = (
            f"cd('{folder}');"
            f"src = fileread('{name}');"
            "try, tree = mtree(src); catch ME, fprintf(2, '%s\\n', ME.message); exit(1); end;"
            "errs = mtfind(tree, 'Kind', 'ERR');"
            "if ~isempty(errs), node = errs.select(1); msg = '语法错误'; "
            "try, msg = char(node.string); catch, end; "
            f"fprintf(2, '%s:%d: %s\\n', '{name}', node.lineno, msg); exit(1); end;"
            "notes = ''; "
            f"try, msgs = checkcode('{name}','-id'); catch, msgs = []; end; "
            "if ~isempty(msgs), for k = 1:numel(msgs), "
            "line = msgs(k).line; if line == 0, line = 1; end; "
            "cid = ''; if isfield(msgs, 'id'), cid = msgs(k).id; end; "
            f"notes = [notes sprintf('[%s] %s:%d: %s\\n', cid, '{name}', line, "
            "strrep(msgs(k).message, char(10), ' '))]; "
            "end, end; "
            "if isempty(notes), disp('语法检查通过'); "
            "else, disp('语法检查通过（另见静态分析提示）'); fprintf('%s', notes); end;"
        )
        result = self._matlab_batch(statement, 300)
        result["command"] = f"matlab -batch check {relative}"
        result["language"] = "matlab"
        return _dump({**result, "ok": result.get("returncode") == 0})

    def _run_matlab(self, source: Path, program_args: list[str] | None = None) -> dict:
        text = read_text(source)
        folder = _matlab_quote(source.parent.resolve().as_posix())
        target = _matlab_quote(source.resolve().as_posix())
        if matlab_is_function(text):
            call = f"{source.stem}({_matlab_call_args(program_args or [])})"
            statement = f"set(0,'DefaultFigureVisible','off'); cd('{folder}'); addpath('{folder}'); {call}; drawnow; close all force;"
        else:
            statement = f"set(0,'DefaultFigureVisible','off'); cd('{folder}'); run('{target}'); drawnow; close all force;"
        result = self._matlab_batch(statement, 180)
        result["command"] = f"matlab -batch {source.name}"
        if program_args and not matlab_is_function(text):
            note = "脚本不接收运行参数。"
            result["stderr"] = "\n".join(part for part in (result.get("stderr") or "", note) if part)
        return result

    def _matlab_batch(self, statement: str, timeout: int) -> dict:
        matlab = self._matlab_bin()
        if not matlab:
            raise EditError("没有找到 MATLAB")
        encoding = "mbcs" if os.name == "nt" else "utf-8"
        return _run([matlab, "-batch", statement], self.workspace, timeout, encoding)


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _enum(values: list[str], description: str = "") -> dict:
    payload = {"type": "string", "enum": values}
    if description:
        payload["description"] = description
    return payload


def _args(arguments: dict | str | None) -> dict:
    if arguments is None:
        return {}
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise EditError("工具参数必须是对象")
        return parsed
    if isinstance(arguments, dict):
        return arguments
    raise EditError("工具参数无法解析")


def _replace(before: str, old: str, new: str) -> str:
    if not old:
        raise EditError("old_string 为空")
    style = newline_style(before)
    source = normalize_newlines(before)
    old_norm = normalize_newlines(old)
    new_norm = normalize_newlines(new)
    count = source.count(old_norm)
    if count == 0:
        raise EditError("old_string 没有匹配到原文，请先 read_file")
    if count > 1:
        raise EditError(f"old_string 匹配到 {count} 处，请带上更多上下文")
    updated = source.replace(old_norm, new_norm, 1)
    if style == "\r\n":
        return updated.replace("\n", "\r\n")
    return updated


def _replace_lines(before: str, start_line: int, end_line: int, content: str) -> str:
    lines = before.splitlines()
    if start_line < 1:
        raise EditError("start_line 从 1 开始")
    new_lines = content.splitlines()
    if not lines and start_line == 1:
        lines = new_lines
        style = newline_style(before) if before else "\n"
        text = style.join(lines)
        return text + (style if text else "")
    if end_line < start_line:
        if start_line > len(lines) + 1:
            raise EditError(f"插入位置超出文件长度 {len(lines)}")
        index = start_line - 1
        lines[index:index] = new_lines
    else:
        if start_line > len(lines):
            raise EditError(f"起始行超出文件长度 {len(lines)}")
        if end_line > len(lines):
            raise EditError(f"结束行超出文件长度 {len(lines)}")
        lines[start_line - 1 : end_line] = new_lines
    style = newline_style(before) if before else "\n"
    text = style.join(lines)
    if before.endswith(("\n", "\r\n")) or text:
        text += style
    return text


def _walk(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
        for filename in filenames:
            if filename.lower() in {".env"}:
                continue
            found.append(Path(dirpath) / filename)
            if len(found) >= 400:
                return found
    return found


_MATLAB_ENTRY = re.compile(
    r"^function\s+(?:\[[^\]]*\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z]\w*)",
    re.IGNORECASE,
)


def _verify_verdict(result: dict) -> tuple[bool, str]:
    if result.get("ok") is False or result.get("returncode") not in (0, None):
        return False, "自我验证未通过：运行失败"
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    if re.search(r"\bFAIL\b|Assertion failed|断言失败|错误使用", text, re.IGNORECASE):
        return False, "自我验证未通过：自检未通过"
    return True, "自我验证通过"


def matlab_is_function(source: str) -> bool:
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        return stripped.lower().startswith("function")
    return False


def matlab_entry_name(source: str) -> str | None:
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        match = _MATLAB_ENTRY.match(stripped)
        return match.group(1) if match else None
    return None


def _matlab_quote(value: str) -> str:
    return value.replace("'", "''")


def _matlab_call_args(args: list[str]) -> str:
    parts = []
    for item in args:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", item):
            parts.append(item)
        else:
            parts.append("'" + item.replace("'", "''") + "'")
    return ", ".join(parts)


def _language_of(path: Path) -> str:
    return {
        ".py": "python",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".m": "matlab",
        ".swb": "solidworks",
    }.get(path.suffix.lower(), "")


def _program_args(args: list[str] | None) -> list[str]:
    values = [str(item) for item in (args or [])][:8]
    if any(len(item) > 200 or any(char in item for char in "\n\r") for item in values):
        raise EditError("运行参数不合法")
    return values


def _run(command: list[str], cwd: Path, timeout: int, encoding: str = "utf-8") -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode(encoding, errors="replace")
        stderr = (exc.stderr or b"").decode(encoding, errors="replace")
        return {"returncode": -1, "stdout": _clip(stdout), "stderr": _clip(stderr + f"\n超时（{timeout} 秒）")}
    return {
        "returncode": completed.returncode,
        "stdout": _clip(completed.stdout.decode(encoding, errors="replace")),
        "stderr": _clip(completed.stderr.decode(encoding, errors="replace")),
    }


def _entry(
    edit_id: str,
    scope: str,
    relative: str,
    kind: str,
    reason: str,
    ok: bool,
    diff: str,
    backup: str | None,
    created: bool,
    restart: bool,
) -> dict:
    return {
        "id": edit_id,
        "time": datetime_now(),
        "scope": scope,
        "path": relative,
        "kind": kind,
        "reason": reason,
        "ok": ok,
        "diff": diff[:20000],
        "backup": backup,
        "created": created,
        "restart_required": restart,
    }


def datetime_now() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
