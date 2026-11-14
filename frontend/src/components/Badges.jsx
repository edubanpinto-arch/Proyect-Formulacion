import React from "react";

export function StatusBadge({ status, t }) {
  const map = {
    active: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500", label: t("status_active") },
    inactive: { bg: "bg-slate-100", text: "text-slate-700", border: "border-slate-300", dot: "bg-slate-400", label: t("status_inactive") },
    pending: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", dot: "bg-amber-500", label: t("pending") },
    rejected: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200", dot: "bg-rose-500", label: t("rejected") },
  };
  const c = map[status] || map.inactive;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs border ${c.bg} ${c.text} ${c.border}`} data-testid={`status-${status}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} ${status === "active" ? "live-dot" : ""}`} />
      <span className="font-medium uppercase tracking-wider text-[10px]">{c.label}</span>
    </span>
  );
}

export function TempBadge({ value }) {
  if (value == null) return <span className="mono text-slate-400">—</span>;
  let cls = "text-emerald-700";
  if (value < 2 || value > 8) cls = "text-rose-700";
  else if (value <= 2.5 || value >= 7.5) cls = "text-amber-700";
  return <span className={`mono font-medium ${cls}`}>{value.toFixed(2)}°C</span>;
}

export function SeverityBadge({ severity, t }) {
  const map = {
    critical: { cls: "bg-rose-50 text-rose-700 border-rose-200", label: t("severity_critical") },
    warning: { cls: "bg-amber-50 text-amber-700 border-amber-200", label: t("severity_warning") },
  };
  const c = map[severity] || map.warning;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold ${c.cls}`}>
      {c.label}
    </span>
  );
}
