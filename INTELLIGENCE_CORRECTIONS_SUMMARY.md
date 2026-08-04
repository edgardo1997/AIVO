# Intelligence Corrections Summary

## 1. Purpose

This document records every architectural correction identified when aligning Sentinel's implementation with the Intelligence Constitution and Reasoning Pipeline. Each entry must include the inconsistency, the correction, the owner, and the state.

## 2. Current State

The Phase I architectural checkpoint identified the following areas where the current implementation is partially aligned but requires future work. No production behavior was changed in this checkpoint.

| # | Inconsistency | Proposed Correction | Owner | State |
|---|---|---|---|---|
| 1 | `AIService.chat` currently combines normalization, routing and response in one function. | Refactor `chat` to call each engine explicitly: Identity, Language, Input, Intent, Ambiguity, Context, then Route. | `AIService` | Planned |
| 2 | `ConversationResponse` capabilities carry ad-hoc fields (`language_decision`, `input_understanding`) without a common contract. | Define `ReasoningTrace` dataclass in `sentinel/intelligence/contracts.py` and use it. | `ConversationAvailabilityLayer` | Planned |
| 3 | `ToolExecutionGuard` does not consume `AmbiguityDecision` today. | Wire `AmbiguityDecision` into `ToolExecutionGuard` so material ambiguity blocks invocation. | `ToolExecutionGuard` | Planned |
| 4 | `WorldModel` does not yet exist. | Create `WorldModel` data collection and persistence per `WORLD_MODEL_SPECIFICATION.md`. | `WorldModel` | Planned |
| 5 | `IntentResult` is not formalized. | Create `IntentService` and `IntentResult` contract. | `Intent` | Planned |
| 6 | `RiskService` is not formalized. | Create `RiskService` and `RiskAssessment` contract. | `Risk` | Planned |
| 7 | `ExplanationService` is not formalized. | Create `/api/explain` endpoint and `ExplanationService`. | `Explanation` | Planned |
| 8 | `LearningService` is not formalized. | Create feedback loop that only updates from verified outcomes. | `Learning` | Planned |
| 9 | `HumanBehaviorService` is not formalized. | Create threshold-adjustment service per `HUMAN_INTERACTION_ENGINE.md`. | `HumanBehavior` | Planned |

## 3. Approved Corrections

None. This is the first architectural checkpoint.

## 4. Rejected Proposals

None.

## 5. Notes

- All planned corrections must follow the amendment rule in `SENTINEL_INTELLIGENCE_CONSTITUTION.md`.
- Every correction must add tests and update `INTELLIGENCE_CONSISTENCY_MATRIX.md` before merging.
