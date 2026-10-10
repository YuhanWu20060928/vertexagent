# VertexAgent

本机编程智能体。擅长 C、Python、MATLAB，也能做普通问答。服务、记忆和代码都在这台电脑上。

## 启动

先确认 Ollama 已打开，然后在这个目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

浏览器打开 http://127.0.0.1:8765

## 模型

方案里的 DeepSeek V4.1-Flash 大约 763B 参数，这台电脑装不下完整权重。Ollama 里的 `deepseek-v4.1-flash:cloud` 当前返回 402，账号没有开通。

问答和写代码都使用页面上当前选中的模型。还没选过时，回退到 `config.yaml` 里的 `qwen2.5:7b`。DeepSeek V4.1 Flash 需要在本机设置里注册 API Key，然后在模型列表中选择它。

## 自主改代码

- **改工作区**：直接修改 `workspace` 里的文件，并用 Python、GCC 或 MATLAB 做验证。
- **改自身代码**：修改 VertexAgent 自己的源码。每次修改会备份到 `data/backups`。Python 语法错误会自动回滚。除 `prompts.py` 外，Python 改动需要点「重启服务」后生效。
- 工作区不能设成 VertexAgent 自己的程序目录，避免项目改动和自身改动混在一起。

## 局域网

服务监听 `0.0.0.0:8765`。同一局域网的电脑用「本机 IP:8765」访问。若连不上，用管理员 PowerShell 运行 `open-firewall.ps1`。这个端口没有登录验证，只适合可信网络。

## 接到 Cursor

在 Cursor 的 OpenAI 兼容设置里：

- Base URL：`http://127.0.0.1:8765/v1`
- 模型名：`vertex-agent`

这条通道会带上 VertexAgent 的编程提示词。要让智能体自己改文件，请用上面的网页。
