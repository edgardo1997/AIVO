# Sentinel Long-Term Operational Memory

Sentinel keeps long-term operational memory separate from its immutable audit log.

## What is stored

- **Execution history:** short-lived technical detail for a session and recovery.
- **Episodic memory:** a concise, user-scoped outcome for each processed execution.
- **Patterns:** deterministic observations of repeated intent targets, created only after
  sufficient evidence (three observations by default).
- **Learned preferences:** user-scoped values recorded as either `explicit` or
  `observed`, including evidence count and confidence.

## Safety rules

1. Memory is advisory context only. It cannot grant permissions, change a policy,
   lower a risk score, authenticate a user, or execute an action.
2. Every record is scoped by verified `user_id`; sessions are not used as the
   long-term identity boundary.
3. Episodes expire after 90 days by default. Audit retention is governed separately.
4. Security-sensitive preference namespaces (`permission`, `policy`, `risk`, `auth`,
   `security`, `execution`) are rejected.
5. Rejected and confirmation-blocked actions are remembered as outcomes, but are not
   executed because of that record.

## Current pattern scope

The first implementation intentionally recognizes only repeated `intent_target` use.
It does not infer semantic facts from raw user text, use embeddings, or send memory to
remote models. Future semantic retrieval must add explicit consent, redaction and
retention controls before it is enabled.
