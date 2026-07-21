# Sentinel Conversation Runtime

## Decision

Sentinel uses a **Conversation Availability Layer** implemented as the Sentinel Conversation Runtime. It is a continuity boundary, not another model router and not a simulated LLM.

The existing Orchestrator remains responsible for intents and actions, ModelRouter remains responsible for model selection and provider fallback, and the Trust Layer remains authoritative for permissions, approval, execution and audit. The runtime only guarantees a stable conversational response when advanced reasoning is unavailable.

## Contract

Every conversation response includes the existing `response`, `provider`, and `model` fields plus additive `conversation_mode` and `capabilities` fields. `conversation_mode` is `advanced` when a real model answered and `core` when the deterministic Sentinel kernel answered. Internal provider and orchestration exceptions are logged but never returned to the user.

The core kernel supports truthful finite intents: greeting, runtime status, capability discovery, product guidance, and deterministic rendering of completed action results. It does not generate open-ended answers or pretend to reason like a language model.

## Availability sequence

1. The Orchestrator may classify and execute a supported action under the existing trust policy.
2. ModelRouter may provide advanced conversational reasoning.
3. If models are absent, offline, unconfigured, timed out, or fail, Sentinel Core responds through the same contract.
4. If orchestration itself is unavailable, conversation still continues without exposing the failure.

Capability snapshots are runtime-derived and intentionally extensible for local models, voice, multimodal input, tools and onboarding checks. Adding a capability must not require changing Chat UI behavior.
