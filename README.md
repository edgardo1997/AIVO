<div align="center">
  <h1>◇ AIVO</h1>
  <p><strong>AI-Powered PC Control Panel</strong></p>
  <p>Monitor · Chat · Console · Files · Automation · Remote</p>
  <br/>
  <p>
    <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12"/>
    <img src="https://img.shields.io/badge/rust-1.96-orange" alt="Rust"/>
    <img src="https://img.shields.io/badge/react-19-cyan" alt="React 19"/>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"/>
  </p>
  <br/>
</div>

---

## ✨ Features

| Module | Description |
|---|---|
| **Dashboard** | Real-time CPU/RAM/disk gauges, quick actions, AI analysis |
| **Monitor** | Detailed metrics: CPU per-core, RAM, disk, network, processes |
| **AI Chat** | Chat with AI about your PC — 10 providers (OpenAI, Anthropic, Ollama, etc.) |
| **Console** | Run shell commands with safety gates and permission system |
| **Files** | Browse, search, read, edit files on your system |
| **Audit Log** | Every action logged with timestamp and result |
| **Permissions** | 4 levels (View/Confirm/Auto/Admin) + Emergency Stop |
| **Plugins** | Extend AIVO with Python hooks (on_metrics, on_command, etc.) |
| **Fleet** | Remote access with token-based pairing and QR |
| **Settings** | AI provider config, provider switcher, API key tester |

## 🖥️ Screenshots

> *Coming soon*

## 🚀 Quick Start

### Prerequisites
- **Python** 3.12+
- **Node.js** 20+
- **Rust** 1.70+ (optional, for desktop app)

### One-Command Setup
```
setup.bat
```

### Manual Setup
```bash
# 1. Python environment
cd sidecar
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Node dependencies
cd ..
npm install

# 3. Start sidecar (terminal 1)
cd sidecar
.venv\Scripts\activate
uvicorn main:app --host 127.0.0.1 --port 8765 --reload

# 4. Start frontend (terminal 2)
npm run dev

# 5. Open browser
start http://localhost:5173
```

### Desktop App (Tauri)
```bash
npm run tauri:dev      # Development mode
npm run tauri:build    # Production installer
```

## 🏗️ Architecture

```
AIVO/
├── src/                    # React frontend
│   ├── components/         # UI components
│   ├── api.ts              # REST API client
│   ├── types.ts            # TypeScript types
│   └── index.css           # Dark theme
├── sidecar/                # Python backend
│   ├── main.py             # FastAPI server (port 8765)
│   ├── fleet_server.py     # Remote proxy server (port 8766)
│   ├── modules/            # Backend modules
│   │   ├── monitor.py      # System metrics (psutil)
│   │   ├── executor.py     # Shell command execution
│   │   ├── ai_provider.py  # AI chat (10 providers)
│   │   ├── filesystem.py   # File operations
│   │   ├── permissions.py  # Permission system
│   │   ├── audit.py        # Audit logging
│   │   ├── proactive.py    # Background health engine
│   │   ├── plugins.py      # Plugin system
│   │   ├── voice.py        # Text-to-speech
│   │   └── fleet.py        # Remote access
│   └── plugins/            # Built-in plugins
├── src-tauri/              # Tauri desktop shell
├── setup.bat               # One-click setup
└── package.json            # Frontend scripts
```

## 🧩 Plugin System

Plugins are Python scripts with hooks. Create one in `~/.aivo/plugins/`:

```json
// manifest.json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "hooks": ["on_metrics", "on_command"],
  "enabled": true
}
```

```python
# main.py
def on_metrics(ctx):
    print(f"CPU: {ctx.get('cpu_percent')}%")
    return {"custom_alert": cpu > 90}

def on_command(ctx):
    if "hello" in ctx.get("command", ""):
        return {"handled": True, "stdout": "Hello from plugin!"}
    return {"handled": False}
```

## 🔒 Safety

- **4 permission levels**: View (read-only), Confirm (prompt before dangerous), Auto (automatic), Admin (no restrictions)
- **Destructive pattern detection**: `rm`, `del`, `format`, `shutdown` and 10+ more patterns flagged
- **Emergency Stop**: Global kill switch for all command execution
- **Audit Trail**: Every action logged with timestamp, user, and result

## 🤖 AI Providers

| Provider | Tier | Default Model |
|---|---|---|
| OpenRouter | Free | `deepseek-v4-flash:free` |
| DeepSeek | Free | `deepseek-v4-flash` |
| Groq | Free | `llama-3.3-70b-versatile` |
| Gemini | Free | `gemini-2.5-flash` |
| GitHub Models | Free | `gpt-4o` |
| Cerebras | Free | `llama-3.3-70b` |
| Mistral | Free | `mistral-large-latest` |
| Ollama | Local | `llama3` |
| OpenAI | Paid | `gpt-4o` |
| Anthropic | Paid | `claude-sonnet-4` |

## 📄 API Docs

When the sidecar is running:
- **Swagger UI**: http://127.0.0.1:8765/docs
- **ReDoc**: http://127.0.0.1:8765/redoc
- **OpenAPI JSON**: http://127.0.0.1:8765/openapi.json

## 🧪 Testing

```bash
# Frontend tests
npm test

# Backend tests (requires sidecar running)
pytest sidecar/tests/ -v
```

## 🛠️ Tech Stack

**Frontend**: React 19, TypeScript 6, Vite 8, Tauri 2  
**Backend**: Python 3.12, FastAPI, psutil, OpenAI SDK  
**Desktop**: Rust, Tauri v2, WebView2  

## 📜 License

MIT
