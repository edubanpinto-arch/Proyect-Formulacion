import React, { useEffect, useState, useCallback } from "react";
import { api, API } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Download, RefreshCw, Search, X } from "lucide-react";
import { toast } from "sonner";

function actionStyle(action = "") {
  if (action.startsWith("auth.login_failed") || action.includes("_failed")) return "bg-rose-50 text-rose-700 border-rose-200";
  if (action.startsWith("admin.user_deleted") || action.startsWith("device.rejected")) return "bg-rose-50 text-rose-700 border-rose-200";
  if (action.startsWith("admin.user_disabled")) return "bg-amber-50 text-amber-700 border-amber-200";
  if (action.startsWith("admin.user_enabled") || action.startsWith("device.approved") || action.startsWith("auth.login_success") || action.startsWith("auth.2fa_enrolled")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (action.startsWith("admin.")) return "bg-sky-50 text-sky-700 border-sky-200";
  if (action.startsWith("device.")) return "bg-indigo-50 text-indigo-700 border-indigo-200";
  if (action.startsWith("alert.")) return "bg-amber-50 text-amber-700 border-amber-200";
  if (action.startsWith("export.")) return "bg-violet-50 text-violet-700 border-violet-200";
  return "bg-slate-100 text-slate-700 border-slate-300";
}

export default function AuditLog() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [actions, setActions] = useState([]);
  const [actionFilter, setActionFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (actionFilter) params.set("action", actionFilter);
      if (search) params.set("q", search);
      const { data } = await api.get(`/admin/audit?${params.toString()}`);
      setItems(data);
    } catch (e) {
      toast.error("Error cargando auditoría");
    } finally { setLoading(false); }
  }, [actionFilter, search]);

  useEffect(() => {
    api.get("/admin/audit/actions").then((r) => setActions(r.data)).catch(() => {});
    load();
  }, [load]);

  const downloadCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (actionFilter) params.set("action", actionFilter);
      const token = localStorage.getItem("cc_token");
      const res = await fetch(`${API}/admin/audit/export?${params.toString()}`, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = document.createElement("a");
      const url = URL.createObjectURL(blob);
      a.href = url; a.download = `coldchain_audit.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("CSV listo");
    } catch { toast.error("Error exportando"); }
  };

  const fmt = (iso) => iso ? new Date(iso).toLocaleString() : "—";

  return (
    <Card className="p-6 border-slate-200" data-testid="audit-log">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <h3 className="font-heading font-medium text-slate-900">{t("audit_title")}</h3>
          <p className="text-xs text-slate-500 mt-0.5 max-w-xl">{t("audit_subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="border-slate-200" onClick={load} disabled={loading} data-testid="audit-refresh">
            <RefreshCw size={14} className={"mr-1.5 " + (loading ? "animate-spin" : "")} /> Refrescar
          </Button>
          <Button size="sm" className="bg-sky-700 hover:bg-sky-800 text-white" onClick={downloadCsv} data-testid="audit-export">
            <Download size={14} className="mr-1.5" /> CSV
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-[240px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input
            data-testid="audit-search"
            placeholder={t("search_audit")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-9"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
              <X size={14} />
            </button>
          )}
        </div>
        <select
          data-testid="audit-action-filter"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded-md px-3 h-10 bg-white min-w-[200px]"
        >
          <option value="">{t("all_actions")}</option>
          {actions.map((a) => (<option key={a} value={a}>{a}</option>))}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-3">{t("timestamp")}</th>
              <th className="text-left py-3 px-3">{t("actor")}</th>
              <th className="text-left py-3 px-3">{t("action")}</th>
              <th className="text-left py-3 px-3">{t("target")}</th>
              <th className="text-left py-3 px-3">{t("ip_addr")}</th>
              <th className="text-left py-3 px-3">{t("status")}</th>
              <th className="text-right py-3 px-3">{t("metadata")}</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={7} className="py-10 text-center text-slate-400">{t("no_audit")}</td></tr>
            )}
            {items.map((it) => (
              <tr key={it.id} className="border-b border-slate-100 hover:bg-slate-50/40" data-testid={`audit-row-${it.id}`}>
                <td className="py-3 px-3 mono text-xs text-slate-600 whitespace-nowrap">{fmt(it.ts)}</td>
                <td className="py-3 px-3">
                  <div className="text-slate-900 mono text-xs">{it.actor_email || "—"}</div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">{it.actor_role || ""}</div>
                </td>
                <td className="py-3 px-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold mono ${actionStyle(it.action)}`}>
                    {it.action}
                  </span>
                </td>
                <td className="py-3 px-3 text-slate-700 text-xs">
                  {it.target_label ? <span className="mono">{it.target_label}</span> : <span className="text-slate-400">—</span>}
                  {it.target_type && <div className="text-[10px] uppercase tracking-wider text-slate-400">{it.target_type}</div>}
                </td>
                <td className="py-3 px-3 mono text-xs text-slate-600">{it.ip || "—"}</td>
                <td className="py-3 px-3">
                  {it.success ? (
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-emerald-700">{t("success")}</span>
                  ) : (
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-rose-700">{t("failed")}</span>
                  )}
                </td>
                <td className="py-3 px-3 text-right">
                  {it.metadata && Object.keys(it.metadata).length > 0 ? (
                    <button
                      data-testid={`audit-detail-${it.id}`}
                      onClick={() => setDetail(it)}
                      className="text-xs text-sky-700 hover:text-sky-900 underline-offset-2 hover:underline"
                    >
                      {t("view")}
                    </button>
                  ) : <span className="text-slate-300">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("metadata")}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">{t("timestamp")}</div><div className="mono">{fmt(detail.ts)}</div></div>
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">{t("actor")}</div><div className="mono">{detail.actor_email}</div></div>
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">{t("action")}</div><div className="mono">{detail.action}</div></div>
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">{t("target")}</div><div className="mono">{detail.target_label || "—"} <span className="text-slate-400">({detail.target_type || "—"})</span></div></div>
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">{t("ip_addr")}</div><div className="mono">{detail.ip || "—"}</div></div>
                <div><div className="uppercase tracking-wider text-[10px] text-slate-500">User-Agent</div><div className="mono text-[10px] break-all">{detail.user_agent || "—"}</div></div>
              </div>
              <div>
                <div className="uppercase tracking-wider text-[10px] text-slate-500 mb-1">{t("metadata")}</div>
                <pre className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs mono overflow-auto max-h-[300px]">{JSON.stringify(detail.metadata || {}, null, 2)}</pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
