# World Model Specification

## 1. Purpose

The World Model is a structured, evidence-based representation of the user's digital environment. It is not conversation history. It is the persistent, queryable state of the world Sentinel operates in.

## 2. Domains

| Domain | Evidence Sources | Examples | Update Frequency |
|---|---|---|---|
| Hardware | OS APIs, sensors, registry | CPU, RAM, disk, GPU | On change |
| Operating System | `platform`, `winreg` (Windows), `uname` (Linux) | Version, language, user path | On boot |
| Installed Applications | Start menu, registry, `Applications` folder, package managers | Notepad, Chrome, VS Code | Daily |
| Projects | Filesystem index, VCS metadata | `project.json`, `.git` | On scan |
| Repositories | Git remotes, branches, recent commits | GitHub origin, default branch | On access |
| Preferred Tools | Usage frequency, user preference | Default editor, terminal, browser | On event |
| Frequent Directories | Access logs, recent commands | Downloads, Desktop, Documents | On event |
| Typical Workflows | Learned from verified patterns | Open → edit → run → commit | On completion |
| Known Devices | Bluetooth, USB, network | Phone, printer, headset | On change |
| Connected Providers | Vault, API keys, cloud auth | OpenRouter, Ollama, NVIDIA | On auth |
| Capabilities | Model registry, tool registry | Local runtime, cloud fallback | On change |
| Limitations | Offline state, missing models, hardware class | No GPU, no cloud key | On change |
| Current Environment | Active window, cwd, environment vars | `SENTINEL_PRODUCT_DIR` | Per request |

## 3. Structure

```
WorldModelSnapshot
├── identity
├── hardware
├── operating_system
├── installed_applications: List[Application]
├── projects: List[Project]
├── repositories: List[Repository]
├── preferred_tools: List[ToolReference]
├── frequent_directories: List[DirectoryReference]
├── workflows: List[WorkflowPattern]
├── known_devices: List[Device]
├── connected_providers: List[Provider]
├── capabilities: List[Capability]
├── limitations: List[Limitation]
├── current_environment: Environment
└── schema_version: int
```

## 4. Rules

- Every entry must have an evidence source and a timestamp.
- No entry may be invented or inferred from a model.
- Entries are read-only until a governed action changes the world.
- The World Model does not override an explicit user instruction.
- The World Model does not include secrets or credentials; it may reference `Vault` handles.

## 5. Persistence

The World Model is stored in:

- `repositories/world_model_store.py` for durable, queryable state.
- Memory-mapped caches for fast lookup during a session.
- Versioned snapshots for rollback and audit.

## 6. Consumers

- **Planning Engine:** chooses tools and targets based on available applications and directories.
- **Entity Resolution:** resolves ambiguous references like "that file" or "the project".
- **Risk Engine:** estimates impact using environment state.
- **Explanation Engine:** explains why a tool was chosen.

## 7. Failure Modes

- Missing domain → empty list, never error.
- Stale data → timestamp is exposed; engine decides whether to refresh.
- Corruption → last verified snapshot is used.

## 8. Privacy

- No file content is stored.
- No credential is stored.
- Paths may be stored for operational use but not transmitted.
