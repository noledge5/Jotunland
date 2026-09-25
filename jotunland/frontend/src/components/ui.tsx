import { useEffect, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export function Card({ title, icon: Icon, action, children, className = "", tone }: {
  title?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  tone?: "sun" | "fire" | "water" | "leaf" | "bolt" | "battery";
}) {
  return (
    <section className={`card ${className}`} data-tone={tone}>
      {(title || action) && (
        <header className="card-head">
          {Icon && (
            <span className="card-icon">
              <Icon size={18} />
            </span>
          )}
          <h2>{title}</h2>
          {action && <div className="card-action">{action}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Toggle({ on, onChange, disabled, label }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`toggle ${on ? "on" : ""}`}
      disabled={disabled}
      onClick={(ev) => {
        ev.stopPropagation();
        onChange(!on);
      }}
    >
      <span />
    </button>
  );
}

export function Stat({ label, value, sub, big }: { label: string; value: ReactNode; sub?: ReactNode; big?: boolean }) {
  return (
    <div className={`stat ${big ? "big" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Chips({ options, value, onChange, disabled }: { options: { value: string; label: ReactNode }[]; value?: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className="chips" role="radiogroup">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} className={`chip ${o.value === value ? "active" : ""}`} disabled={disabled} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Schieberegler, der erst beim Loslassen an Home Assistant sendet. */
export function Slider({ value, min, max, step, onCommit, format, disabled }: {
  value: number;
  min: number;
  max: number;
  step: number;
  onCommit: (v: number) => void;
  format?: (v: number) => string;
  disabled?: boolean;
}) {
  const [local, setLocal] = useState(value);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    if (!dragging) setLocal(value);
  }, [value, dragging]);
  const commit = () => {
    setDragging(false);
    if (local !== value) onCommit(local);
  };
  return (
    <div className="slider">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={local}
        disabled={disabled}
        style={{ ["--p" as string]: `${((local - min) / (max - min || 1)) * 100}%` }}
        onPointerDown={() => setDragging(true)}
        onChange={(ev) => setLocal(Number(ev.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={() => dragging && commit()}
      />
      <span className="slider-value">{format ? format(local) : local}</span>
    </div>
  );
}

export function Bar({ value, max = 100, tone }: { value?: number; max?: number; tone?: string }) {
  const p = value === undefined ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="bar" data-tone={tone}>
      <span style={{ width: `${p}%` }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Badge({ children, tone }: { children: ReactNode; tone?: "ok" | "warn" | "bad" | "info" | "muted" }) {
  return <span className="badge" data-tone={tone}>{children}</span>;
}
