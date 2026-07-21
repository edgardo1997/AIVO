import logging
from fastapi import APIRouter

log = logging.getLogger("sentinel.help")
router = APIRouter(prefix="/api/help")

HELP_TOPICS: dict[str, dict] = {
    "getting-started": {
        "id": "getting-started",
        "title": "Getting Started",
        "category": "basics",
        "icon": "🚀",
        "content": (
            "Sentinel is your local AI orchestration and security layer.\n\n"
            "## Quick Start\n"
            "1. **Set up an AI provider** — Go to the Settings tab and configure a provider (Ollama for local, OpenAI/Anthropic for cloud).\n"
            "2. **Choose your permission level** — The Permissions tab lets you set Auto (AI decides), Confirm (you approve each action), or Manual (full control).\n"
            "3. **Start a conversation** — Use the Chat tab to interact with the AI, or the Execute tab for direct command execution.\n"
            "4. **Monitor your system** — The Dashboard and Monitor tabs show real-time system metrics and AI activity.\n"
            "5. **Explore advanced features** — Fleet for remote access, Plugins for extensibility, Triggers for automation."
        ),
    },
    "chat": {
        "id": "chat",
        "title": "Chat",
        "category": "features",
        "icon": "💬",
        "content": (
            "The Chat tab provides a conversational interface to the AI.\n\n"
            "## How it works\n"
            "- Type your message in the input field and press Enter.\n"
            "- The AI processes your request using the configured provider.\n"
            "- Responses appear in the conversation history above.\n\n"
            "## Tips\n"
            "- Use the agent selector to switch between different AI agents.\n"
            "- Enable multi-agent mode for collaborative responses.\n"
            "- Previous conversation context is maintained for coherence."
        ),
    },
    "execute": {
        "id": "execute",
        "title": "Execute",
        "category": "features",
        "icon": "⚡",
        "content": (
            "The Execute tab allows direct command and code execution through the AI.\n\n"
            "## How it works\n"
            "- Describe the task you want performed (e.g., 'list files in Documents').\n"
            "- The AI interprets your request and generates the appropriate command.\n"
            "- Depending on permission level, the command may execute automatically or require your approval.\n\n"
            "## Permission Levels\n"
            "- **Auto**: Commands execute immediately.\n"
            "- **Confirm**: You review and approve each command before execution.\n"
            "- **Manual**: You write and execute commands directly."
        ),
    },
    "permissions": {
        "id": "permissions",
        "title": "Permissions & Security",
        "category": "security",
        "icon": "🔒",
        "content": (
            "Sentinel's permission system gives you fine-grained control over AI actions.\n\n"
            "## Permission Levels\n"
            "- **Auto** — AI can execute approved actions without confirmation.\n"
            "- **Confirm** — Every action requires your explicit approval (recommended for new users).\n"
            "- **Manual** — Full manual control; the AI proposes but cannot execute.\n\n"
            "## Emergency Stop\n"
            "The Emergency Stop button immediately halts all execution. Activate it from the Permissions tab.\n\n"
            "## Granular Rules\n"
            "Create custom rules to allow/deny specific tools or commands based on patterns."
        ),
    },
    "fleet": {
        "id": "fleet",
        "title": "Fleet & Remote Access",
        "category": "features",
        "icon": "🌐",
        "content": (
            "Fleet allows you to connect multiple devices for remote access and configuration sync.\n\n"
            "## Features\n"
            "- **Remote Access** — Enable remote control of this device from another computer or phone.\n"
            "- **Device Registry** — Track all devices in your fleet with metadata.\n"
            "- **Configuration Sync** — Push or pull configuration between paired devices.\n\n"
            "## Getting Started\n"
            "1. Enable remote access using the toggle.\n"
            "2. Generate a pairing token.\n"
            "3. On the remote device, register this device using the token."
        ),
    },
    "plugins": {
        "id": "plugins",
        "title": "Plugins",
        "category": "features",
        "icon": "🧩",
        "content": (
            "Plugins extend Sentinel with custom functionality.\n\n"
            "## Creating Plugins\n"
            "- Go to the Plugins tab and use the Create form.\n"
            "- Choose from available templates (minimal, with_code, data_collector, etc.).\n"
            "- Each plugin can have hooks that respond to system events.\n\n"
            "## Marketplace\n"
            "- Browse available plugins from the Marketplace tab.\n"
            "- Install plugins directly from URLs.\n"
            "- Permissions are declared in each plugin's manifest and must be approved."
        ),
    },
    "monitor": {
        "id": "monitor",
        "title": "System Monitor",
        "category": "features",
        "icon": "📊",
        "content": (
            "The Monitor tab shows real-time system metrics.\n\n"
            "## Metrics Tracked\n"
            "- CPU usage per core and overall\n"
            "- Memory usage (total, used, available)\n"
            "- Disk usage for all drives\n"
            "- Network I/O statistics\n"
            "- Running processes\n"
            "- GPU utilization (if available)\n\n"
            "Historical data is available in the Observability tab."
        ),
    },
    "policies": {
        "id": "policies",
        "title": "Policies",
        "category": "security",
        "icon": "📜",
        "content": (
            "Policies define rules for what the AI can and cannot do.\n\n"
            "## How Policies Work\n"
            "- Policies are written in YAML format.\n"
            "- Each policy can allow or deny specific actions based on conditions.\n"
            "- Policies are evaluated before execution.\n\n"
            "## Built-in Policies\n"
            "- **Filesystem**: Controls file read/write/delete operations.\n"
            "- **Network**: Controls network access and downloads.\n"
            "- **System**: Controls system-level commands and settings."
        ),
    },
    "agents": {
        "id": "agents",
        "title": "Agents",
        "category": "features",
        "icon": "🤖",
        "content": (
            "Agents are specialized AI personas with specific roles and capabilities.\n\n"
            "## Using Agents\n"
            "- Each agent has a system prompt that defines its behavior.\n"
            "- Switch between agents in the Chat tab.\n"
            "- Multi-agent mode allows multiple agents to collaborate on complex tasks.\n\n"
            "## Creating Agents\n"
            "- Customize existing agents or create new ones with specific instructions.\n"
            "- Define which tools each agent has access to."
        ),
    },
    "triggers": {
        "id": "triggers",
        "title": "Triggers & Automation",
        "category": "features",
        "icon": "⏰",
        "content": (
            "Triggers allow you to automate actions based on events or schedules.\n\n"
            "## Trigger Types\n"
            "- **Schedule**: Runs at specified times or intervals (cron expression).\n"
            "- **Event**: Responds to system events (CPU threshold, disk space, etc.).\n"
            "- **Webhook**: Responds to HTTP requests.\n\n"
            "## Creating Triggers\n"
            "Define what action to take when the trigger fires, such as sending a notification or executing a command."
        ),
    },
    "vault": {
        "id": "vault",
        "title": "Vault",
        "category": "security",
        "icon": "🔐",
        "content": (
            "The Vault securely stores sensitive information like API keys and credentials.\n\n"
            "## Using the Vault\n"
            "- Add entries with key-value pairs for any sensitive data.\n"
            "- Values are encrypted at rest.\n"
            "- Audit logging tracks all access to vault entries.\n\n"
            "## Best Practices\n"
            "- Store API keys, tokens, and credentials in the Vault rather than in code.\n"
            "- Use descriptive keys for easy reference.\n"
            "- Review the audit log periodically."
        ),
    },
    "knowledge-base": {
        "id": "knowledge-base",
        "title": "Knowledge Base",
        "category": "features",
        "icon": "📚",
        "content": (
            "The Knowledge Base stores documents and information for the AI to reference.\n\n"
            "## Features\n"
            "- Store documents (text, markdown, PDF) for AI context.\n"
            "- Search across all stored documents.\n"
            "- Documents are indexed for semantic search.\n\n"
            "## Use Cases\n"
            "- Store project documentation for AI-assisted development.\n"
            "- Save reference materials for quick AI lookup.\n"
            "- Maintain a personal wiki accessible to the AI."
        ),
    },
    "settings": {
        "id": "settings",
        "title": "Settings",
        "category": "basics",
        "icon": "⚙️",
        "content": (
            "The Settings tab lets you configure the application.\n\n"
            "## Configuration Options\n"
            "- **AI Provider**: Choose between Ollama (local), OpenAI, Anthropic, and other providers.\n"
            "- **Model Selection**: Pick which model to use for each provider.\n"
            "- **Cost Tracking**: Set budgets and view usage statistics.\n"
            "- **About**: View version information and check for updates."
        ),
    },
    "feedback-costs": {
        "id": "feedback-costs",
        "title": "Feedback & Costs",
        "category": "features",
        "icon": "💰",
        "content": (
            "Track AI performance feedback and usage costs.\n\n"
            "## Feedback\n"
            "- Rate AI responses to improve future interactions.\n"
            "- View aggregated feedback statistics.\n"
            "- Identify patterns in AI performance.\n\n"
            "## Cost Tracking\n"
            "- Monitor per-model and total spending.\n"
            "- Set budget alerts.\n"
            "- View cost breakdowns by provider and model."
        ),
    },
}

HELP_CATEGORIES = {
    "basics": {"id": "basics", "title": "Getting Started", "icon": "🚀", "order": 1},
    "features": {"id": "features", "title": "Features", "icon": "⭐", "order": 2},
    "security": {"id": "security", "title": "Security", "icon": "🔒", "order": 3},
}


@router.get("/topics")
def list_topics(category: str = None):
    topics = list(HELP_TOPICS.values())
    if category:
        topics = [t for t in topics if t["category"] == category]
    return {"topics": topics, "categories": list(HELP_CATEGORIES.values())}


@router.get("/topics/{topic_id}")
def get_topic(topic_id: str):
    topic = HELP_TOPICS.get(topic_id)
    if not topic:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.get("/categories")
def list_categories():
    return {"categories": list(HELP_CATEGORIES.values())}


ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title": "Bienvenido a Sentinel",
        "description": "Sentinel es tu capa de confianza local para la orquestación de IA. Coordina, protege y audita las interacciones entre la IA y tu sistema.",
        "icon": "🛡️",
    },
    {
        "id": "permissions",
        "title": "Elige tu nivel de permisos",
        "description": "Recomendamos empezar en modo 'Confirmar' — la IA propone acciones y tú las apruebas. Puedes cambiar a 'Auto' cuando te sientas cómodo.",
        "icon": "🔒",
        "action": {"tab": "permissions", "label": "Ir a Permisos"},
    },
    {
        "id": "provider",
        "title": "Configura un proveedor IA",
        "description": "Ve a Configuración para añadir un proveedor. Ollama es gratuito y local. OpenAI y Anthropic ofrecen modelos más potentes pero tienen costo.",
        "icon": "🤖",
        "action": {"tab": "settings", "label": "Ir a Configuración"},
    },
    {
        "id": "chat",
        "title": "Comienza a conversar",
        "description": "Usa el Chat para hablar con la IA. Explora ideas, haz preguntas o pide ayuda con tareas cotidianas.",
        "icon": "💬",
        "action": {"tab": "chat", "label": "Ir al Chat"},
    },
    {
        "id": "monitor",
        "title": "Monitorea tu sistema",
        "description": "El Dashboard y Monitor te muestran métricas en tiempo real: CPU, memoria, disco, red, y procesos.",
        "icon": "📊",
        "action": {"tab": "dashboard", "label": "Ir al Dashboard"},
    },
    {
        "id": "fleet",
        "title": "Conecta tus dispositivos",
        "description": "Con Fleet puedes conectar múltiples dispositivos, sincronizar configuración y acceder remotamente.",
        "icon": "🌐",
        "action": {"tab": "fleet", "label": "Ir a Fleet"},
    },
]


@router.get("/onboarding/steps")
def get_onboarding_steps():
    return {"steps": ONBOARDING_STEPS}
