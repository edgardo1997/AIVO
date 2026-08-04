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

## 4. Consistency Checks

Before merging any feature, verify:

1. It does not bypass `ToolExecutionGuard`.
2. It does not bypass `ExecutionPipeline`.
3. It does not reduce the matrix coverage.
4. It adds or updates the relevant engine contract.
5. It updates this matrix.
