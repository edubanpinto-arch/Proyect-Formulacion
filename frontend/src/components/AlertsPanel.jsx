import React, { useEffect, useMemo, useState, useCallback } from "react";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { SeverityBadge } from "./Badges";
import { ChevronRight, CheckCheck } from "lucide-react";
import { toast } from "sonner";

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

function groupByDevice(alerts) {
  const map = new Map();
  for (const a of alerts) {
    const g = map.get(a.device_id) || { device_id: a.device_id, device_name: a.device_name, latest: a, total: 0, pending: 0 };
    g.total += 1;
    if (!a.acknowledged) g.pending += 1;
    if (a.ts > g.latest.ts) g.latest = a;
    map.set(a.device_id, g);
  }
  return [...map.values()].sort((x, y) => (y.latest.ts > x.latest.ts ? 1 : -1));
}

function DeviceAlertsDialog({ deviceId, onClose, onChanged }) {
  const { t } = useI18n();
  const [items, setItems] = useState([]);

  const load = useCallback(async () => {
    if (!deviceId) return;
    try { setItems((await api.get(`/devices/${deviceId}/alerts`)).data); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  }, [deviceId]);

  useEffect(() => { load(); }, [load]);

  const act = async (path) => {
    try { await api.post(path); await load(); onChanged(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const pending = items.filter((a) => !a.acknowledged).length;

  return (
    <Dialog open={!!deviceId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="device-alerts-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">{t("device_alerts_title")} · <span className="mono">{deviceId}</span></DialogTitle>
          <DialogDescription>{items.length} {t("alerts_total")} · {pending} {t("alerts_pending")}</DialogDescription>
        </DialogHeader>
        <div className="flex justify-end">
          <Button size="sm" disabled={pending === 0} onClick={() => act(`/devices/${deviceId}/alerts/ack-all`)}
            className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="ack-all-btn">
            <CheckCheck size={14} className="mr-1" /> {t("ack_all")}
          </Button>
        </div>
        <div className="max-h-[55vh] overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-md">
          {items.map((a) => (
            <div key={a.id} className={`flex items-center justify-between gap-3 px-4 py-2.5 ${a.acknowledged ? "opacity-60" : ""}`} data-testid={`dialog-alert-row-${a.id}`}>
              <div className="flex items-center gap-3 min-w-0">
                <SeverityBadge severity={a.severity} t={t} />
                <span className="text-sm text-slate-700 truncate">{a.message}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="mono text-xs text-slate-500">{fmtTime(a.ts)}</span>
                {!a.acknowledged && (
                  <Button size="sm" variant="outline" className="border-slate-200" onClick={() => act(`/alerts/${a.id}/ack`)} data-testid={`ack-${a.id}`}>
                    {t("acknowledge")}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AlertsPanel({ alerts, onChanged }) {
  const { t } = useI18n();
  const [openDevice, setOpenDevice] = useState(null);
  const groups = useMemo(() => groupByDevice(alerts), [alerts]);

  return (
    <Card className="p-0 overflow-hidden border-slate-200">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-4">{t("severity")}</th>
              <th className="text-left py-3 px-4">{t("device_id")}</th>
              <th className="text-left py-3 px-4">{t("last_alert")}</th>
              <th className="text-left py-3 px-4">{t("timestamp")}</th>
              <th className="text-left py-3 px-4">{t("alerts_pending")}</th>
              <th className="py-3 px-4" />
            </tr>
          </thead>
          <tbody>
            {groups.length === 0 && (
              <tr><td colSpan={6} className="py-10 text-center text-slate-400">{t("no_alerts")}</td></tr>
            )}
            {groups.map((g) => (
              <tr key={g.device_id} onClick={() => setOpenDevice(g.device_id)}
                className={`border-b border-slate-100 cursor-pointer hover:bg-slate-50 transition-colors ${g.pending ? "" : "opacity-60"}`}
                data-testid={`alert-group-${g.device_id}`}>
                <td className="py-3 px-4"><SeverityBadge severity={g.latest.severity} t={t} /></td>
                <td className="py-3 px-4 mono">{g.device_id}</td>
                <td className="py-3 px-4 text-slate-700">{g.latest.message}</td>
                <td className="py-3 px-4 mono text-xs text-slate-600">{fmtTime(g.latest.ts)}</td>
                <td className="py-3 px-4">
                  <span className={`mono text-xs px-2 py-0.5 rounded-full border ${g.pending ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-slate-100 text-slate-500 border-slate-200"}`}
                    data-testid={`alert-group-count-${g.device_id}`}>
                    {g.pending} / {g.total}
                  </span>
                </td>
                <td className="py-3 px-4 text-right text-slate-400"><ChevronRight size={16} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <DeviceAlertsDialog deviceId={openDevice} onClose={() => setOpenDevice(null)} onChanged={onChanged} />
    </Card>
  );
}
