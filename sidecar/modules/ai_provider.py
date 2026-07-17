import json
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

router = APIRouter()

CONFIG_FILE = os.path.expanduser("~/.aivo_config.json")

FREE_PROVIDERS = {
    "openrouter": {
        "label": "OpenRouter (28+ free models)",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_required": True,
        "default_model": "deepseek/deepseek-v4-flash:free",
        "description": "Single key, 28+ free models. No credit card.",
        "signup_url": "https://openrouter.ai/keys",
    },
    "deepseek": {
        "label": "DeepSeek V4 Flash (free tier)",
        "base_url": "https://api.deepseek.com",
        "api_key_required": True,
        "default_model": "deepseek-v4-flash",
        "description": "5M free tokens on signup. No credit card.",
        "signup_url": "https://platform.deepseek.com/",
    },
    "groq": {
        "label": "Groq (free tier)",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_required": True,
        "default_model": "llama-3.3-70b-versatile",
        "description": "Ultra-fast. 30 RPM free. No credit card.",
        "signup_url": "https://console.groq.com/",
    },
    "gemini": {
        "label": "Google Gemini (free tier)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openapi/",
        "api_key_required": True,
        "default_model": "gemini-2.5-flash",
        "description": "1500 req/day free. 1M context. No credit card.",
        "signup_url": "https://aistudio.google.com/",
    },
    "github": {
        "label": "GitHub Models (free)",
        "base_url": "https://models.github.ai/inference",
        "api_key_required": True,
        "default_model": "gpt-4o",
        "description": "GPT-4o, Grok-3 free. Needs GitHub account.",
        "signup_url": "https://github.com/marketplace/models",
    },
    "cerebras": {
        "label": "Cerebras (free tier)",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_required": True,
        "default_model": "llama-3.3-70b",
        "description": "Fastest inference. 1M tokens/day free.",
        "signup_url": "https://console.cerebras.ai/",
    },
    "mistral": {
        "label": "Mistral AI (free tier)",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_required": True,
        "default_model": "mistral-large-latest",
        "description": "1B tokens/month free. No credit card.",
        "signup_url": "https://console.mistral.ai/",
    },
    "openai": {
        "label": "OpenAI (paid)",
        "base_url": None,
        "api_key_required": True,
        "default_model": "gpt-4o",
        "description": "Best quality. Requires paid API key.",
        "signup_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic Claude (paid)",
        "base_url": None,
        "api_key_required": True,
        "default_model": "claude-sonnet-4-20250514",
        "description": "Excellent reasoning. Requires paid API key.",
        "signup_url": "https://console.anthropic.com/",
    },
    "ollama": {
        "label": "Ollama (local, free)",
        "base_url": "http://localhost:11434/v1",
        "api_key_required": False,
        "default_model": "llama3",
        "description": "Run models locally. 100% free & private.",
        "signup_url": "https://ollama.com/",
    },
}

class ConfigModel(BaseModel):
    provider: str = "openrouter"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = ""

class ChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None
    context: Optional[list] = None
    provider: Optional[str] = None

class SystemAnalyzeRequest(BaseModel):
    metrics: dict

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
            cfg = ConfigModel(**data)
            if not cfg.model and cfg.provider in FREE_PROVIDERS:
                cfg.model = FREE_PROVIDERS[cfg.provider]["default_model"]
            if not cfg.base_url and cfg.provider in FREE_PROVIDERS:
                cfg.base_url = FREE_PROVIDERS[cfg.provider]["base_url"]
            return cfg
    return ConfigModel(
        provider="openrouter",
        model=FREE_PROVIDERS["openrouter"]["default_model"],
        base_url=FREE_PROVIDERS["openrouter"]["base_url"],
    )

def save_config(cfg: ConfigModel):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg.model_dump(), f)

def get_client(cfg: ConfigModel):
    return OpenAI(
        base_url=cfg.base_url or "https://openrouter.ai/api/v1",
        api_key=cfg.api_key or "sk-no-key-required",
        default_headers={
            "HTTP-Referer": "https://aivo.app",
            "X-Title": "AIVO",
        } if cfg.provider == "openrouter" else {},
    )

SYSTEM_PROMPT = """You are AIVO, an AI system control assistant integrated directly into the user's PC.

You have real-time access to:
- System metrics: CPU usage, RAM, disk, network, running processes
- File system: read, write, list, search files
- Command execution: run shell commands, launch apps, kill processes
- Installed applications database

Your capabilities:
1. ANALYZE: Interpret system metrics and diagnose problems
2. SUGGEST: Proactively recommend optimizations based on current state
3. EXECUTE: Perform actions when the user asks
4. EXPLAIN: Break down complex system concepts simply
5. PREDICT: Anticipate issues based on trends (e.g., "disk will be full in 3 days")

Guidelines:
- Be concise but thorough
- When you detect a problem (high CPU, low disk, etc.), proactively suggest a fix
- If the user's request is vague, ask clarifying questions
- Never execute destructive commands without explicit confirmation
- Explain what you're doing before you do it

Today's date: {date}
Current system state will be provided in each request."""

ANALYZE_PROMPT = """You are AIVO's analysis engine. Given the following system metrics, provide:
1. A brief health assessment (good/warning/critical)
2. Any immediate issues detected
3. 1-3 actionable suggestions to improve performance or stability
4. A simple explanation the user can understand

System Metrics:
{metrics}

Respond in a friendly, helpful tone. Use emojis sparingly."""

@router.post("/chat")
def chat(req: ChatRequest):
    cfg = load_config()
    if req.provider:
        p = ConfigModel(
            provider=req.provider,
            api_key=cfg.api_key,
            base_url=FREE_PROVIDERS.get(req.provider, {}).get("base_url"),
            model=FREE_PROVIDERS.get(req.provider, {}).get("default_model", ""),
        )
    else:
        p = cfg
    try:
        client = get_client(p)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(date="2026-07-07")}
        ]
        if req.context:
            messages.extend(req.context[-8:])
        messages.append({"role": "user", "content": req.message})
        response = client.chat.completions.create(
            model=p.model,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        )
        return {
            "response": response.choices[0].message.content,
            "model": p.model,
            "provider": p.provider,
        }
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "unauthorized" in error_msg.lower() or "api key" in error_msg.lower():
            raise HTTPException(status_code=401, detail=f"Invalid API key for {p.provider}. Get one at {FREE_PROVIDERS.get(p.provider, {}).get('signup_url', 'the provider website')}")
        if "model" in error_msg.lower() and "not" in error_msg.lower():
            raise HTTPException(status_code=400, detail=f"Model '{p.model}' not available. Try a different model.")
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/analyze")
def analyze_metrics(req: SystemAnalyzeRequest):
    cfg = load_config()
    try:
        client = get_client(cfg)
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {"role": "system", "content": ANALYZE_PROMPT.format(metrics=json.dumps(req.metrics, indent=2))},
            ],
            temperature=0.5,
            max_tokens=1000,
        )
        return {
            "analysis": response.choices[0].message.content,
            "model": cfg.model,
        }
    except Exception as e:
        return {"analysis": f"Analysis unavailable: {str(e)}", "model": "none"}

@router.get("/config")
def get_config():
    cfg = load_config()
    data = cfg.model_dump()
    # Never return the stored API key to clients; expose only whether one is set
    # plus a masked hint so the UI can show it is configured.
    raw_key = data.pop("api_key", "") or ""
    data["api_key_set"] = bool(raw_key)
    data["api_key_hint"] = f"...{raw_key[-4:]}" if len(raw_key) >= 4 else ""
    return {**data, "free_providers": FREE_PROVIDERS}

@router.post("/config")
def set_config(cfg: ConfigModel):
    # The key is never sent back to the client, so an empty api_key on save means
    # "keep the existing one" rather than wiping the stored credential.
    if not cfg.api_key:
        cfg.api_key = load_config().api_key
    if cfg.provider in FREE_PROVIDERS:
        info = FREE_PROVIDERS[cfg.provider]
        if not cfg.base_url:
            cfg.base_url = info["base_url"]
        if not cfg.model:
            cfg.model = info["default_model"]
    save_config(cfg)
    return {"status": "saved"}
