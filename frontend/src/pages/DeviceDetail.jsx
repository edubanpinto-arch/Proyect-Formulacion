import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import Topbar from "../components/Topbar";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ChevronLeft, Thermometer, Activity } from "lucide-react";
import TempChart from "../components/TempChart";
import { StatusBadge, TempBadge, SeverityBadge } from "../components/Badges";

export default function DeviceDetail() {
  const { deviceId } = useParams();
  const { t } = useI18n();
  const [device, setDevice] = useState(null);
  const [readings, setReadings] = useState([]);
  const [alerts, setAlerts] = useState([]);

  const load = useCallback(async () => {
    try {
      const [d, r, a] = await Promise.all([
        api.get(`/devices/${deviceId}`),
        api.get(`/devices/${deviceId}/readings?limit=120`),
        api.get(`/devices/${deviceId}/alerts`),
      ]);
      setDevice(d.data);
      setReadings(r.data);
      setAlerts(a.data);
    } catch {}
  }, [deviceId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, [load]);

  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString() : "—";

  return (
    <div className="min-h-screen bg-slate-50">
      <Topbar />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-8" data-testid="device-detail-page">
        <Link to="/dashboard" className="inline-flex items-center text-sm text-slate-500 hover:text-slate-900 mb-4">
          <ChevronLeft size={14} className="mr-1" /> {t("nav_dashboard")}
        </Link>

        <div className="flex items-end justify-between flex-wrap gap-4 mb-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{t("device_id")}</div>
            <div className="font-mono text-2xl text-slate-900 mt-1">{deviceId}</div>
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
            <Card className="px-5 py-3 border-slate-200">
              <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{t("target_range")}</div>
              <div className="mono text-emerald-700 font-medium">{t("range_2_8")}</div>
            </Card>
          </div>
        </div>

        <Card className="p-6 border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-heading text-slate-900 font-medium flex items-center gap-2"><Activity size={18} /> {t("temperature_history")}</h2>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-700"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500" /> {t("safe_zone")}</span>
              <span className="flex items-center gap-1.5 text-amber-700"><span className="w-3 border-t-2 border-amber-500 border-dashed" /> 2.5° / 7.5°</span>
              <span className="flex items-center gap-1.5 text-rose-700"><span className="w-3 border-t-2 border-rose-500 border-dotted" /> 2° / 8°</span>
            </div>
          </div>
          <TempChart readings={readings} />
        </Card>

        <Card className="mt-6 p-0 overflow-hidden border-slate-200">
          <div className="px-6 pt-5">
            <h3 className="font-heading text-slate-900 font-medium">{t("alerts")}</h3>
          </div>
          <table className="w-full text-sm mt-3">
            <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-y border-slate-200">
              <tr>
                <th className="text-left py-3 px-6">{t("severity")}</th>
                <th className="text-left py-3 px-6">{t("message")}</th>
                <th className="text-left py-3 px-6">{t("temperature")} / {t("timestamp")}</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 && <tr><td colSpan={3} className="py-10 text-center text-slate-400">{t("no_alerts")}</td></tr>}
              {alerts.map((a) => (
                <tr key={a.id} className="border-b border-slate-100">
                  <td className="py-3 px-6"><SeverityBadge severity={a.severity} t={t} /></td>
                  <td className="py-3 px-6 text-slate-700">{a.message}</td>
                  <td className="py-3 px-6 mono text-xs text-slate-600">{a.temperature?.toFixed?.(2)}°C · {fmtTime(a.ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </main>
    </div>
  );
}
