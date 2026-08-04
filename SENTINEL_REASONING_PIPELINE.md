# Sentinel Reasoning Pipeline

## 1. Overview

The reasoning pipeline is a strict sequence of bounded stages. Each stage owns one transformation of the user's input. Stages may emit a result, a clarification, or a failure. They never bypass each other.

```
Identity
  ↓
Language
  ↓
Input Normalization
  ↓
Intent Understanding
  ↓
Ambiguity Resolution
  ↓
Context Resolution
  ↓
Memory Selection
  ↓
World Model
  ↓
Planning
  ↓
Risk Evaluation
  ↓
Governance
  ↓
Execution
  ↓
Verification
  ↓
Explanation
  ↓
Learning
  ↓
Persistence
```

## 2. Stage Contracts

### 2.1 Identity Engine

- **Purpose:** determine who is interacting.
- **Inputs:** device context, session token, user profile.
- **Outputs:** `IdentityResult` with user id, session, trust level.
- **Failure mode:** degraded local-only session.
- **Consumer:** Language Engine.

### 2.2 Language Engine

- **Purpose:** determine the response language.
- **Inputs:** message, user preference, conversation language, explicit request.
- **Outputs:** `LanguageDecision`.
- **Failure mode:** product default language.
- **Consumer:** Input Normalization Engine and response assembly.

### 2.3 Input Normalization Engine

- **Purpose:** recover harmless noise.
- **Inputs:** raw text, language, context.
- **Outputs:** `InputUnderstandingResult` with normalized text and correction log.
- **Failure mode:** preserve original text.
- **Consumer:** Intent Engine.

### 2.4 Intent Engine

- **Purpose:** classify what the user wants.
- **Inputs:** normalized text, context, history.
- **Outputs:** `IntentResult` with candidate intents and selected intent.
- **Failure mode:** assume `conversation` intent.
- **Consumer:** Ambiguity Engine.

### 2.5 Ambiguity Engine

- **Purpose:** resolve or request clarification.
- **Inputs:** `IntentResult`, `InputUnderstandingResult`, context.
- **Outputs:** `AmbiguityDecision` (`auto_correct`, `infer`, `ask_clarification`, `reject`).
- **Failure mode:** ask clarification.
- **Consumer:** Context Engine if resolved; UI if clarification.

### 2.6 Context Engine

- **Purpose:** select the information that matters now.
- **Inputs:** resolved intent, conversation history, active workflows.
- **Outputs:** `ContextWindow` with trimmed/summarized messages.
- **Failure mode:** empty context.
- **Consumer:** Memory Engine and World Model.

### 2.7 Memory Engine

- **Purpose:** recall relevant durable state.
- **Inputs:** user id, domain selectors, recency.
- **Outputs:** `MemorySnapshot`.
- **Failure mode:** no memory.
- **Consumer:** World Model and Planning.

### 2.8 World Model Engine

- **Purpose:** provide structured evidence of the user's digital world.
- **Inputs:** user id, context, memory.
- **Outputs:** `WorldModelSnapshot`.
- **Failure mode:** empty model.
- **Consumer:** Planning.

### 2.9 Planning Engine

- **Purpose:** produce an executable plan.
- **Inputs:** resolved intent, world model, selected tools.
- **Outputs:** `ExecutionPlan` (single-step, multi-step, conditional, parallel).
- **Failure mode:** explain that the request cannot be planned.
- **Consumer:** Risk Engine.

### 2.10 Confidence Engine

- **Purpose:** expose certainty at every reasoning stage.
- **Inputs:** each engine's intermediate result.
- **Outputs:** confidence scores per stage.
- **Failure mode:** low confidence.
- **Consumer:** Risk Engine.

### 2.11 Risk Engine

- **Purpose:** estimate privacy, security, cost, destructiveness, irreversibility.
- **Inputs:** plan, identity, permissions, provider, model.
- **Outputs:** `RiskAssessment` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Failure mode:** escalate to `CRITICAL`.
- **Consumer:** Governance Engine.

### 2.12 Governance Engine

- **Purpose:** final authority on whether execution is permitted.
- **Inputs:** plan, risk, permissions, authority state.
- **Outputs:** `GovernanceDecision` (allow, confirm, deny).
- **Failure mode:** deny.
- **Consumer:** Execution Engine.

### 2.13 Execution Engine

- **Purpose:** run approved tools through `ExecutionPipeline`.
- **Inputs:** approved plan.
- **Outputs:** raw tool results.
- **Failure mode:** fail with evidence.
- **Consumer:** Verification Engine.

### 2.14 Verification Engine

- **Purpose:** confirm expected outcome.
- **Inputs:** expected outcome, raw result.
- **Outputs:** `VerificationResult` with evidence and confidence.
- **Failure mode:** report unverified.
- **Consumer:** Explanation Engine.

### 2.15 Explanation Engine

- **Purpose:** answer why-questions.
- **Inputs:** any reasoning artifact.
- **Outputs:** localized explanation.
- **Failure mode:** admit that the reason is unavailable.
- **Consumer:** UI.

### 2.16 Learning Engine

- **Purpose:** improve from verified feedback.
- **Inputs:** verified outcomes, user corrections, accepted/rejected assumptions.
- **Outputs:** model updates, preference updates, routing updates.
- **Failure mode:** no update.
- **Consumer:** Persistence.

### 2.17 Human Behavior Engine

- **Purpose:** reduce unnecessary clarification without ignoring material ambiguity.
- **Inputs:** message pattern, history of corrections, user style.
- **Outputs:** adjusted clarification threshold.
- **Failure mode:** default threshold.
- **Consumer:** Ambiguity Engine.

## 3. Pipeline Invariants

- `ToolExecutionGuard` is the only gateway to `ExecutionPipeline`.
- A stage can ask for clarification and end the pipeline.
- A stage can fail and the pipeline falls back to a safe core response.
- No stage can commit a governed action.
- Every stage must log evidence for audit.

## 4. Implementation Roadmap

1. Finalize engine contracts as dataclasses in `sentinel/intelligence/contracts.py`.
2. Refactor `AIService.chat` to invoke engines explicitly.
3. Add `WorldModel` data collection (filesystem index, app registry, device state).
4. Implement `IntentService` and `RiskService` as thin wrappers around existing logic.
5. Add per-engine confidence fields to `ConversationResponse` capabilities.
6. Add `ExplanationService` endpoints.
7. Add `LearningService` feedback loop.
