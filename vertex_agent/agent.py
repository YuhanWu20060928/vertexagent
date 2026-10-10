from __future__ import annotations

import importlib
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime

from vertex_agent.config import MATLAB_LOCAL_MODEL, AppConfig, model_base
from vertex_agent.llm import ModelError, OllamaClient
from vertex_agent.memory import MemoryStore, SessionStore
from vertex_agent.tools import Toolbox

def _model_label(model: str) -> str:
    name = model_base(model)
    if name in {"deepseek-v4-pro", "deepseek-v4.1-pro", "deepseek-pro"}:
        return "DeepSeek V4.1 Pro"
    if name in {"deepseek-flash", "deepseek-v4.1-flash", "deepseek-v4-flash"}:
        return "DeepSeek V4.1 Flash"
    if name == MATLAB_LOCAL_MODEL:
        return "MATLAB R2024b（本地）"
    return model or "当前模型"


def _sampling(config: AppConfig, model: str) -> tuple[float, int, int, bool]:
    """7B 本地模型固定短上下文，且不发送思考参数。"""
    if model_base(model) == MATLAB_LOCAL_MODEL:
        return 0.2, min(int(config.num_ctx), 8192), min(int(config.num_predict), 4096), False
    return config.temperature, config.num_ctx, config.num_predict, True


MODE_PREFIX = {
    "general": "",
    "workspace": "【任务类型：直接修改工作区代码并运行验证。不要只在回复里贴代码。】\n",
    "self": "【任务类型：修改 VertexAgent 自身源码，scope 使用 agent。先阅读相关文件，再用 apply_edit 写入，最后调用 validate_agent。】\n",
}


async def run_turn(
    *,
    ollama: OllamaClient,
    config: AppConfig,
    toolbox: Toolbox,
    sessions: SessionStore,
    memory: MemoryStore,
    session_id: str,
    text: str,
    mode: str,
    think: bool,
    images: list[str] | None = None,
    model: str | None = None,
    language: str = "",
) -> AsyncIterator[dict]:
    prompt = _reload_prompt(config, memory)
    session = sessions.load(session_id) or {
        "id": session_id,
        "title": "新的对话",
        "created": _now(),
        "messages": [],
    }
    chosen = model or config.model
    temperature, num_ctx, num_predict, allow_think = _sampling(config, chosen)
    yield {"type": "session", "session_id": session_id, "title": session.get("title") or "新的对话"}
    yield {"type": "progress", "text": f"正在使用 {_model_label(chosen)}"}

    prior = list(session.get("messages") or [])
    matlab_code = (language or "").strip().lower() == "matlab" and mode == "workspace"
    if matlab_code:
        prompt += (
            "\n\n本次是 MATLAB 编程，按普通对话输出纯代码。"
            "不要调用工具，不要输出 JSON，不要提 apply_edit。"
            "不要提问。回复只能是一个 ```matlab 代码块。"
        )
        prefix = "【只输出一个 MATLAB 代码块，不要工具，不要解释。】\n"
    else:
        prefix = MODE_PREFIX.get(mode, "")
    working = _clip(prior)
    working.insert(0, {"role": "system", "content": prompt})
    user_message: dict = {"role": "user", "content": prefix + text}
    if images:
        user_message["images"] = images
    working.append(user_message)
    user_index = len(working) - 1
    nudged = False
    verify_nudged = False
    edited = False
    verified = False
    used_tools = False
    restart_required = False
    final_content = ""
    finished = False
    step = 0
    budget = config.max_steps
    ceiling = budget * 3

    try:
        while True:
            if step >= budget:
                if step < ceiling and used_tools:
                    budget = min(ceiling, budget + config.max_steps)
                    yield {"type": "progress", "text": "继续处理"}
                else:
                    break
            step += 1
            turn = None
            async for event in ollama.chat(
                model=chosen,
                messages=working,
                tools=None if matlab_code else toolbox.schemas(),
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                think=think and allow_think,
            ):
                if event["type"] == "turn":
                    turn = event
                elif matlab_code and event["type"] in {"token", "thinking"}:
                    continue
                else:
                    yield event
            if turn is None:
                raise ModelError("模型没有返回内容")

            calls = _calls_from_turn(turn)
            content = turn.get("content") or ""
            if calls:
                used_tools = True
                if content:
                    yield {"type": "reset"}
                working.append(_assistant(content, [call["raw"] for call in calls], turn.get("thinking") or ""))
                for call in calls:
                    try:
                        arguments = _arguments(call["arguments"])
                    except json.JSONDecodeError:
                        output = json.dumps({"ok": False, "error": "工具参数不是合法 JSON"}, ensure_ascii=False)
                        yield {"type": "progress", "text": "工具参数无法解析"}
                        working.append(
                            {
                                "role": "tool",
                                "content": output,
                                "tool_name": call["name"],
                                "tool_call_id": call["id"],
                            }
                        )
                        continue
                    yield {"type": "progress", "text": _progress(call["name"], arguments)}
                    output = toolbox.execute(call["name"], arguments)
                    parsed = _parse_output(output)
                    if parsed.get("restart_required"):
                        restart_required = True
                    if call["name"] == "apply_edit" and str(arguments.get("scope") or "workspace") != "agent":
                        edited = True
                    if call["name"] in {"verify_code", "run_code"} and parsed.get("ok"):
                        verified = True
                    yield {"type": "progress", "text": _progress(call["name"], arguments, done=parsed.get("ok", True))}
                    working.append(
                        {
                            "role": "tool",
                            "content": output if len(output) <= 6000 else output[:6000] + "\n...[已截断]",
                            "tool_name": call["name"],
                            "tool_call_id": call["id"],
                        }
                    )
                continue

            if (
                not matlab_code
                and mode in {"workspace", "self"}
                and not used_tools
                and not nudged
                and step < budget
                and "```" in content
            ):
                nudged = True
                yield {"type": "reset"}
                yield {"type": "progress", "text": "正在写入文件"}
                working.append(_assistant(content, thinking=turn.get("thinking") or ""))
                working.append(
                    {
                        "role": "user",
                        "content": "【系统提醒】上一步没有调用工具，代码还没有写入磁盘。请立刻调用 apply_edit，需要验证时再调用 run_code。",
                    }
                )
                continue

            if (
                mode == "workspace"
                and edited
                and not verified
                and not verify_nudged
                and step < budget
            ):
                verify_nudged = True
                yield {"type": "reset"}
                yield {"type": "progress", "text": "正在验证"}
                working.append(_assistant(content, thinking=turn.get("thinking") or ""))
                working.append(
                    {
                        "role": "user",
                        "content": "【系统提醒】代码还没有自我验证。请立刻对刚修改的文件调用 verify_code。未通过就按报错修改后再验证。",
                    }
                )
                continue

            final_content = content
            finished = True
            yield {"type": "progress", "text": ""}
            working.append(_assistant(content, thinking=turn.get("thinking") or ""))
            break
        if not finished:
            yield {"type": "progress", "text": "正在整理结果"}
            working.append(
                {
                    "role": "user",
                    "content": (
                        "【系统提醒】不要再调用工具。最终回复只能是一个 ```matlab 代码块，块外一个字都不要写。"
                        if matlab_code
                        else "【系统提醒】不要再调用工具。根据已经写好的文件和运行结果，直接给出最终回复。"
                    ),
                }
            )
            turn = None
            async for event in ollama.chat(
                model=chosen,
                messages=working,
                tools=None,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                think=think and allow_think,
            ):
                if event["type"] == "turn":
                    turn = event
                else:
                    yield event
            content = (turn or {}).get("content") or ""
            final_content = content
            yield {"type": "progress", "text": ""}
            if content:
                working.append(_assistant(content, thinking=(turn or {}).get("thinking") or ""))
    except ModelError as exc:
        failed = {"role": "user", "content": text}
        if images:
            failed["images"] = images
        session["messages"] = (prior + [failed, {"role": "assistant", "content": str(exc)}])[-40:]
        if (session.get("title") or "") in {"", "新的对话"}:
            session["title"] = text.strip().splitlines()[0][:28] or "新的对话"
        session["updated"] = _now()
        sessions.save(session)
        yield {"type": "error", "message": str(exc)}
        return

    if matlab_code and final_content:
        pure = matlab_code_only(final_content)
        final_content = pure
        yield {"type": "reset"}
        yield {"type": "token", "text": pure}
        for message in reversed(working):
            if message.get("role") == "assistant" and not message.get("tool_calls"):
                message["content"] = pure
                break

    fresh = working[user_index:]
    stored_user = {"role": "user", "content": text}
    if images:
        stored_user["images"] = images
    fresh[0] = stored_user
    fresh = [message for message in fresh if not str(message.get("content") or "").startswith("【系统提醒】")]
    session["messages"] = (prior + [_slim(message) for message in fresh])[-40:]
    title = session.get("title") or ""
    if title in {"", "新的对话"}:
        session["title"] = text.strip().splitlines()[0][:28] or "新的对话"
    session["updated"] = _now()
    sessions.save(session)
    yield {
        "type": "done",
        "session_id": session_id,
        "title": session["title"],
        "restart_required": restart_required,
        "content": final_content,
    }


_MATLAB_FENCE = re.compile(r"```(?:matlab|m)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)


def matlab_code_only(text: str) -> str:
    """MATLAB 回复只保留源码，去掉说明和工具 JSON。"""
    blocks = []
    for block in _MATLAB_FENCE.findall(text or ""):
        code = block.strip()
        if code and not _looks_like_tool_json(code):
            blocks.append(code)
    if blocks:
        return f"```matlab\n{blocks[-1]}\n```"
    embedded = _matlab_from_tool_json(text or "")
    if embedded:
        return f"```matlab\n{embedded.strip()}\n```"
    return (text or "").strip()


def _looks_like_tool_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and '"name"' in stripped and "apply_edit" in stripped


def _matlab_from_tool_json(text: str) -> str:
    decoder = json.JSONDecoder()
    index = 0
    found = ""
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        try:
            obj, offset = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + offset
        if not isinstance(obj, dict):
            continue
        arguments = obj.get("arguments") if isinstance(obj.get("arguments"), dict) else obj
        for key in ("content", "new_string", "source"):
            value = arguments.get(key) if isinstance(arguments, dict) else None
            if isinstance(value, str) and value.strip():
                found = value
    return found


def _assistant(content: str, tool_calls: list | None = None, thinking: str = "") -> dict:
    message: dict = {"role": "assistant", "content": content or ""}
    if tool_calls:
        message["tool_calls"] = tool_calls
    if thinking:
        message["reasoning_content"] = thinking
    return message


def _reload_prompt(config: AppConfig, memory: MemoryStore) -> str:
    import vertex_agent.prompts as prompts

    try:
        importlib.reload(prompts)
    except SyntaxError as exc:
        raise ModelError(f"提示词文件有语法错误，请先回滚：{exc}") from exc
    return prompts.agent_prompt(str(config.workspace), memory.summary(), config.self_edit)


def _calls_from_turn(turn: dict) -> list[dict]:
    native = _normalize_calls(turn.get("tool_calls") or [])
    if native:
        return native
    text_calls = []
    content = turn.get("content") or ""
    cursor = 0
    while True:
        start = content.find("<tool_call>", cursor)
        if start < 0:
            break
        end = content.find("</tool_call>", start)
        if end < 0:
            break
        blob = content[start + len("<tool_call>") : end].strip()
        cursor = end + len("</tool_call>")
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("name"):
            text_calls.append(
                {
                    "id": f"call_text_{len(text_calls)}",
                    "function": {"name": obj["name"], "arguments": obj.get("arguments") or {}},
                }
            )
    return _normalize_calls(text_calls)


def _normalize_calls(raw_calls: list[dict]) -> list[dict]:
    calls = []
    for index, call in enumerate(raw_calls):
        function = call.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        calls.append(
            {
                "id": call.get("id") or f"call_{index}",
                "name": name,
                "arguments": function.get("arguments") if function.get("arguments") is not None else {},
                "raw": call,
            }
        )
    return calls


def _arguments(value) -> dict:
    if isinstance(value, str):
        if not value.strip():
            return {}
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def _progress(name: str, arguments: dict, done: bool = False) -> str:
    path = ""
    if isinstance(arguments, dict):
        path = str(arguments.get("path") or "")
    labels = {
        "list_files": ("正在查看文件", "已查看文件"),
        "read_file": ("正在读取", "已读取"),
        "search_code": ("正在搜索", "已搜索"),
        "apply_edit": ("正在写入", "已写入"),
        "run_code": ("正在运行", "已运行"),
        "verify_code": ("正在验证", "已验证"),
        "validate_agent": ("正在检查", "已检查"),
        "remember": ("正在记录", "已记录"),
        "recall": ("正在回忆", "已回忆"),
    }
    doing, finished = labels.get(name, ("正在处理", "已处理"))
    text = finished if done else doing
    return f"{text} {path}".strip()


def _preview(arguments: dict) -> dict:
    shown = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 500:
            shown[key] = value[:500] + "..."
        else:
            shown[key] = value
    return shown


def _parse_output(output: str) -> dict:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "error": output}
    if isinstance(parsed, dict):
        return parsed
    return {"ok": False, "error": output}


def _clip(messages: list[dict]) -> list[dict]:
    window = messages[-30:]
    last_image = -1
    for index, message in enumerate(window):
        if message.get("role") == "user" and message.get("images"):
            last_image = index
    clipped = []
    for index, message in enumerate(window):
        item = dict(message)
        if item.get("images") and index != last_image:
            item.pop("images", None)
        content = item.get("content") or ""
        if item.get("role") == "tool" and len(content) > 4000:
            item["content"] = content[:4000] + "\n...[已截断]"
        clipped.append(item)
    return clipped


def _slim(message: dict) -> dict:
    item = {key: value for key, value in message.items() if key != "raw"}
    content = item.get("content") or ""
    if item.get("role") == "tool" and len(content) > 6000:
        item["content"] = content[:6000] + "\n...[已截断]"
    return item


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
