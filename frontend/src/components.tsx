import type { ReactNode } from "react";

export type Row = Record<string, unknown>;
export type Listing<T> = { items: T[]; total: number };
export const integer = (value: number) => value.toLocaleString();
export const percent = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
export const money = (value: unknown) => Number(value).toLocaleString(undefined, {
  style: "currency", currency: "USD", maximumFractionDigits: 0,
});
export function storage(value: number) {
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}
export const human = (value: string) => value.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
export const localDate = (value: string | null) => value ? new Date(value).toLocaleString() : "—";

export function State({ loading, error, children }: { loading: boolean; error: unknown; children: ReactNode }) {
  if (loading) return <div className="panel empty" role="status"><span className="loader"/> Loading workspace data</div>;
  if (error) return <div className="panel empty" role="alert">{error instanceof Error ? error.message : "Request failed"}</div>;
  return <>{children}</>;
}

export function Heading({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="heading"><div><h1>{title}</h1><p>{description}</p></div>{children}</div>;
}

export function Pill({ value }: { value: string }) {
  const tone = ["up", "open", "healthy", "successful", "passed"].includes(value) ? "ok"
    : ["failed", "blocked", "CRITICAL", "missing"].includes(value) ? "danger"
    : ["WARNING", "warning", "stale", "pending"].includes(value) ? "warning" : "neutral";
  return <span className={`pill ${tone}`}><i/>{human(value)}</span>;
}

export function Metric({ title, value, detail, icon }: { title: string; value: ReactNode; detail: string; icon?: ReactNode }) {
  return <div className="panel metric"><span>{title}{icon}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export function DataTable({ rows, columns, empty = "No records available." }: { rows: Row[]; columns?: string[]; empty?: string }) {
  if (!rows.length) return <div className="empty">{empty}</div>;
  const fields = columns ?? Object.keys(rows[0]);
  return <div className="table-scroll"><table><thead><tr>{fields.map(field => <th key={field}>{human(field)}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{fields.map(field => {
      const value = row[field];
      const text = value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value);
      return <td key={field} title={text}>
        {typeof value === "string" && ["status", "severity"].includes(field) ? <Pill value={value} /> : text}
      </td>;
    })}</tr>)}</tbody>
  </table></div>;
}
