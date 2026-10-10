from __future__ import annotations

import uvicorn

from vertex_agent import __version__
from vertex_agent.config import load_config
from vertex_agent.server import lan_urls


def main() -> None:
    config = load_config()
    config.workspace.mkdir(parents=True, exist_ok=True)
    urls = "  ".join(lan_urls(config.port)) or "（没有发现局域网地址）"
    print(f"VertexAgent {__version__}")
    print(f"本机    http://127.0.0.1:{config.port}")
    print(f"局域网  {urls}")
    print(f"模型    {config.model}")
    print(f"工作区  {config.workspace}")
    print(f"自主改码 {'开启' if config.self_edit else '关闭'}")
    print("Cursor 可把 OpenAI Base URL 设为 " + f"http://127.0.0.1:{config.port}/v1 ，模型名 vertex-agent")
    uvicorn.run("vertex_agent.server:app", host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
