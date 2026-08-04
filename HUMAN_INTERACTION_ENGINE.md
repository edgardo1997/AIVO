# Human Interaction Engine

## 1. Purpose

Humans do not communicate like API clients. The Human Interaction Engine models real user communication patterns to reduce friction without removing safety.

## 2. Behaviors to Support

| Behavior | Example | Engine Response |
|---|---|---|
| Hesitation | "um, maybe open... no, not that" | Wait for completion; do not act on partial. |
| Self-correction | "abre notepad, digo calculadora" | Use the final, explicit correction. |
| Changing mind | "no, mejor no" | Cancel or pause. |
| Unfinished request | "borra el..." | Prompt for missing target. |
| Implicit request | "estoy aburrido" | Interpret as conversation unless user explicitly asks for action. |
| Frustration | "nada funciona" | Respond supportively; do not escalate permissions. |
| Repeated command | "abre notepad", "abre notepad" | Avoid duplicate tool calls; confirm already open. |
| Context switching | "y por cierto, cuál es la hora" | Treat as new conversational intent. |
| Dictation artifacts | missing punctuation, wrong words | Normalize through Input Understanding. |
| Mixed language | "abre Chrome" | Resolve language and intent before action. |

## 3. Design Principles

- **No execution on partial intent.** Wait for a complete, unambiguous request.
- **No execution on self-canceled input.** If the user corrects before the engine finishes, use the final form.
- **No execution on frustration.** Empathic response, not tool use.
- **No duplicate actions.** Track recent tool invocations in a bounded window.
- **Clarifications are localized and specific.** Ask about the missing dimension, not everything.

## 4. State Model

```
HumanInteractionState
├── user_style: Dict[str, Any]
├── recent_corrections: List[Correction]
├── recent_confirmations: List[Confirmation]
├── clarification_history: List[Clarification]
├── preference_overrides: List[Override]
├── session_frustration_score: float
└── schema_version: int
```

## 5. Interaction with Other Engines

- **Input Understanding:** receives normalized text and confidence.
- **Ambiguity Engine:** receives adjusted thresholds.
- **Explanation Engine:** receives human-style why-answers.
- **Learning Engine:** receives accepted and rejected assumptions.

## 6. Threshold Adjustment

- A user who frequently accepts inferences gets slightly looser *informational* thresholds.
- A user who frequently rejects inferences gets tighter thresholds.
- Destructive, paid and cloud thresholds are never loosened by learning.

## 7. Safety Guards

- Learning never increases authority.
- Frustration never triggers destructive actions.
- Repeated commands never bypass `ToolExecutionGuard`.
- Corrections are not permanent unless the user explicitly confirms.

## 8. Future Work

- Voice-specific disfluency handling.
- Regional command patterns.
- Personal command aliases with explicit user approval.
