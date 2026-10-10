const state = {
  sessionId: null,
  filePath: "",
  editorPath: "",
  scope: "agent",
  sending: false,
  images: [],
  otherModel: "",
  allModels: [],
  tone: "code",
};

const chat = document.querySelector("#chat");
const input = document.querySelector("#input");
const modelSelect = document.querySelector("#model");
const sessionList = document.querySelector("#session-list");
const fileList = document.querySelector("#file-list");
const editList = document.querySelector("#edit-list");
const preview = document.querySelector("#preview");
const status = document.querySelector("#status");
const modeHint = document.querySelector("#mode-hint");

const hints = {
  ask: "直接提问。",
  create: "写明体裁、对象和篇幅。",
  code: "代码只支持 Python、C、C++。生成后可放入工作区，用 Python、gcc 或 g++ 编译运行。",
  translate: "把外文译成简体中文。学术论文请在消息里说明。",
  self: "只改被点名的源码。",
};

function esc(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

const LANG_LABEL = {
  c: "C", cpp: "C++", "c++": "C++", h: "C", python: "Python", py: "Python",
  js: "JavaScript", json: "JSON",
};

function codeLanguage(info, body) {
  const name = String(info || "").trim().split(/\s+/)[0].toLowerCase();
  if (name === "c++") return "cpp";
  if (name === "py") return "python";
  if (name === "h") return "c";
  if (LANG_LABEL[name]) return name;
  if (/^\s*#include\s*[<"]iostream/m.test(body) || /\bstd::/.test(body) || /\busing\s+namespace\s+std\b/.test(body)) return "cpp";
  if (/^\s*#include\b/m.test(body) || /\bint\s+main\s*\(/.test(body)) return "c";
  if (/^\s*(def|import|class)\s/m.test(body)) return "python";
  return "text";
}

function highlight(code, lang) {
  const words = {
    c: "auto|break|case|char|const|continue|default|do|double|else|enum|extern|float|for|goto|if|inline|int|long|register|return|short|signed|sizeof|static|struct|switch|typedef|union|unsigned|void|volatile|while",
    cpp: "auto|break|case|catch|char|class|const|continue|default|delete|do|double|else|enum|explicit|extern|float|for|friend|goto|if|inline|int|long|namespace|new|operator|private|protected|public|return|short|signed|sizeof|static|struct|switch|template|this|throw|try|typedef|typename|union|unsigned|using|virtual|void|volatile|while",
    python: "False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield",
    matlab: "break|case|catch|classdef|continue|else|elseif|end|for|function|global|if|otherwise|parfor|persistent|return|switch|try|while|true|false",
  };
  const stash = [];
  const keep = (kind, text) => {
    const token = `%%TOK${stash.length}%%`;
    stash.push(`<span class="tok-${kind}">${text}</span>`);
    return token;
  };
  let html = esc(code).replace(/\r\n/g, "\n");
  html = html.replace(/(&quot;(?:\\.|[^&])*?&quot;|&#39;(?:\\.|[^&])*?&#39;)/g, (item) => keep("string", item));
  if (lang === "python") html = html.replace(/(#.*)$/gm, (item) => keep("comment", item));
  else if (lang === "matlab" || lang === "m") html = html.replace(/(%.*)$/gm, (item) => keep("comment", item));
  else if (lang !== "text") {
    html = html.replace(/\/\*[\s\S]*?\*\//g, (item) => keep("comment", item));
    html = html.replace(/(\/\/.*)$/gm, (item) => keep("comment", item));
    html = html.replace(/(^#\s*[a-zA-Z_]\w*)/gm, (item) => keep("pre", item));
  }
  const keys = words[lang] || words[lang === "m" ? "matlab" : "c"];
  if (words[lang] || lang === "m" || lang === "cpp" || lang === "h") {
    html = html.replace(new RegExp(`\\b(${keys})\\b`, "g"), (item) => keep("key", item));
  }
  html = html.replace(/\b([A-Za-z_]\w*)(?=\s*\()/g, (item) => keep("fn", item));
  html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, (item) => keep("num", item));
  return html.replace(/%%TOK(\d+)%%/g, (_, index) => stash[Number(index)]);
}

function codeCard(info, body) {
  const lang = codeLanguage(info, body);
  const label = LANG_LABEL[lang] || (info || "代码");
  return `<div class="code-card">
    <div class="code-bar">
      <span class="code-lang">${esc(label)}<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></span>
      <button type="button" class="copy-code" title="复制代码" aria-label="复制代码">
        <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.2" y="2.2" width="8" height="9.2" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.3"/><rect x="2.6" y="4.6" width="8" height="9.2" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>
        <span>复制</span>
      </button>
    </div>
    <pre><code>${highlight(body.replace(/\n$/, ""), lang)}</code></pre>
  </div>`;
}

function renderText(raw) {
  const chunks = String(raw || "").split("```");
  return chunks.map((chunk, index) => {
    if (index % 2 === 0) return esc(chunk);
    const breakAt = chunk.indexOf("\n");
    const info = breakAt >= 0 ? chunk.slice(0, breakAt) : "";
    const body = breakAt >= 0 ? chunk.slice(breakAt + 1) : chunk;
    return codeCard(info, body);
  }).join("");
}

function emptyState() {
  chat.innerHTML = `<div class="empty">
    <div class="hello">
      <span class="logo" aria-hidden="true"><svg viewBox="0 0 32 32"><defs><linearGradient id="g2" x1="4" y1="2" x2="28" y2="30"><stop stop-color="#5ad7ff"/><stop offset=".45" stop-color="#6a7bff"/><stop offset="1" stop-color="#ffb15a"/></linearGradient></defs><path fill="url(#g2)" d="M16 3c2.2 5.2 5.6 8.4 11 10.2-5.4 1.6-8.8 5-10.6 10.4C14.6 18.2 11.2 14.8 6 13.2 11.4 11.4 14.8 8.2 16 3z"/></svg></span>
      <h1>你好，我是 VertexAgent</h1>
    </div>
    <p class="sub">写 Python、C、C++，或让我直接改工作区里的文件。</p>
    <div class="chips">
      <button type="button" class="chip" data-prompt="把 hello.py 的问候改成中文并运行">把问候改成中文并运行</button>
      <button type="button" class="chip" data-prompt="写一个 C 语言单链表，编译并运行">写一个 C 语言单链表</button>
      <button type="button" class="chip" data-prompt="写一个 C++ 程序，判断一个整数是不是质数，编译并运行">写一个 C++ 质数判断</button>
    </div>
  </div>`;
}

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

const MATLAB_MODEL = "matlab-r2024b:latest";

function isMatlabModel(name) {
  return String(name || "").trim().toLowerCase().replace(/:latest$/, "") === "matlab-r2024b";
}

function matlabCompileOn() {
  return currentMode() === "workspace" && document.querySelector("#language").value === "matlab";
}

function isPageModel(name) {
  const base = String(name || "").trim().toLowerCase().replace(/:latest$/, "");
  return base === "deepseek-flash" || base === "deepseek-v4.1-flash" || base === "deepseek-v4-flash" || base === "deepseek-v4-pro" || base === "deepseek-v4.1-pro" || base === "deepseek-pro" || base === "qwen3.5" || base.startsWith("qwen3.5:");
}

function renderModelChoices(preferred) {
  const items = state.allModels.filter((item) => isPageModel(item.name));
  const current = preferred || modelSelect.value;
  modelSelect.disabled = false;
  modelSelect.innerHTML = items.map((item) => `<option value="${esc(item.name)}">${esc(item.label || item.name)}</option>`).join("");
  if (current && items.some((item) => item.name === current)) modelSelect.value = current;
  else if (items[0]) modelSelect.value = items[0].name;
  const label = document.querySelector("#model-label");
  if (label && modelSelect.selectedOptions[0]) label.textContent = modelSelect.selectedOptions[0].textContent;
}

function applyTone(tone) {
  state.tone = tone || "ask";
  const pill = document.querySelector("#language-pill");
  if (pill) pill.classList.toggle("hidden", state.tone !== "code");
  if (modeHint) modeHint.textContent = hints[state.tone] || hints.ask;
}

async function persistModel() {
  const body = { model: modelSelect.value };
  if (!matlabCompileOn() && modelSelect.value && !isMatlabModel(modelSelect.value)) {
    state.otherModel = modelSelect.value;
    body.general_model = modelSelect.value;
  }
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function applyLanguageModel() {
  if (modelSelect.value && !isMatlabModel(modelSelect.value)) state.otherModel = modelSelect.value;
  renderModelChoices();
  await persistModel();
}

function startTurn(text, images) {
  if (!chat.querySelector(".turn")) chat.innerHTML = "";
  const shots = (images || []).map((url) => `<img src="${esc(url)}" alt="">`).join("");
  const turn = document.createElement("article");
  turn.className = "turn";
  turn.innerHTML = `<div class="user">${shots ? `<div class="shots">${shots}</div>` : ""}<div class="bubble">${esc(text)}</div></div><div class="assistant"></div>`;
  chat.appendChild(turn);
  chat.scrollTop = chat.scrollHeight;
  return turn.querySelector(".assistant");
}

function assistantBubble(box) {
  let bubble = box.querySelector(":scope > .bubble");
  if (!bubble) {
    bubble = document.createElement("div");
    bubble.className = "bubble";
    box.appendChild(bubble);
  }
  return bubble;
}

function addTool(box, name, phase, payload) {
  let card = box.querySelector(`[data-tool="${CSS.escape(name)}"]:last-of-type`);
  if (phase === "start" || !card) {
    card = document.createElement("details");
    card.className = "tool";
    card.open = true;
    card.dataset.tool = name;
    card.innerHTML = `<summary>${esc(name)}</summary><pre></pre>`;
    box.appendChild(card);
  }
  const pre = card.querySelector("pre");
  if (phase === "start") {
    pre.textContent = JSON.stringify(payload, null, 2);
  } else {
    const diff = payload && payload.diff ? `\n\n${payload.diff}` : "";
    const brief = { ...payload };
    if (brief.diff && String(brief.diff).length > 1200) brief.diff = `${String(brief.diff).slice(0, 1200)}\n...`;
    pre.textContent = JSON.stringify(brief, null, 2) + diff;
  }
  chat.scrollTop = chat.scrollHeight;
}

async function refreshHealth() {
  const response = await fetch("/api/health");
  const data = await response.json();
  const lan = (data.lan || []).join("  ") || "仅本机";
  const tools = `Python 可用 · GCC ${data.gcc ? "可用" : "未找到"}`;
  status.textContent = `${data.ollama ? "Ollama 已连接" : "Ollama 未连接"} · ${data.model} · ${lan} · ${tools}`;
  document.querySelector("#workspace").value = data.workspace || "";
  const py = document.querySelector("#py-label");
  if (py) py.textContent = data.python ? `Python ${data.python}` : "Python";
  const sync = document.querySelector("#sync-url");
  if (sync) sync.value = data.local || location.origin;
  return data;
}

async function refreshModels(active) {
  const response = await fetch("/api/models");
  if (!response.ok) {
    modelSelect.innerHTML = `<option>${esc(active || "未连接")}</option>`;
    return;
  }
  const data = await response.json();
  const items = (data.models || []).map((item) => (typeof item === "string" ? { name: item, label: item } : item)).filter((item) => isPageModel(item.name));
  state.allModels = items;
  if (active) state.otherModel = active;
  renderModelChoices(data.active || active);
}

async function refreshKey() {
  const response = await fetch("/api/deepseek");
  if (!response.ok) return;
  const data = await response.json();
  const status = document.querySelector("#key-status");
  if (!status) return;
  status.textContent = data.registered
    ? `已注册 ${data.hint}。在模型列表里选择 DeepSeek V4.1 Flash 后才会用它。`
    : "尚未注册。Key 只保存在这台电脑，请用 127.0.0.1 打开本页。";
}

async function refreshSessions() {
  const response = await fetch("/api/sessions");
  const data = await response.json();
  sessionList.innerHTML = "";
  for (const session of data.sessions || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item${session.id === state.sessionId ? " active" : ""}`;
    button.innerHTML = `${esc(session.title)}<small>${esc(session.updated || "")}</small>`;
    button.addEventListener("click", () => openSession(session.id));
    sessionList.appendChild(button);
  }
}

async function openSession(id) {
  const response = await fetch(`/api/sessions/${id}`);
  if (!response.ok) return;
  const data = await response.json();
  state.sessionId = id;
  chat.innerHTML = "";
  let box = null;
  for (const message of data.messages || []) {
    if (message.role === "user") {
      box = startTurn(message.content || "", message.images || []);
    } else if (message.role === "assistant" && box && message.content && !message.tool_calls) {
      assistantBubble(box).innerHTML = renderText(message.content);
    }
  }
  if (!data.messages || !data.messages.length) emptyState();
  refreshSessions();
}

async function refreshFiles() {
  const response = await fetch(`/api/files?scope=${state.scope}&path=${encodeURIComponent(state.filePath)}`);
  const data = await response.json();
  document.querySelector("#file-path").textContent = state.filePath || (state.scope === "agent" ? "系统源码" : "/");
  fileList.innerHTML = "";
  if (!data.ok) {
    fileList.textContent = data.error || "无法读取";
    return;
  }
  for (const entry of data.entries || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-row";
    button.textContent = `${entry.type === "dir" ? "▸ " : ""}${entry.name}`;
    button.addEventListener("click", () => {
      const next = state.filePath ? `${state.filePath}/${entry.name}` : entry.name;
      if (entry.type === "dir") {
        state.filePath = next;
        refreshFiles();
      } else {
        openEditor(next);
      }
    });
    fileList.appendChild(button);
  }
}

function paintGutter() {
  const editor = document.querySelector("#editor");
  const lines = editor.value.split("\n").length || 1;
  document.querySelector("#gutter").textContent = Array.from({ length: lines }, (_, index) => index + 1).join("\n");
  const point = editor.value.slice(0, editor.selectionStart).split("\n");
  document.querySelector("#caret").textContent = `行 ${point.length}，列 ${point[point.length - 1].length + 1}`;
}

function showRun(data) {
  const ok = data.ok !== false && !data.error;
  document.querySelector("#run-command").textContent = data.command || "已完成";
  const log = [data.stdout, data.stderr].filter(Boolean).join("\n");
  document.querySelector("#run-diagnosis").textContent = data.diagnosis || data.error || (ok ? "通过" : (data.stderr || "未通过"));
  document.querySelector("#run-output").textContent = log || data.message || "";
}

async function openEditor(path) {
  const response = await fetch(`/api/source/raw?scope=${state.scope}&path=${encodeURIComponent(path)}`);
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    showRun({ ok: false, error: data.detail || data.error || "无法打开" });
    return;
  }
  state.editorPath = path;
  document.querySelector("#editor").value = data.content || "";
  document.querySelector("#editor-name").textContent = path;
  const ext = path.split(".").pop();
  document.querySelector("#editor-lang").textContent = { py: "Python", c: "C", cpp: "C++", cc: "C++", m: "MATLAB", swb: "SolidWorks", js: "JavaScript", css: "CSS", html: "HTML", md: "Markdown" }[ext] || "文本";
  paintGutter();
}

async function saveEditor() {
  if (!state.editorPath) {
    alert("先从左侧打开一个文件。");
    return null;
  }
  const response = await fetch("/api/source/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope: state.scope,
      path: state.editorPath,
      content: document.querySelector("#editor").value,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    showRun({ ok: false, error: data.detail || data.error || "保存失败" });
    return null;
  }
  showRun({ ok: true, command: `保存 ${data.path || state.editorPath}`, message: data.message || "已保存", stdout: data.diff || "" });
  if (data.restart_required) document.querySelector("#restart-banner").classList.remove("hidden");
  return data;
}

async function runAction(action) {
  const path = state.editorPath || "";
  if (/\.(m|swb)$/i.test(path)) {
    showRun({ ok: false, error: "代码编程仅支持 Python、C 和 C++。" });
    return;
  }
  const saved = await saveEditor();
  if (!saved) return;
  const args = document.querySelector("#run-args").value.trim().split(/\s+/).filter(Boolean);
  const response = await fetch("/api/source/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope: state.scope, path: state.editorPath, action, args }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showRun({ ok: false, error: data.detail || "失败" });
    return;
  }
  showRun(data);
}

function setScope(scope) {
  state.scope = scope;
  state.filePath = "";
  document.querySelector("#scope-agent").classList.toggle("on", scope === "agent");
  document.querySelector("#scope-workspace").classList.toggle("on", scope === "workspace");
  document.querySelector("#scope-label").textContent = scope === "agent"
    ? "可改系统源码。编译、调试、运行前可以填运行参数。"
    : "工作区源码。Python 直接运行，C/C++ 用 gcc、g++。";
  refreshFiles();
}

async function openPreview(path) {
  const response = await fetch(`/api/file?scope=workspace&path=${encodeURIComponent(path)}`);
  const data = await response.json();
  document.querySelector('[data-tab="preview"]').click();
  preview.textContent = data.ok ? data.content : (data.error || "无法读取");
}

async function refreshEdits() {
  const response = await fetch("/api/self-edits");
  const data = await response.json();
  editList.innerHTML = "";
  const edits = (data.edits || []).filter((item) => item.scope === "agent");
  if (!edits.length) {
    editList.innerHTML = `<div class="note">还没有修改过自身代码。</div>`;
    return;
  }
  for (const edit of edits) {
    const card = document.createElement("article");
    card.className = "edit-card";
    const flag = edit.ok ? `<span class="ok">成功</span>` : `<span class="bad">失败</span>`;
    card.innerHTML = `<header><strong>${esc(edit.path || "")}</strong>${flag}</header><small class="muted">${esc(edit.time || "")} · ${esc(edit.reason || "")}</small><pre>${esc(edit.diff || edit.error || "")}</pre>`;
    if (edit.ok && edit.kind !== "rollback" && edit.backup) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "回滚这次修改";
      button.addEventListener("click", async () => {
        const result = await fetch(`/api/self-edits/${edit.id}/rollback`, { method: "POST" });
        const body = await result.json();
        if (!result.ok) alert(body.detail || "回滚失败");
        refreshEdits();
      });
      card.appendChild(button);
    }
    editList.appendChild(card);
  }
}

function showTab(name) {
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const body of document.querySelectorAll(".tab-body")) body.classList.add("hidden");
  document.querySelector(`#tab-${name}`).classList.remove("hidden");
}

function renderImageStrip() {
  const strip = document.querySelector("#image-strip");
  if (!strip) return;
  strip.innerHTML = state.images.map((item, index) => `<button type="button" data-image="${index}"><img src="${esc(item.url)}" alt=""><span>×</span></button>`).join("");
}

function addImageFile(file) {
  if (!file || !file.type.startsWith("image/") || state.images.length >= 4) return;
  const reader = new FileReader();
  reader.onload = () => {
    state.images.push({ name: file.name, url: String(reader.result || "") });
    renderImageStrip();
  };
  reader.readAsDataURL(file);
}

async function sendMessage(event) {
  event.preventDefault();
  const raw = input.value.trim();
  const images = state.images.map((item) => item.url);
  if ((!raw && !images.length) || state.sending) return;
  const language = document.querySelector("#language");
  const names = { python: "Python", c: "C", cpp: "C++" };
  const text = raw || "请看这张图片。";
  const message = currentMode() === "workspace" && language
    ? `代码语言：${names[language.value] || language.value}\n${text}`
    : text;
  state.sending = true;
  document.querySelector("#send").disabled = true;
  const box = startTurn(message, images);
  input.value = "";
  state.images = [];
  renderImageStrip();
  let sawToken = false;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: state.sessionId,
        mode: currentMode(),
        think: document.querySelector("#think").checked,
        images,
        language: document.querySelector("#language").value,
        model: modelSelect.value,
      }),
    });
    if (!response.ok || !response.body) {
      const failure = await response.json().catch(() => ({}));
      box.innerHTML = `<div class="error">${esc(failure.detail || "请求失败")}</div>`;
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.type === "session") state.sessionId = payload.session_id;
        if (payload.type === "progress") {
          let line = box.querySelector(".progress");
          if (!payload.text) {
            if (line) line.remove();
          } else {
            if (!line) {
              line = document.createElement("p");
              line.className = "progress";
              box.appendChild(line);
            }
            line.textContent = payload.text;
          }
        }
        if (payload.type === "reset") {
          const bubble = box.querySelector(":scope > .bubble");
          if (bubble) {
            bubble.dataset.raw = "";
            bubble.innerHTML = "";
          }
        }
        if (payload.type === "thinking") {
          let thought = box.querySelector(".thinking");
          if (!thought) {
            thought = document.createElement("details");
            thought.className = "thinking";
            thought.open = true;
            thought.innerHTML = `<summary>正在思考</summary><p class="trace"></p>`;
            box.prepend(thought);
          }
          thought.querySelector(".trace").textContent += payload.text;
        }
        if (payload.type === "token") {
          sawToken = true;
          const bubble = assistantBubble(box);
          bubble.dataset.raw = (bubble.dataset.raw || "") + payload.text;
          bubble.innerHTML = renderText(bubble.dataset.raw);
        }
        if (payload.type === "tool" && payload.result && payload.result.restart_required) {
          document.querySelector("#restart-banner").classList.remove("hidden");
        }
        if (payload.type === "error") {
          const note = document.createElement("div");
          note.className = "error";
          note.textContent = payload.message;
          box.appendChild(note);
        }
        if (payload.type === "done") box.querySelector(".progress")?.remove();
        if (payload.type === "done" && payload.restart_required) {
          document.querySelector("#restart-banner").classList.remove("hidden");
          document.querySelector("#view-admin").classList.add("active");
          document.querySelector("#view-chat").classList.remove("active");
          showTab("edits");
        }
        chat.scrollTop = chat.scrollHeight;
      }
    }
    if (!sawToken && !box.querySelector(".error") && !box.querySelector(".tool") && !box.querySelector(".thinking")) {
      assistantBubble(box).textContent = "模型没有返回文字。可以换一个模型，或把任务再说具体一点。";
    }
  } catch (error) {
    box.innerHTML = `<div class="error">${esc(error.message || error)}</div>`;
  } finally {
    state.sending = false;
    document.querySelector("#send").disabled = false;
    refreshSessions();
    refreshFiles();
    refreshEdits();
  }
}

chat.addEventListener("click", async (event) => {
  const chip = event.target.closest(".chip");
  if (chip) {
    input.value = chip.dataset.prompt || chip.textContent;
    input.focus();
    return;
  }
  const button = event.target.closest(".copy-code");
  if (!button) return;
  const code = button.closest(".code-card").querySelector("code").textContent;
  try {
    await navigator.clipboard.writeText(code);
  } catch {
    const area = document.createElement("textarea");
    area.value = code;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const label = button.querySelector("span");
  label.textContent = "已复制";
  button.classList.add("copied");
  setTimeout(() => {
    label.textContent = "复制";
    button.classList.remove("copied");
  }, 1400);
});
document.querySelector("#composer").addEventListener("submit", sendMessage);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    document.querySelector("#composer").requestSubmit();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.altKey && !event.ctrlKey && !event.metaKey && event.key.toLowerCase() === "a") {
    event.preventDefault();
    document.querySelector("#image-input").click();
  }
});
document.querySelector("#image-input").addEventListener("change", (event) => {
  for (const file of event.target.files || []) addImageFile(file);
  event.target.value = "";
});
document.querySelector("#import-file").addEventListener("click", () => document.querySelector("#import-input").click());
document.querySelector("#import-input").addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (file.size > 16 * 1024 * 1024) {
    alert("单个文件不要超过 16MB。旧版 doc、ppt 请先另存为 docx、pptx。");
    return;
  }
  if (file.type.startsWith("image/")) {
    addImageFile(file);
    return;
  }
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (["pdf", "docx", "pptx"].includes(ext)) {
    const body = new FormData();
    body.append("file", file);
    fetch("/api/import", { method: "POST", body })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "读不出来");
        input.value = `${input.value}${input.value ? "\n" : ""}${data.text || ""}`.slice(0, 20000);
        input.focus();
      })
      .catch((error) => alert(error.message || "这个文件读不出来"));
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    input.value = `${input.value}${input.value ? "\n" : ""}${reader.result || ""}`.slice(0, 20000);
    input.focus();
  };
  reader.readAsText(file);
});
document.querySelector("#image-strip").addEventListener("click", (event) => {
  const button = event.target.closest("[data-image]");
  if (!button) return;
  state.images.splice(Number(button.dataset.image), 1);
  renderImageStrip();
});
input.addEventListener("paste", (event) => {
  const files = [...(event.clipboardData?.files || [])].filter((file) => file.type.startsWith("image/"));
  if (!files.length) return;
  event.preventDefault();
  files.forEach(addImageFile);
});
document.querySelector("#new-chat").addEventListener("click", () => {
  state.sessionId = null;
  state.images = [];
  renderImageStrip();
  emptyState();
  refreshSessions();
});
document.querySelector("#clear-turn").addEventListener("click", () => document.querySelector("#new-chat").click());
document.querySelector("#code-to-workspace").addEventListener("click", async () => {
  const card = [...document.querySelectorAll(".code-card")].pop();
  if (!card) {
    alert("这轮对话里还没有代码块。");
    return;
  }
  const code = card.querySelector("code").textContent;
  const label = card.querySelector(".code-lang").textContent;
  const ext = label.includes("Python") ? "py" : label.includes("C++") ? "cpp" : "c";
  const path = `snippet.${ext}`;
  const response = await fetch("/api/workspace/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content: code.endsWith("\n") ? code : `${code}\n` }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) alert(data.detail || "保存失败");
  else alert(`已写入工作区 ${path}`);
});
document.querySelector("#copy-url").addEventListener("click", async () => {
  const url = document.querySelector("#sync-url").value;
  try { await navigator.clipboard.writeText(url); } catch { /* 浏览器未授权剪贴板时忽略 */ }
});
document.querySelector("#language").addEventListener("change", () => applyLanguageModel());
modelSelect.addEventListener("change", async () => {
  if (!isMatlabModel(modelSelect.value)) state.otherModel = modelSelect.value;
  await persistModel();
  refreshHealth();
});
document.querySelector("#apply-workspace").addEventListener("click", async () => {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace: document.querySelector("#workspace").value }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "工作区无效");
    return;
  }
  state.filePath = "";
  refreshHealth();
  refreshFiles();
});
document.querySelector("#file-up").addEventListener("click", () => {
  const parts = state.filePath.split("/").filter(Boolean);
  parts.pop();
  state.filePath = parts.join("/");
  refreshFiles();
});
document.querySelector("#scope-agent").addEventListener("click", () => setScope("agent"));
document.querySelector("#scope-workspace").addEventListener("click", () => setScope("workspace"));
document.querySelector("#editor").addEventListener("input", paintGutter);
document.querySelector("#editor").addEventListener("keyup", paintGutter);
document.querySelector("#editor").addEventListener("click", paintGutter);
document.querySelector("#editor").addEventListener("scroll", () => {
  document.querySelector("#gutter").scrollTop = document.querySelector("#editor").scrollTop;
});
document.querySelector("#file-save").addEventListener("click", saveEditor);
document.querySelector("#file-reload").addEventListener("click", () => {
  if (state.editorPath) openEditor(state.editorPath);
});
document.querySelector("#file-new").addEventListener("click", () => {
  const hint = state.scope === "agent" ? "vertex_agent/新文件.py" : "hello.py";
  const name = window.prompt("新建文件的相对路径", hint);
  if (!name) return;
  state.editorPath = name.trim();
  document.querySelector("#editor").value = "";
  document.querySelector("#editor-name").textContent = state.editorPath;
  paintGutter();
});
document.querySelector("#file-compile").addEventListener("click", () => runAction("compile"));
document.querySelector("#file-debug").addEventListener("click", () => runAction("debug"));
document.querySelector("#file-run").addEventListener("click", () => runAction("run"));
document.querySelector("#file-verify").addEventListener("click", () => runAction("verify"));
document.querySelector("#publish-version").addEventListener("click", async () => {
  const note = window.prompt("版本说明", "");
  if (!note) return;
  const response = await fetch("/api/source/publish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) showRun({ ok: false, error: data.detail || "发布失败" });
  else showRun(data);
});
async function askDebug() {
  if (state.scope === "agent" && state.editorPath) await saveEditor();
  const diagnosis = document.querySelector("#run-diagnosis").textContent;
  const output = document.querySelector("#run-output").textContent;
  const path = state.editorPath || "当前打开的系统文件";
  const radio = document.querySelector('input[name="mode"][value="self"]');
  radio.checked = true;
  radio.dispatchEvent(new Event("change"));
  document.querySelector("#think").checked = true;
  showView("chat");
  for (const item of document.querySelectorAll(".nav button")) item.classList.remove("on");
  input.value = state.scope === "agent"
    ? `请调试系统源码 ${path}。先 read_file，再按报错 apply_edit，最后 validate_agent。\n诊断：${diagnosis}\n输出：${output.slice(0, 2000)}`
    : `请根据编译结果修复工作区文件 ${path}。\n诊断：${diagnosis}\n输出：${output.slice(0, 2000)}`;
  document.querySelector("#composer").requestSubmit();
}
document.querySelector("#sync-chat").addEventListener("click", askDebug)
document.querySelector("#restart").addEventListener("click", async () => {
  await fetch("/api/restart", { method: "POST" });
  status.textContent = "正在重启，请稍等几秒后刷新。";
  setTimeout(() => location.reload(), 2500);
});
for (const button of document.querySelectorAll(".tab")) {
  button.addEventListener("click", () => showTab(button.dataset.tab));
}
for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.addEventListener("change", () => {
    if (currentMode() === "self") modeHint.textContent = hints.self;
  });
}
function showView(name) {
  for (const view of document.querySelectorAll(".view")) {
    view.classList.toggle("active", view.id === `view-${name}`);
  }
}
for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => {
    showView(button.dataset.view);
    if (button.closest(".nav")) {
      for (const item of document.querySelectorAll(".nav button")) item.classList.toggle("on", item === button);
    }
    if (button.dataset.mode) {
      const radio = document.querySelector(`input[name="mode"][value="${button.dataset.mode}"]`);
      if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event("change"));
      }
      const think = document.querySelector("#think");
      if (think) think.checked = button.dataset.mode === "workspace";
    }
    if (button.dataset.tone) applyTone(button.dataset.tone);
  });
}
modelSelect.addEventListener("change", () => {
  const label = document.querySelector("#model-label");
  if (label && modelSelect.selectedOptions[0]) label.textContent = modelSelect.selectedOptions[0].textContent;
});
document.querySelector("#save-key").addEventListener("click", async () => {
  const button = document.querySelector("#save-key");
  const apiKey = document.querySelector("#api-key").value.trim();
  button.disabled = true;
  button.textContent = "正在校验…";
  try {
    const response = await fetch("/api/deepseek", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await response.json();
    if (!response.ok) {
      alert(data.detail || "注册失败");
      return;
    }
    document.querySelector("#api-key").value = "";
    await refreshKey();
    await refreshModels(data.model);
    refreshHealth();
  } finally {
    button.disabled = false;
    button.textContent = "注册到本机";
  }
});
document.querySelector("#clear-key").addEventListener("click", async () => {
  const response = await fetch("/api/deepseek", { method: "DELETE" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "清除失败");
    return;
  }
  await refreshKey();
  await refreshModels(data.model);
  refreshHealth();
});

emptyState();
refreshHealth().then((data) => {
  if (data.general_model && !isMatlabModel(data.general_model)) state.otherModel = data.general_model;
  return refreshModels(data.model);
}).catch(() => {
  status.textContent = "页面没有连上 VertexAgent 服务。";
});
refreshKey();
refreshSessions();
refreshFiles();
refreshEdits();
