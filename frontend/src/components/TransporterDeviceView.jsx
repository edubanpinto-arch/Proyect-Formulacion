import React, { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "./ui/card";
import { Thermometer, ShieldCheck, AlertTriangle } from "lucide-react";
import TempChart from "./TempChart";
import { StatusBadge, TempBadge, SeverityBadge } from "./Badges";

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

export default function TransporterDeviceView({ deviceId }) {
  const { t } = useI18n();
  const [data, setData] = useState(null);

  const refresh = useCallback(async () => {
    try { setData((await api.get(`/transporter/device/${deviceId}`)).data); } catch (e) { /* retry next tick */ }
  }, [deviceId]);

  useEffect(() => {
    setData(null);
    refresh();
    const i = setInterval(refresh, 6000);
    return () => clearInterval(i);
  }, [refresh]);

  const device = data?.device;
  const alerts = data?.alerts || [];

  return (
    <div data-testid="transporter-device-view">
      <div className="flex items-end justify-between flex-wrap gap-4 mb-6">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{t("device_id")}</div>
          <div className="font-mono text-2xl text-slate-900 mt-1" data-testid="transporter-device-id">{deviceId}</div>
          <div className="text-sm text-slate-600 mt-1">{device?.name}</div>
        </div>
        <div className="flex items-center gap-3">
          {device && <StatusBadge status={device.live_status} t={t} />}
          <Card className="px-5 py-3 flex items-center gap-3 border-slate-200">
            <Thermometer size={18} className="text-sky-700" />
            <div>
              <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{t("current_temp")}</div>
              <div className="text-2xl mono"><TempBadge value={device?.last_temperature} /></div>
            </div>
          </Card>
        </div>
      </div>

      <Card className="p-6 border-slate-200">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-slate-900 font-medium">{t("temperature_history")}</h2>
          <span className="flex items-center gap-1.5 text-emerald-700 text-xs"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500" /> {t("safe_zone")}</span>
        </div>
        <TempChart readings={data?.readings || []} height={280} />
      </Card>

      <Card className="mt-6 p-6 border-slate-200">
        <h3 className="font-heading text-slate-900 font-medium mb-3 flex items-center gap-2"><AlertTriangle size={18} /> {t("alerts")}</h3>
        {alerts.length === 0 ? (
          <div className="text-sm text-slate-500 flex items-center gap-2"><ShieldCheck size={16} className="text-emerald-600" /> {t("no_alerts")}</div>
        ) : (
          <div className="space-y-2">
            {alerts.map((a) => (
              <div key={a.id} className={`flex items-center justify-between border rounded-md px-4 py-2 ${a.severity === "critical" ? "border-rose-200 bg-rose-50" : "border-amber-200 bg-amber-50"}`}>
                <div className="flex items-center gap-3">
                  <SeverityBadge severity={a.severity} t={t} />
                  <span className="text-sm text-slate-700">{a.message}</span>
                </div>
                <span className="mono text-xs text-slate-500">{fmtTime(a.ts)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
