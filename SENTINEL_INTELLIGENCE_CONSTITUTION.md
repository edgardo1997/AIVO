# Sentinel Intelligence Constitution (Phase I)

## 1. Preamble

Sentinel is a governed, local-first personal AI operating intelligence layer. It is not a chatbot. Every interaction must follow the same constitutional reasoning architecture, regardless of provider, model, language, hardware class, or UI surface.

This document defines the permanent rules that every intelligence engine must obey. Subsequent features may extend the engines, but they may not bypass or weaken these guarantees.

## 2. Core Guarantees

| # | Guarantee | Meaning |
|---|---|---|
| G1 | Identity is evidence, not permission | Who the user is does not, by itself, authorize an action. |
| G2 | Intent before execution | No tool is selected before the user's intent is understood. |
| G3 | Ambiguity before planning | No plan is produced while a material ambiguity remains unresolved. |
| G4 | Planning before execution | No tool is invoked before an executable plan exists. |
| G5 | Governance before every tool | `ToolExecutionGuard` has the final authority on invocation. |
| G6 | Verification before success | No action is reported successful before evidence is collected. |
| G7 | Explanation after execution | The user can always ask why a decision was made. |
| G8 | Learning after verification | Models and preferences improve only from verified outcomes. |
| G9 | World model never overrides explicit instruction | Structured evidence does not defeat a direct user command. |
| G10 | Memory never overrides recent evidence | The most reliable, recent evidence wins over durable preference. |
| G11 | Confidence never overrides authority | A high confidence score cannot bypass governance. |
| G12 | Language is provider-independent | The response language is a product decision, not a model decision. |
| G13 | Secrets are never normalized | Codes, paths, keys and hashes are preserved exactly. |

## 3. Engine Ownership

| Engine | Owner File | Responsibility | Never Does |
|---|---|---|---|
| Identity | `services/identity_service.py` (conceptual) | User, session, device, trust | Infer authority from identity |
| Language | `services/language_service.py` | Language decision, instruction, validation | Delegate language to provider |
| Input Understanding | `services/input_understanding_service.py` | Normalize noisy input, recover typos | Execute or authorize |
| Intent | `services/intent_service.py` (conceptual) | Classify what the user wants | Assume execution |
| Ambiguity | `services/input_understanding_service.py` | Detect and resolve ambiguity | Authorize ambiguous actions |
| Context | `sentinel/core/context_window.py` | Select what matters now | Accumulate everything |
| Memory | `repositories/*_store.py` | Persist and recall durable state | Override explicit instruction |
| World Model | `services/world_model_service.py` (conceptual) | Structured evidence of the digital world | Hallucinate |
| Planning | `sentinel/core/execution_pipeline.py` | Convert intent into plans | Execute plans directly |
| Confidence | Each engine exposes a score | Quantify certainty | Replace governance |
| Risk | `services/risk_service.py` (conceptual) | Estimate privacy, security, cost, irreversibility | Authorize by score |
| Governance | `sentinel/core/tool_execution_guard.py` | Final authority on tool invocation | Bypass pipeline |
| Execution | `sentinel/core/execution_pipeline.py` | Run approved tools safely | Execute unapproved tools |
| Verification | `sentinel/core/execution_pipeline.py` + tool results | Confirm expected outcome | Report success without evidence |
| Explanation | `services/explanation_service.py` (conceptual) | Answer why-questions | Invent reasons |
| Learning | `sentinel/core/intelligence_coordinator.py` (conceptual) | Improve from verified feedback | Increase authority silently |
| Human Behavior | `services/human_behavior_service.py` (conceptual) | Reduce unnecessary clarification | Ignore material ambiguity |

## 4. Sovereign Rules

1. A tool is never invoked before `ToolExecutionGuard` approves.
2. `ExecutionPipeline` is the only path to tool execution.
3. A `ModelRouter` recommendation is a proposal, not an order.
4. Provider fallback does not alter language, intent, or authority.
5. The durable backend preference is authoritative; frontend state caches it but cannot override it silently.
6. No engine may increase its own authority based on user acceptance of a previous inference.
7. Every governed action is recorded in `Audit` with the original request, the resolved interpretation, the authority and the outcome.
8. The `World Model` is read-only until an explicit, governed write occurs.

## 5. Amendment Rule

Any change to this constitution must:

1. Be documented in `INTELLIGENCE_CONSISTENCY_MATRIX.md` and `INTELLIGENCE_CORRECTIONS_SUMMARY.md`.
2. Show that no engine bypasses `ToolExecutionGuard` or `ExecutionPipeline`.
3. Show that no guarantee is weakened.
4. Add or update invariants and tests before merging.
