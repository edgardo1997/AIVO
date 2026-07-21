"""Event type constants for Sentinel's Live Activity system."""

# Pipeline lifecycle
PIPELINE_STARTED = "pipeline.started"
PIPELINE_COMPLETED = "pipeline.completed"
PIPELINE_FAILED = "pipeline.failed"
PIPELINE_CANCELLED = "pipeline.cancelled"

# Intent
INTENT_DETECTING = "intent.detecting"
INTENT_DETECTED = "intent.detected"

# Context
CONTEXT_LOADING = "context.loading"
CONTEXT_LOADED = "context.loaded"

# Planner
PLANNER_STARTED = "planner.started"
PLANNER_STEP_CREATED = "planner.step.created"
PLANNER_COMPLETED = "planner.completed"

# Policy
POLICY_VALIDATING = "policy.validating"
POLICY_VALIDATED = "policy.validated"
POLICY_DENIED = "policy.denied"

# Tool
TOOL_SEARCHING = "tool.searching"
TOOL_SELECTED = "tool.selected"
TOOL_STARTED = "tool.started"
TOOL_PROGRESS = "tool.progress"
TOOL_FINISHED = "tool.finished"

# Execution
EXECUTION_STARTED = "execution.started"
EXECUTION_PROGRESS = "execution.progress"
EXECUTION_COMPLETED = "execution.completed"

# Audit
AUDIT_STARTED = "audit.started"
AUDIT_COMPLETED = "audit.completed"

# Performance Engine
PERFORMANCE_SETTINGS_CHANGED = "performance.settings_changed"
PERFORMANCE_PROFILING_STARTED = "performance.profiling.started"
PERFORMANCE_PROFILING_STOPPED = "performance.profiling.stopped"
PERFORMANCE_PROFILE_APPLIED = "performance.profile.applied"

# Power Management
POWER_PLANS_LISTED = "power.plans_listed"
POWER_PLAN_CHANGED = "power.plan_changed"
POWER_PLAN_FAILED = "power.plan_failed"

# Gaming Mode
GAMING_MODE_ACTIVATED = "gaming.mode.activated"
GAMING_MODE_DEACTIVATED = "gaming.mode.deactivated"
GAMING_GAME_DETECTED = "gaming.game.detected"
GAMING_PROFILE_APPLIED = "gaming.profile.applied"

# Developer Mode
DEVELOPER_MODE_ACTIVATED = "developer.mode.activated"
DEVELOPER_MODE_DEACTIVATED = "developer.mode.deactivated"
DEVELOPER_PROJECT_SET = "developer.project.set"
DEVELOPER_ENV_UPDATED = "developer.env.updated"

# Streaming Mode
STREAMING_MODE_ACTIVATED = "streaming.mode.activated"
STREAMING_MODE_DEACTIVATED = "streaming.mode.deactivated"
STREAMING_STREAM_STARTED = "streaming.stream.started"
STREAMING_STREAM_STOPPED = "streaming.stream.stopped"

# Workspace Manager
WORKSPACE_CREATED = "workspace.created"
WORKSPACE_OPENED = "workspace.opened"
WORKSPACE_CLOSED = "workspace.closed"
WORKSPACE_DELETED = "workspace.deleted"

# Automation Engine
AUTOMATION_RULE_ADDED = "automation.rule.added"
AUTOMATION_RULE_REMOVED = "automation.rule.removed"
AUTOMATION_RULE_TRIGGERED = "automation.rule.triggered"
AUTOMATION_ACTION_EXECUTED = "automation.action.executed"

# Identity
IDENTITY_RESOLVED = "identity.resolved"
IDENTITY_VERIFIED = "identity.verified"
IDENTITY_CREDENTIAL_SAVED = "identity.credential_saved"
IDENTITY_CREDENTIAL_LOADED = "identity.credential_loaded"
IDENTITY_CREDENTIAL_DELETED = "identity.credential_deleted"
IDENTITY_FAILED = "identity.failed"

# Sandbox
SANDBOX_CREATED = "sandbox.created"
SANDBOX_PROCESS_ASSIGNED = "sandbox.process_assigned"
SANDBOX_TERMINATED = "sandbox.terminated"
SANDBOX_CLOSED = "sandbox.closed"
SANDBOX_FAILED = "sandbox.failed"

# Environment Snapshot
SNAPSHOT_CREATED = "snapshot.created"
SNAPSHOT_RESTORED = "snapshot.restored"
SNAPSHOT_DELETED = "snapshot.deleted"
SNAPSHOT_FAILED = "snapshot.failed"

# GPU Control
GPU_LISTED = "gpu.listed"
GPU_STATUS = "gpu.status"
GPU_POWER_LIMIT_SET = "gpu.power_limit_set"
GPU_PROFILE_APPLIED = "gpu.profile_applied"
GPU_RESET = "gpu.reset"
GPU_FAILED = "gpu.failed"

# Process Control
PROCESS_LISTED = "process.listed"
PROCESS_KILLED = "process.killed"
PROCESS_SUSPENDED = "process.suspended"
PROCESS_RESUMED = "process.resumed"
PROCESS_PRIORITY_CHANGED = "process.priority_changed"
PROCESS_FAILED = "process.failed"

# AI Workflows
WORKFLOW_CREATED = "workflow.created"
WORKFLOW_STARTED = "workflow.started"
WORKFLOW_STEP_EXECUTED = "workflow.step.executed"
WORKFLOW_COMPLETED = "workflow.completed"
WORKFLOW_FAILED = "workflow.failed"

ALL_EVENTS = frozenset({
    PIPELINE_STARTED,
    PIPELINE_COMPLETED,
    PIPELINE_FAILED,
    PIPELINE_CANCELLED,
    INTENT_DETECTING,
    INTENT_DETECTED,
    CONTEXT_LOADING,
    CONTEXT_LOADED,
    PLANNER_STARTED,
    PLANNER_STEP_CREATED,
    PLANNER_COMPLETED,
    POLICY_VALIDATING,
    POLICY_VALIDATED,
    POLICY_DENIED,
    TOOL_SEARCHING,
    TOOL_SELECTED,
    TOOL_STARTED,
    TOOL_PROGRESS,
    TOOL_FINISHED,
    EXECUTION_STARTED,
    EXECUTION_PROGRESS,
    EXECUTION_COMPLETED,
    AUDIT_STARTED,
    AUDIT_COMPLETED,
    PERFORMANCE_SETTINGS_CHANGED,
    PERFORMANCE_PROFILING_STARTED,
    PERFORMANCE_PROFILING_STOPPED,
    PERFORMANCE_PROFILE_APPLIED,
    POWER_PLANS_LISTED,
    POWER_PLAN_CHANGED,
    POWER_PLAN_FAILED,
    GAMING_MODE_ACTIVATED,
    GAMING_MODE_DEACTIVATED,
    GAMING_GAME_DETECTED,
    GAMING_PROFILE_APPLIED,
    DEVELOPER_MODE_ACTIVATED,
    DEVELOPER_MODE_DEACTIVATED,
    DEVELOPER_PROJECT_SET,
    DEVELOPER_ENV_UPDATED,
    STREAMING_MODE_ACTIVATED,
    STREAMING_MODE_DEACTIVATED,
    STREAMING_STREAM_STARTED,
    STREAMING_STREAM_STOPPED,
    WORKSPACE_CREATED,
    WORKSPACE_OPENED,
    WORKSPACE_CLOSED,
    WORKSPACE_DELETED,
    AUTOMATION_RULE_ADDED,
    AUTOMATION_RULE_REMOVED,
    AUTOMATION_RULE_TRIGGERED,
    AUTOMATION_ACTION_EXECUTED,
    IDENTITY_RESOLVED,
    IDENTITY_VERIFIED,
    IDENTITY_CREDENTIAL_SAVED,
    IDENTITY_CREDENTIAL_LOADED,
    IDENTITY_CREDENTIAL_DELETED,
    IDENTITY_FAILED,
    SANDBOX_CREATED,
    SANDBOX_PROCESS_ASSIGNED,
    SANDBOX_TERMINATED,
    SANDBOX_CLOSED,
    SANDBOX_FAILED,
    SNAPSHOT_CREATED,
    SNAPSHOT_RESTORED,
    SNAPSHOT_DELETED,
    SNAPSHOT_FAILED,
    GPU_LISTED,
    GPU_STATUS,
    GPU_POWER_LIMIT_SET,
    GPU_PROFILE_APPLIED,
    GPU_RESET,
    GPU_FAILED,
    PROCESS_LISTED,
    PROCESS_KILLED,
    PROCESS_SUSPENDED,
    PROCESS_RESUMED,
    PROCESS_PRIORITY_CHANGED,
    PROCESS_FAILED,
    WORKFLOW_CREATED,
    WORKFLOW_STARTED,
    WORKFLOW_STEP_EXECUTED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
})
