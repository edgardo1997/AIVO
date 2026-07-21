# Sentinel Local Model

Sentinel ships an application-owned local inference path. It does not require Ollama, Python model libraries, an account, or an API key.

The first production startup downloads two pinned, integrity-verified artifacts in the background: the official Windows Vulkan build of `llama.cpp` and the official `Qwen/Qwen3-1.7B-GGUF` Q8 model. They are stored under `%LOCALAPPDATA%/Sentinel/local-ai`, outside the application binary so updates do not duplicate the 1.8 GB model.

`SentinelLocalModelRuntime` owns installation, SHA-256 verification, process lifecycle and health checks. It binds only to `127.0.0.1:11435`. ModelRouter sees it as the `sentinel_local` provider and gives it the highest default priority. The model receives Sentinel's live orchestration context and capability registry; it is not granted direct system access and all actions continue through the existing Trust Layer.

The API exposes `GET /api/ai/local-model/status` and `POST /api/ai/local-model/install` for onboarding progress and recovery. Conversation Availability Layer remains active while installation is in progress or if installation fails.
