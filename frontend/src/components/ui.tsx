import type { ReactNode } from "react";

export function StateBadge({ state }: { state: string }) {
  return <span className={`badge s-${state}`} data-testid="state">{state}</span>;
}

export function Conf({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="muted">—</span>;
  const pct = Math.round(value * 100);
  return (
    <span className="conf" title={`confidence ${value}`}>
      <span className="bar"><span style={{ width: `${pct}%` }} className={value >= 0.85 ? "hi" : value >= 0.7 ? "mid" : "lo"} /></span>
      {pct}%
    </span>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export function Card({ title, children, right }: { title: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card">
      <div className="card-h"><h3>{title}</h3>{right}</div>
      {children}
    </section>
  );
}

export function ErrorLine({ error }: { error: string }) {
  return error ? <p className="error" role="alert">{error}</p> : null;
}

export function fmtTime(v: string | number | undefined) {
  if (v == null || (typeof v !== "number" && typeof v !== "string")) return "";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v.replace(" ", "T") + (v.includes("Z") ? "" : "Z"));
  return isNaN(+d) ? String(v) : d.toLocaleTimeString();
}

/** A JSON blob behind a "展开" toggle, so the learn page (and its recording) can open exactly one thing. */
export function Expand({ name, label, value }: { name: string; label: string; value: unknown }) {
  return (
    <details className="jsonbox" data-json={name}>
      <summary>展开 {label}</summary>
      <Json value={value} />
    </details>
  );
}
