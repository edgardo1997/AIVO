import type { ReactNode } from "react";
import { Dot, type Severity } from "./Badge";

interface TimelineItem {
  id: string | number;
  tone?: Severity;
  title: ReactNode;
  meta?: ReactNode;
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="sntl-timeline">
      {items.map((item) => (
        <div className="sntl-timeline-item" key={item.id}>
          <span className="sntl-timeline-dot">
            <Dot tone={item.tone ?? "info"} />
          </span>
          <div className="sntl-timeline-body">
            <div className="sntl-timeline-title">{item.title}</div>
            {item.meta && <div className="sntl-timeline-meta">{item.meta}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
