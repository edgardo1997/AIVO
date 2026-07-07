export interface SystemInfo {
  os: string; version: string; hostname: string; architecture: string; processor: string;
  boot_time: number; uptime_seconds: number;
}
export interface CpuInfo {
  percent: number; count: number; physical_count: number;
  freq: { current: number; min: number; max: number } | null;
  load_avg: number[] | null;
}
export interface MemoryInfo {
  total: number; available: number; used: number; percent: number;
  swap_total: number; swap_used: number; swap_percent: number;
}
export interface DiskInfo {
  partitions: { device: string; mountpoint: string; fstype: string; total: number; used: number; free: number; percent: number }[];
  read_bytes: number; write_bytes: number;
}
export interface NetworkInfo {
  bytes_sent: number; bytes_recv: number; packets_sent: number; packets_recv: number;
  connections: { fd: number; type: string; laddr: string; raddr: string; status: string }[];
}
export interface ProcessInfo {
  pid: number; name: string; cpu_percent: number; memory_percent: number; status: string; create_time: number;
}
export interface AiConfig {
  provider: string; api_key: string; base_url: string | null; model: string;
}
export interface FreeProvider {
  label: string; base_url: string | null; api_key_required: boolean; default_model: string; description: string; signup_url: string;
}
export interface CommandResult {
  stdout: string; stderr: string; returncode: number;
  needs_confirm?: boolean; action_id?: string; reason?: string; classification?: string;
}
export interface PermissionStatus {
  level: string; emergency_stop: boolean; pending_actions: number;
  allowlist: string[]; blocklist: string[]; auto_safe: boolean;
}
export interface AuditEntry {
  timestamp: string; action: string; details: string; status: string; user: string;
}
export interface ProactiveSuggestion {
  id: string; title: string; icon: string; priority: string;
  message: string; timestamp: string; dismissed?: boolean;
  actions: { label: string; action: string }[];
  context?: Record<string, unknown>;
}

export interface PluginInfo {
  id: string; name: string; version: string; author: string;
  description: string; enabled: boolean; has_code: boolean;
  loaded: boolean; error: string | null; is_builtin: boolean;
}

export interface FleetStatus {
  remote_enabled: boolean; local_ip: string; api_port: number;
  api_url: string; paired: boolean; has_pairing_token: boolean;
}

export type TabType = "dashboard" | "monitor" | "chat" | "console" | "files" | "audit" | "permissions" | "plugins" | "fleet" | "settings";
