import type { CSSProperties } from "react";

export type IconName =
  | "dashboard" | "monitor" | "chat" | "console" | "files" | "audit"
  | "shield" | "plugin" | "fleet" | "settings"
  | "cpu" | "memory" | "disk" | "network" | "activity" | "swap"
  | "alert" | "check" | "x" | "refresh" | "trash" | "play" | "stop"
  | "lock" | "unlock" | "eye" | "key" | "zap" | "search" | "plus"
  | "bell" | "power" | "brain" | "clock" | "server" | "wifi" | "mic" | "volume" | "send"
  | "folder" | "file" | "chevronRight" | "download" | "sparkles" | "gauge";

const paths: Record<IconName, string> = {
  dashboard: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z",
  monitor: "M3 4h18v12H3zM8 20h8M12 16v4",
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  console: "M4 4h16v16H4zM7 9l3 3-3 3M13 15h4",
  files: "M4 5a2 2 0 0 1 2-2h4l2 3h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4z",
  audit: "M9 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2M9 3a1 1 0 0 0 0 2h6a1 1 0 0 0 0-2M9 3a1 1 0 0 1 0-2h6a1 1 0 0 1 0 2M9 12l2 2 4-4",
  shield: "M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5z",
  plugin: "M9 3v4M15 3v4M6 7h12v4a6 6 0 0 1-12 0zM12 17v4",
  fleet: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2c3 3 3 17 0 20M12 2c-3 3-3 17 0 20",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H1a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 2.6 7a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V1a2 2 0 1 1 4 0v.1A1.6 1.6 0 0 0 17 2.6a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H23a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z",
  cpu: "M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2M6 6h12v12H6zM10 10h4v4h-4z",
  memory: "M4 6h16v9H4zM4 19h16M7 15v4M12 15v4M17 15v4M8 9h8",
  disk: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6M12 3v3M12 18v3",
  network: "M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0M12 12v6M9 21h6",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  swap: "M7 3v14M7 3l-3 3M7 3l3 3M17 21V7M17 21l-3-3M17 21l3-3",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6",
  trash: "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14",
  play: "M6 4l14 8-14 8z",
  stop: "M6 6h12v12H6z",
  lock: "M6 10V7a6 6 0 0 1 12 0v3M5 10h14v11H5z",
  unlock: "M6 10V7a6 6 0 0 1 11-3M5 10h14v11H5z",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
  key: "M15 7a4 4 0 1 0-3.9 5L9 14l-2 2-2-1v-2l6-6M14.5 7.5h.01",
  zap: "M13 2 3 14h8l-1 8 10-12h-8z",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16M21 21l-4.3-4.3",
  plus: "M12 5v14M5 12h14",
  bell: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  power: "M12 2v10M6.4 6.4a9 9 0 1 0 11.2 0",
  brain: "M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 0V4a3 3 0 0 0-3-1M15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 0",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2",
  server: "M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01",
  wifi: "M2 8.5a15 15 0 0 1 20 0M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0M12 19h.01",
  mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3M6 11a6 6 0 0 0 12 0M12 19v3",
  volume: "M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a9 9 0 0 1 0 14",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  folder: "M4 5a2 2 0 0 1 2-2h4l2 3h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4z",
  file: "M14 3v5h5M6 3h8l5 5v13H6z",
  chevronRight: "M9 18l6-6-6-6",
  download: "M12 3v12M7 10l5 5 5-5M4 21h16",
  sparkles: "M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15l-1.8-4.2L5.5 9l4.7-1.3zM19 14l.8 2 2 .8-2 .8L19 20l-.8-2.4-2-.6 2-.8z",
  gauge: "M12 14l4-4M20 16a8 8 0 1 0-16 0",
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
  strokeWidth?: number;
}

export function Icon({ name, size = 18, className, style, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
