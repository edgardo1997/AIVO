# Intelligence Consistency Matrix

## 1. Purpose

This matrix maps every constitutional guarantee to the engines, files and tests that enforce it. It is used to verify that new features do not weaken existing rules.

## 2. Matrix

| Guarantee | Engines | Files | Tests | Status |
|---|---|---|---|---|
| G1 Identity is evidence, not permission | Identity, Governance | `sentinel/core/tool_execution_guard.py` | `test_identity_authority.py` (conceptual) | Planned |
| G2 Intent before execution | Intent, Planning, Execution | `sidecar/services/input_understanding_service.py` | `test_input_understanding.py` | In Progress |
| G3 Ambiguity before planning | Ambiguity, Planning | `sidecar/services/input_understanding_service.py` | `test_input_understanding.py` | In Progress |
| G4 Planning before execution | Planning, Governance, Execution | `sentinel/core/execution_pipeline.py` | `test_execution_pipeline.py` | Existing |
| G5 Governance before every tool | Governance, Execution | `sentinel/core/tool_execution_guard.py` | `test_tool_execution_guard.py` | Existing |
| G6 Verification before success | Execution, Verification | `sentinel/core/execution_pipeline.py` | `test_execution_pipeline.py` | Existing |
| G7 Explanation after execution | Explanation | `services/explanation_service.py` (conceptual) | `test_explanation.py` (conceptual) | Planned |
| G8 Learning after verification | Learning, Persistence | `sentinel/core/intelligence_coordinator.py` (conceptual) | `test_learning.py` (conceptual) | Planned |
| G9 World model never overrides explicit instruction | World Model, Planning | `services/world_model_service.py` (conceptual) | `test_world_model.py` (conceptual) | Planned |
| G10 Memory never overrides recent evidence | Memory, Context | `repositories/conversation_repository.py` | `test_conversation_*` | Existing |
| G11 Confidence never overrides authority | Confidence, Governance | `sentinel/core/tool_execution_guard.py` | `test_tool_execution_guard.py` | Existing |
| G12 Language is provider-independent | Language | `sidecar/services/language_service.py` | `test_multilingual_contract.py` | Complete |
| G13 Secrets are never normalized | Input Understanding | `sidecar/services/input_understanding_service.py` | `test_input_understanding.py` | Complete |

## 3. Interaction Boundaries

| Engine | Reads From | Writes To | May Not Read | May Not Write |
|---|---|---|---|---|
| Identity | `UserPreferencesStore`, `Vault` | `IdentityResult` | Secrets content | Authority |
| Language | `UserPreferencesStore`, message | `LanguageDecision` | Provider config | Provider state |
| Input Understanding | message, context | `InputUnderstandingResult` | Vault | Tool state |
| Intent | `InputUnderstandingResult` | `IntentResult` | Tool registry | Plan |
| Ambiguity | `InputUnderstandingResult`, `IntentResult` | `AmbiguityDecision` | Tool state | Authority |
| Context | `ConversationRepository`, `Memory` | `ContextWindow` | Tool results | Durable state |
| Memory | `*_store.py` | `MemorySnapshot` | Other user data | Cross-user data |
| World Model | OS, filesystem, registry | `WorldModelSnapshot` | Private file content | Unverified facts |
| Planning | `IntentResult`, `WorldModel` | `ExecutionPlan` | Tool keys | Execution order |
| Risk | plan, identity, prefs | `RiskAssessment` | Secrets | Governance state |
| Governance | plan, risk, authority | `GovernanceDecision` | Model outputs | Execution state |
| Execution | `GovernanceDecision` | raw results | `ToolGateway` | Authority |
| Verification | expected, raw results | `VerificationResult` | Secrets | Durable state |
| Explanation | any artifact | explanation | Secrets | State |
| Learning | verified outcomes | updates | Unverified outcomes | Authority |

## 4. Existing Owner Map (Phase II)

| Constitutional Stage | Existing Owner | Active Runtime Path | Input | Output | Persistence | Test Coverage | Missing Contract | Duplication Risk | Path(s) |
|---|---|---|---|---|---|---|---|---|---|
| Identity | `sidecar/main.py` request context | `ToolRequest.user_context` | device, session, user | identity dict | `UserPreferencesStore`, `Vault` | `test_tool_execution_guard.py` | `IdentityResult` | Low: identity is implicit | both |
| Language | `sidecar/services/language_service.py` | `AIService.chat` | message, preference, explicit | `LanguageDecision` | `UserPreferencesStore` | `test_multilingual_contract.py` | none | Low | both |
| Input Understanding | `sidecar/services/input_understanding_service.py` | `AIService.chat` | raw message, context | `InputUnderstandingResult` | `ConversationResponse` capabilities | `test_input_understanding.py` | none | Low | both |
| Intent | `sidecar/services/input_understanding_service.py` (selected_intent) + `sentinel/core/intent.py` | `ToolExecutionGuard._classify_risk` | normalized text | `Intent` / `selected_intent` | `ToolRequest.user_context` | `test_input_understanding.py`, `test_ambiguity_enforcement.py` | `IntentResult` | Medium: intent scattered | both |
| Ambiguity | `sidecar/services/input_understanding_service.py` | `AIService.chat` + `ToolExecutionGuard` | `InputUnderstandingResult` | `AmbiguityDecision` | `ConversationResponse` capabilities, `ToolRequest.user_context` | `test_ambiguity_enforcement.py` | none | Low | both |
| Context | `sentinel/core/context_window.py` | `AIService.chat` | messages, model | `ContextWindow` / managed messages | none (per-request) | `test_context_window.py` | `ContextSelection` | Low | both |
| Memory | `repositories/*_store.py` | `repositories/conversation_repository.py` | user id, domain | durable state | SQLite | `test_conversation_*`, `test_multilingual_contract.py` | `MemorySelection` | Low | governed, post-exec |
| World Model | none yet | none yet | OS/filesystem | structured facts | none yet | none | `WorldModelEvidence` | Low (no owner yet) | governed, background |
| Planning | `sentinel/core/execution_pipeline.py` + `sentinel/core/planner.py` | `ExecutionPipeline.execute` | intent, tool args | `ExecutionPlan` / `ToolRequest` | `ExecutionGrantContext` | `test_execution_pipeline.py` | `PlanResult` | Low | governed |
| Confidence | none centralized | none | per-stage scores | none | none | none | `ConfidenceSummary` | High if duplicated | all |
| Risk | `sentinel/security/tool_guard.py` `_classify_risk` | `ToolExecutionGuard.execute` | tool, plan, context | `RiskLevel` | `ExecutionResult` | `test_tool_execution_guard.py` | `RiskDecision` | Medium | governed |
| Governance | `sentinel/security/tool_guard.py` + `sentinel/core/policy_engine.py` | `ToolExecutionGuard.execute` | plan, risk, authority | `SecurityDecision` | `ExecutionResult.audit_entry` | `test_tool_execution_guard.py`, `test_ambiguity_enforcement.py` | `GovernanceDecisionReference` | Low | governed |
| Execution | `sentinel/core/execution_pipeline.py` | `ExecutionPipeline.execute` | `GovernanceDecision` | `ToolResult` | audit | `test_execution_pipeline.py` | `VerificationResult` | Low | governed |
| Verification | `sentinel/core/execution_pipeline.py` | `ExecutionPipeline._execute_via_guard` + result | expected, actual | `success` flag | `ToolResult` | `test_execution_pipeline.py` | `VerificationResult` | Low | governed |
| Explanation | `sidecar/services/explanation_service.py` (new) | `explain()` | `reason_code`, `facts` | `ExplanationResult` | none | `test_intelligence_phase2.py` | none | Low | governed, post-exec |
| Learning | `sentinel/core/intelligence/feedback.py` (conceptual) | background | verified outcomes | updates | durable | none | `LearningObservation` | Low | post-exec, background |

## 5. Consistency Checks

Before merging any feature, verify:

1. It does not bypass `ToolExecutionGuard`.
2. It does not bypass `ExecutionPipeline`.
3. It does not reduce the matrix coverage.
4. It adds or updates the relevant engine contract.
5. It updates this matrix.
