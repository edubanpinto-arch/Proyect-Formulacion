import React, { useState, useEffect, useCallback } from "react";
import Topbar from "../components/Topbar";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Lock, Thermometer, ShieldCheck, AlertTriangle } from "lucide-react";
import TempChart from "../components/TempChart";
import { StatusBadge, TempBadge, SeverityBadge } from "../components/Badges";
import { toast } from "sonner";

export default function TransporterPage() {
  const { t } = useI18n();
  const [unlocked, setUnlocked] = useState(null); // device id
  const [pwd, setPwd] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  const refresh = useCallback(async (id) => {
    if (!id) return;
    try {
      const { data } = await api.get(`/transporter/device/${id}`);
      setData(data);
    } catch (e) {
      // unlock might have expired
    }
  }, []);

  useEffect(() => {
    if (!unlocked) return;
    refresh(unlocked);
    const i = setInterval(() => refresh(unlocked), 6000);
    return () => clearInterval(i);
  }, [unlocked, refresh]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/transporter/access", { device_password: pwd });
      setUnlocked(data.device_id);
      toast.success("Acceso concedido");
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString() : "—";

  if (!unlocked) {
    return (
      <div className="min-h-screen bg-slate-50">
        <Topbar />
        <main className="max-w-md mx-auto px-6 py-16" data-testid="transporter-unlock">
          <div className="text-center mb-8">
            <div className="w-12 h-12 rounded-md bg-sky-700 text-white grid place-items-center mx-auto">
              <Lock size={20} />
            </div>
            <h1 className="text-3xl font-heading font-semibold text-slate-900 mt-4">{t("transporter_view")}</h1>
            <p className="text-sm text-slate-500 mt-1">{t("enter_hw_password")}</p>
          </div>
          <Card className="p-6 border-slate-200">
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("password")}</Label>
                <Input data-testid="hw-password" type="password" required value={pwd} onChange={(e) => setPwd(e.target.value)} />
              </div>
              <Button type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11" data-testid="hw-unlock-submit">
                {loading ? "…" : t("unlock")}
              </Button>
            </form>
          </Card>
        </main>
      </div>
    );
  }

  const device = data?.device;
  const readings = data?.readings || [];
  const alerts = data?.alerts || [];

  return (
    <div className="min-h-screen bg-slate-50">
      <Topbar />
      <main className="max-w-[1100px] mx-auto px-6 lg:px-10 py-8" data-testid="transporter-device-view">
        <div className="flex items-end justify-between flex-wrap gap-4 mb-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{t("device_id")}</div>
            <div className="font-mono text-2xl text-slate-900 mt-1">{device?.device_id}</div>
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
          <TempChart readings={readings} height={280} />
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
      </main>
    </div>
  );
}
