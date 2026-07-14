<div align="center">
  <h1>◇ Sentinel</h1>
  <p><strong>Trust Layer for AI-OS Interaction</strong></p>
  <p>A security layer between AI agents and your operating system — policies, audit, and execution control.</p>
  <br/>
  <p>
    <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12"/>
    <img src="https://img.shields.io/badge/version-1.0.0-green" alt="v1.0.0"/>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"/>
    <img src="https://img.shields.io/github/v/release/anomalyco/sentinel" alt="GitHub Release"/>
  </p>
</div>

## What is Sentinel?

Sentinel is a **Trust Layer** — it sits between AI agents and your operating system, enforcing security policies, auditing every execution, and redacting sensitive data from outputs.

## Quick Start

### Docker

```bash
docker pull ghcr.io/anomalyco/sentinel:latest
docker run -d -p 8765:8765 ghcr.io/anomalyco/sentinel:latest
```

Open http://localhost:8765

### Windows

Download the MSI installer from the [Releases page](https://github.com/anomalyco/sentinel/releases).

## Architecture

```
Identity → Intent → Decision → Policy → Gateway → Execution → Quality → Audit
```

Every tool execution goes through this 7-step pipeline. No bypass is allowed.

## Features

- **YAML Policies** — Configure permission levels, destructive patterns, and tool access without touching code
- **Hot Reload** — Edit policy YAML files and reload without restarting
- **Quality Gate** — Automatic detection and redaction of API keys, tokens, and secrets in tool outputs
- **SQLite Storage** — All audit logs, execution history, and config in a single database file
- **API v1** — Professional REST API with OpenAPI spec

## Documentation

- [Getting Started](docs/getting-started.md)
- [Policies Guide](docs/policies-guide.md)
- [API Reference](docs/api-reference.md)
- [Deployment Guide](docs/deployment.md)
- [OpenAPI Spec](docs/openapi.yaml)

## License

MIT
