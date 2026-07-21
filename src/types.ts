export type TabType =
  | "dashboard"
  | "monitor"
  | "chat"
  | "sentinel"
  | "files"
  | "knowledge"
  | "memory"
  | "permissions"
  | "vault"
  | "fleet"
  | "plugins"
  | "agents"
  | "triggers"
  | "settings"
  | "help";

export interface V1ExecuteRequest {
  tool_id: string;
  params: Record<string, unknown>;
}

export interface V1ExecuteResponse {
  success: boolean;
  data: unknown;
  error: string | null;
  requires_confirmation: boolean;
  action_id: string | null;
  duration_ms: number | null;
  pipeline: {
    intent: unknown;
    decision: unknown;
    advisory?: AdvisoryReport | null;
  } | null;
}

export interface AdvisoryAction {
  id: string;
  label: string;
  delegated_intent?: string | null;
  local_action?: "dismiss" | "show_evidence" | null;
}

export interface AdvisoryInsight {
  kind: "risk" | "opportunity" | "contradiction" | "uncertainty" | string;
  title: string;
  detail: string;
  level: 0 | 1 | 2 | 3;
}

export interface AdvisoryReport {
  confidence_score: number;
  confidence_label: "baja" | "media" | "alta";
  explanation: string;
  positive_factors: string[];
  negative_factors: string[];
  insights: AdvisoryInsight[];
  intervention_level: 0 | 1 | 2 | 3;
  should_notify: boolean;
  actions: AdvisoryAction[];
  evidence: { type: string; id: string; verified: boolean }[];
}

export interface V1PolicyInfo {
  id: string;
  description: string;
  source: string;
}

export interface V1ReloadResponse {
  status: string;
  policies: V1PolicyInfo[];
}

export interface V1AuditEntry {
  id: number;
  timestamp: string;
  action: string;
  details: string;
  status: string;
  user: string;
}

export interface V1AuditResponse {
  entries: V1AuditEntry[];
  total: number;
}

export type AuditEntry = V1AuditEntry;

export interface CpuInfo {
  percent: number;
  count: number;
  freq: { current: number };
}

export interface MemoryInfo {
  percent: number;
  total: number;
  used: number;
  swap_percent: number;
  swap_used: number;
  swap_total: number;
}

export interface DiskPartition {
  mountpoint: string;
  fstype: string;
  total: number;
  used: number;
  free: number;
  percent: number;
}

export interface DiskInfo {
  partitions: DiskPartition[];
}

export interface NetworkInfo {
  bytes_recv: number;
  bytes_sent: number;
  connections: unknown[];
}

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
}

export interface PermissionStatus {
  level: string;
  emergency_stop: boolean;
  pending_actions: number;
}

export interface FleetStatus {
  local_ip: string;
  api_port: number;
  api_url: string;
  remote_enabled: boolean;
  paired: boolean;
  device_count: number;
}

export interface FleetDevice {
  device_id: string;
  name: string;
  device_type: string;
  os: string;
  version: string;
  ip: string;
  port: number;
  last_seen: string | null;
  is_self: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface SyncLogEntry {
  id: number;
  direction: string;
  peer_id: string;
  peer_url: string;
  status: string;
  config_keys: string;
  error: string;
  started_at: string;
  completed_at: string | null;
}

export interface PluginInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  has_code: boolean;
  enabled: boolean;
  loaded: boolean;
  error?: string;
  is_builtin?: boolean;
  permissions?: string[];
  homepage?: string;
  license?: string;
}

export interface MarketplacePlugin {
  id: string;
  name: string;
  version: string;
  author: string;
  description: string;
  hooks: string[];
  permissions: string[];
  download_url: string;
  homepage: string;
  license: string;
  updated: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  provider: string;
  model: string;
  capabilities: string[];
  allowed_tools: string[];
  system_prompt: string;
  status: string;
  max_concurrency: number;
  created_at?: string;
  updated_at?: string;
}

export interface StepResultItem {
  step_id: string;
  tool_id: string;
  success: boolean;
  data?: unknown;
  error?: string | null;
  duration_ms?: number | null;
  attempts?: number;
  recovery_strategy?: string;
  executed_tool_id?: string | null;
  status?: string;
  model_decision?: {
    provider_id: string;
    model: string;
    task_type: string;
    strategy: string;
    reason: string;
  } | null;
}

export interface PlanStepItem {
  id: string;
  tool_id: string;
  description: string;
  estimated_impact: string;
  is_reversible: boolean;
  depends_on?: string[];
  model_decision?: {
    provider_id: string;
    model: string;
    task_type: string;
    strategy: string;
    reason: string;
  } | null;
}

export interface SentinelResponse {
  presentation?: SentinelPresentation;
  approved: boolean;
  simulated?: boolean;
  blocked?: boolean;
  action_id?: string | null;
  simulation_summary?: string;
  error?: string | null;
  decision: string;
  decision_reason?: string;
  intent: {
    action: string;
    target: string;
    confidence: number;
    raw_input: string;
    parameters?: Record<string, unknown>;
  };
  plan: {
    risk_score: number;
    steps: PlanStepItem[];
  };
  goal?: {
    id: string;
    priority: number;
    possible_capabilities: string[];
  } | null;
  context_factors?: string[];
  base_risk_score?: number | null;
  context_modifier?: number | null;
  final_risk_score?: number | null;
  tool_result: {
    success: boolean;
    data?: unknown;
    error?: string | null;
    duration_ms?: number | null;
    requires_confirmation: boolean;
  } | null;
  step_results?: StepResultItem[] | null;
  rollback_actions?: { step_id: string; rollback_tool_id: string; success: boolean; error?: string | null }[];
  advisory?: AdvisoryReport | null;
  grounding_results?: GroundingEvidence[];
  grounding_satisfied?: boolean;
  execution_id?: string;
}

export interface GroundingEvidence {
  category: string;
  required: boolean;
  grounded: boolean;
  source: string;
  tool_id?: string | null;
  timestamp?: string;
  freshness_seconds?: number;
  reason?: string;
  error?: string | null;
}

export interface SentinelPresentation {
  version: number;
  mode: "user" | "developer";
  status: "completed" | "needs_approval" | "preview" | "failed" | "not_executed";
  title: string;
  summary: string;
  risk: { level: "unknown" | "low" | "medium" | "high" | "critical"; score?: number | null };
  evidence: {
    required: number;
    verified: number;
    satisfied: boolean;
    sources: { category?: string; tool?: string | null; verified: boolean }[];
  };
  next_action?: string | null;
  details?: {
    intent?: { action: string; target: string; confidence: number };
    decision?: { value: string; reason: string } | null;
    tools?: string[];
    error?: string | null;
  } | null;
}

export interface ApproveResponse {
  presentation?: SentinelPresentation;
  blocked: boolean;
  approved: boolean;
  action_id?: string | null;
  error?: string | null;
  simulation_summary?: string;
  decision?: string;
  decision_reason?: string;
  intent?: {
    action: string;
    target: string;
    confidence: number;
    raw_input: string;
    parameters?: Record<string, unknown>;
  };
  tool_result?: {
    success: boolean;
    data?: unknown;
    error?: string | null;
    duration_ms?: number | null;
    requires_confirmation: boolean;
  } | null;
  step_results?: StepResultItem[] | null;
  rollback_actions?: { step_id: string; rollback_tool_id: string; success: boolean; error?: string | null }[];
}

export interface CircuitBreakerState {
  provider_id: string;
  tool_id?: string;
  state: string;
  consecutive_failures: number;
  failure_threshold: number;
  cooldown_seconds: number;
  remaining_cooldown: number;
  last_failure?: string;
  last_success?: string;
}

export interface RateLimitStats {
  keys: Record<string, { allowed: number; denied: number; limit: number; window_seconds: number }>;
  total_allowed: number;
  total_denied: number;
}

export interface FeedbackStats {
  total_feedbacks: number;
  by_provider?: Record<string, { count: number; avg_duration_ms: number; success_rate: number }>;
}

export interface CostSummary {
  total_cost: number;
  total_tokens: number;
  by_provider?: Record<string, { cost: number; tokens: number }>;
}

export interface ObservabilityOverview {
  enabled: boolean;
  traces: {
    total_executions: number; active_spans: number; success_rate: number;
    latency_ms: { average: number; p50: number; p95: number; maximum: number };
    quality: { blocked: number; redacted: number };
    errors_by_category: Record<string, number>;
  };
  costs: { total_cost_usd: number; total_tokens: number; total_calls: number };
  alerts: { total: number; unacknowledged: number; by_source: Record<string, number> };
}

export interface ModelFeedbackStat {
  provider_id: string;
  task_type: string;
  total: number;
  successes: number;
  failures: number;
  avg_duration_ms: number;
  success_rate: number;
}

export interface ModelFeedbackRecord {
  provider_id: string;
  model: string;
  task_type: string;
  success: boolean;
  duration_ms: number;
  timestamp: string;
  error?: string | null;
}

export interface ModelCostRow {
  provider_id: string;
  model: string;
  total_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface CostTotal {
  total_cost_usd: number;
  total_tokens: number;
}

export interface CostBudget {
  name: string;
  max_cost_usd: number;
  period: string;
  provider_id?: string | null;
  max_tokens?: number | null;
  enabled: boolean;
}

export interface PerformanceAlert {
  id: string;
  tool_id: string;
  metric: string;
  deviation: number;
  severity: string;
  timestamp: string;
}

export interface FallbackStats {
  total_fallbacks: number;
  successful_fallbacks: number;
  by_tool?: Record<string, { attempts: number; successes: number }>;
}

export interface HealthStatus {
  tools: Record<string, { healthy: boolean; state: string; consecutive_failures: number }>;
  stats: Record<string, number>;
}

export interface NetworkStatus {
  online: boolean;
  last_check?: string;
}

export interface AlertInfo {
  id: string;
  severity: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface AlertItem {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  source: string;
  timestamp: string;
  acknowledged: boolean;
  data: Record<string, unknown>;
}

export interface AlertStats {
  total: number;
  unacknowledged: number;
  by_source: Record<string, number>;
  max_alerts: number;
}

export interface AlertListResponse {
  enabled?: boolean;
  alerts: AlertItem[];
  stats: AlertStats;
}

export interface CostAlertItem {
  budget_name: string;
  provider_id: string;
  current_cost: number;
  max_cost: number;
  current_tokens: number;
  max_tokens: number;
  period: string;
}

export interface PerfAlertItem {
  provider_id: string;
  model: string;
  task_type: string;
  tool_id: string;
  baseline_avg: number;
  current_avg: number;
  deviation_pct: number;
  severity: string;
  timestamp: string;
}

export interface TriggerCondition {
  metric: string;
  operator: string;
  value: number;
}

export interface TriggerAction {
  tool_id: string;
  params: Record<string, unknown>;
}

export interface Trigger {
  id: string;
  name: string;
  description: string;
  conditions: TriggerCondition[];
  action: TriggerAction | null;
  cooldown_seconds: number;
  enabled: boolean;
  last_fired: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface TriggerHistory {
  id: number;
  trigger_id: string;
  condition_met: boolean;
  action_executed: boolean;
  result?: string | null;
  timestamp?: string | null;
}

export const TRIGGER_OPERATORS = [
  { value: "gt", label: ">", desc: "Greater than" },
  { value: "lt", label: "<", desc: "Less than" },
  { value: "gte", label: "\u2265", desc: "Greater than or equal" },
  { value: "lte", label: "\u2264", desc: "Less than or equal" },
  { value: "eq", label: "=", desc: "Equal" },
  { value: "neq", label: "\u2260", desc: "Not equal" },
] as const;

export const TRIGGER_METRICS = [
  "cpu_percent",
  "memory_percent",
  "disk_percent",
  "network_bytes_recv",
  "network_bytes_sent",
  "swap_percent",
  "battery_percent",
  "process_count",
  "load_average",
] as const;

export interface AuditEntryFull {
  id: number;
  timestamp: string;
  action: string;
  details: string;
  status: string;
  user: string;
  event_id?: string | null;
  execution_id?: string | null;
  payload?: string | null;
  previous_hash?: string | null;
  entry_hash?: string | null;
}

export interface IntegrityResult {
  valid: boolean;
  entries: number;
  head: string;
}

export const AUDIT_STATUSES = [
  "info", "success", "error", "authorized", "blocked", "denied", "pending_confirmation",
] as const;

export interface SubTaskResult {
  sub_task_id: string;
  success: boolean;
  error?: string | null;
  duration_ms?: number;
}

export interface MultiAgentResponse {
  success: boolean;
  error?: string | null;
  sub_task_results: SubTaskResult[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  multiAgentResult?: MultiAgentResponse;
}

export interface VaultEntry {
  id: string;
  name: string;
  category: string;
  value: string;
  masked: boolean;
  rotatable: boolean;
  rotation_days: number;
  last_rotated: number | null;
  created_at?: string;
  updated_at?: string;
  notes: string;
}

export interface VaultAuditEntry {
  id: number;
  vault_id: string;
  action: string;
  timestamp: string;
  details: string;
}

export interface VaultStatus {
  entry_count: number;
  encryption_enabled: boolean;
  categories: string[];
}

export interface KbDocument {
  doc_id: string;
  source: string;
  chunks: number;
  created_at: string;
}

export interface KbSearchResult {
  text: string;
  source: string;
  score: number;
}

export interface KbStats {
  enabled: boolean;
  documents: number;
  chunks: number;
  embedding_provider: string;
  chunk_size: number;
  chunk_overlap: number;
}

export interface KbListResponse {
  documents: KbDocument[];
  total: number;
}

export interface KbSearchResponse {
  results: KbSearchResult[];
  count: number;
}

export interface KbAddResponse {
  doc_id: string;
  status: string;
}

export interface KbQueryResponse {
  context: string;
  has_results: boolean;
}

export interface PermissionRule {
  id: string;
  user_id: string;
  tool: string;
  permission: string;
  path_prefix: string;
  effect: "allow" | "deny" | "require_confirm";
}

export interface MemorySession {
  session_id: string;
  created_at: string;
  updated_at: string;
  execution_count: number;
  last_utterance: string;
}

export interface MemoryRecord {
  execution_id: string;
  timestamp: string;
  utterance: string;
  intent: Record<string, unknown>;
  tool_result: unknown;
  error: string | null;
  duration_ms: number;
  session_id: string;
}

export interface ReportPreview {
  provider: string;
  model: string;
  selection_reason: string;
  source_count: number;
  source_chars: number;
  estimated_prompt_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  estimated_cost_usd: number;
  sources: Record<string, unknown>[];
  skipped_sensitive: string[];
}

export interface UserProfile {
  identity: {
    user_id: string;
    username?: string;
    role: string;
    is_local: boolean;
    [key: string]: unknown;
  };
  profile: {
    user_id: string;
    username: string;
    display_name: string;
    avatar: string;
    theme: string;
    timezone: string;
    locale: string;
    created_at: string;
    updated_at: string;
  };
  preferences: Record<string, unknown>;
}

export interface ProfileHistoryEntry {
  field: string;
  old_value: string;
  new_value: string;
  changed_at: string;
}

export interface ProfilePreset {
  preset_name: string;
  description: string;
  created_at?: string;
}

export interface ConversationMessage {
  id: string;
  prompt: string;
  response?: string;
  provider?: string;
  model?: string;
  pipeline?: unknown;
  performance?: {
    time_to_first_token_ms: number;
    generation_ms: number;
    output_tokens: number;
    tokens_per_second: number;
  };
  elapsed?: number;
  error?: string;
  errorCode?: string;
  retryable?: boolean;
}

export interface ConversationThread {
  session_id: string;
  title: string;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface ProfileSearchResult {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string;
  theme: string;
  bio: string;
  tags: string[];
}

export interface HelpTopic {
  id: string;
  title: string;
  category: string;
  icon: string;
  content: string;
}

export interface HelpCategory {
  id: string;
  title: string;
  icon: string;
  order: number;
}

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  icon: string;
  action?: { tab: string; label: string };
}

export interface RecoveryStatus {
  circuit_breakers: { name: string; state: string; failure_count: number; last_failure: string | null }[];
  tool_recovery: Record<string, unknown>;
  model_fallback: Record<string, unknown>;
  offline_queue: { id: string; tool_id: string; status: string; created_at: string; error?: string }[];
  network: { online: boolean; last_check?: string };
  healthy: boolean;
}

export interface HealthCheckResult {
  sidecar_responding: boolean;
  offline_items: number;
  circuit_breaker_count: number;
}

export interface ProactiveSuggestion {
  id: string;
  uid: string;
  title: string;
  message: string;
  priority: string;
  icon: string;
  value: number;
  timestamp: number;
}

export interface ProactiveTrend {
  reliable: boolean;
  old_avg?: Record<string, number>;
  new_avg?: Record<string, number>;
  trends?: Record<string, string>;
}

export interface ProactiveStatus {
  suggestions: ProactiveSuggestion[];
  trends: ProactiveTrend;
  engine_active: boolean;
}

export interface ComponentDuration {
  component: string;
  label: string;
  avg_duration_ms: number;
  max_duration_ms: number;
  sample_count: number;
}

export interface ToolUsageStat {
  tool: string;
  calls: number;
  share_pct: number;
  failures: number;
  failure_rate: number;
}

export interface ThroughputStats {
  requests_per_minute: number;
  window_seconds: number;
}

export interface BottleneckInfo {
  component: string;
  label: string;
  avg_duration_ms: number;
  max_duration_ms: number;
  sample_count: number;
  bottleneck_score: number;
  failure_rate: number;
}

export interface PipelineMetricsOverview {
  summary: {
    total_events: number;
    total_failures: number;
  };
  component_durations: ComponentDuration[];
  tool_usage: ToolUsageStat[];
  throughput: ThroughputStats;
  bottlenecks: BottleneckInfo[];
}

export interface TimelineEventSummary {
  event_type: string;
  status: string;
  timestamp: number;
  tool: string | null;
  message: string | null;
  duration: number | null;
  progress: number | null;
}

export interface TimelineNode {
  component: string;
  label: string;
  events: TimelineEventSummary[];
  duration_ms: number;
  status: string;
}

export interface TimelineTree {
  request_id: string;
  children: TimelineNode[];
}
