import React, { useEffect, useState, useCallback } from "react";
import Topbar from "../components/Topbar";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { StatusBadge, TempBadge, SeverityBadge } from "../components/Badges";
import { Activity, AlertTriangle, BatteryWarning, CheckCircle2, Clock, ShieldAlert, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import UsersManager from "../components/UsersManager";
import AuditLog from "../components/AuditLog";
import EmailAlertsCard from "../components/EmailAlertsCard";

function KPI({ label, value, hint, icon: Icon, accent = "sky", testid }) {
  const accents = {
    sky: "text-sky-700 bg-sky-50 border-sky-200",
    emerald: "text-emerald-700 bg-emerald-50 border-emerald-200",
    rose: "text-rose-700 bg-rose-50 border-rose-200",
    amber: "text-amber-700 bg-amber-50 border-amber-200",
    slate: "text-slate-700 bg-slate-100 border-slate-200",
  };
  return (
    <Card className="p-6 border-slate-200 shadow-sm" data-testid={testid}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{label}</div>
          <div className="mt-2 text-4xl sm:text-5xl font-mono font-medium text-slate-900 tracking-tighter">{value}</div>
          {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
        </div>
        <div className={`w-9 h-9 rounded-md grid place-items-center border ${accents[accent]}`}>
          <Icon size={16} strokeWidth={1.8} />
        </div>
      </div>
    </Card>
  );
}

export default function AdminDashboard() {
  const { t } = useI18n();
  const [stats, setStats] = useState({});
  const [devices, setDevices] = useState([]);
  const [pending, setPending] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [transporters, setTransporters] = useState([]);

  const loadAll = useCallback(async () => {
    try {
      const [s, d, p, a, tr] = await Promise.all([
        api.get("/stats/summary"),
        api.get("/devices"),
        api.get("/devices/pending"),
        api.get("/alerts"),
        api.get("/admin/transporters"),
      ]);
      setStats(s.data);
      setDevices(d.data);
      setPending(p.data);
      setAlerts(a.data);
      setTransporters(tr.data);
    } catch (e) {
      // silent
    }
  }, []);

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 8000);
    return () => clearInterval(id);
  }, [loadAll]);

  const approve = async (deviceId) => {
    try {
      await api.post("/devices/approve", { device_id: deviceId });
      toast.success("Dispositivo aprobado");
      loadAll();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const reject = async (deviceId) => {
    try {
      await api.post("/devices/reject", { device_id: deviceId });
      toast.success("Dispositivo rechazado");
      loadAll();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };
  const ackAlert = async (id) => {
    try { await api.post(`/alerts/${id}/ack`); loadAll(); }
    catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  const assignTransporter = async (deviceId, email) => {
    try {
      await api.post("/devices/approve", { device_id: deviceId, transporter_email: email });
      toast.success("Asignado");
      loadAll();
    } catch (e) { toast.error(formatErr(e.response?.data?.detail)); }
  };

  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString() : "—";

  const activeAlerts = alerts.filter((a) => !a.acknowledged);

  return (
    <div className="min-h-screen bg-slate-50">
      <Topbar />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-8" data-testid="admin-dashboard">
        <div className="flex items-end justify-between mb-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{t("overview")}</div>
            <h1 className="text-3xl sm:text-4xl font-heading font-semibold text-slate-900 mt-1">{t("nav_dashboard")}</h1>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <KPI testid="kpi-active" label={t("active")} value={stats.active ?? 0} icon={Activity} accent="emerald" />
          <KPI testid="kpi-inactive" label={t("inactive")} value={stats.inactive ?? 0} icon={BatteryWarning} accent="slate" />
          <KPI testid="kpi-pending" label={t("pending_approval")} value={stats.pending ?? 0} icon={Clock} accent="amber" />
          <KPI testid="kpi-critical" label={t("critical_alerts")} value={stats.critical_alerts ?? 0} icon={ShieldAlert} accent="rose" />
          <KPI testid="kpi-warning" label={t("warning_alerts")} value={stats.warning_alerts ?? 0} icon={AlertTriangle} accent="amber" />
        </div>

        {/* Pending Devices */}
        {pending.length > 0 && (
          <Card className="mt-6 p-6 border-amber-200 bg-amber-50/30" data-testid="pending-devices-section">
            <div className="flex items-center gap-2 mb-3">
              <Clock size={18} className="text-amber-700" />
              <h2 className="font-heading font-medium text-slate-900">{t("pending_devices")}</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 border-b border-slate-200">
                  <tr><th className="text-left py-2">{t("device_id")}</th><th className="text-left py-2">{t("last_temp")}</th><th className="text-left py-2">{t("last_seen")}</th><th className="text-right py-2">{t("actions")}</th></tr>
                </thead>
                <tbody>
                  {pending.map((d) => (
                    <tr key={d.device_id} className="border-b border-slate-100" data-testid={`pending-row-${d.device_id}`}>
                      <td className="py-3 mono text-slate-900">{d.device_id}</td>
                      <td className="py-3"><TempBadge value={d.last_temperature} /></td>
                      <td className="py-3 text-slate-600 mono text-xs">{fmtTime(d.last_seen)}</td>
                      <td className="py-3 text-right space-x-2">
                        <Button size="sm" onClick={() => approve(d.device_id)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid={`approve-${d.device_id}`}>
                          <CheckCircle2 size={14} className="mr-1" /> {t("approve")}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => reject(d.device_id)} className="border-rose-200 text-rose-700 hover:bg-rose-50" data-testid={`reject-${d.device_id}`}>
                          {t("reject")}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Tabs */}
        <Tabs defaultValue="devices" className="mt-6">
          <TabsList className="bg-white border border-slate-200">
            <TabsTrigger value="devices" data-testid="tab-devices">{t("devices")}</TabsTrigger>
            <TabsTrigger value="alerts" data-testid="tab-alerts">{t("alerts")} {activeAlerts.length > 0 && <span className="ml-1.5 text-[10px] bg-rose-600 text-white rounded-full px-1.5">{activeAlerts.length}</span>}</TabsTrigger>
            <TabsTrigger value="users" data-testid="tab-users">{t("users")}</TabsTrigger>
            <TabsTrigger value="audit" data-testid="tab-audit">{t("audit")}</TabsTrigger>
          </TabsList>

          <TabsContent value="devices" className="mt-4">
            <Card className="p-0 overflow-hidden border-slate-200">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left py-3 px-4">{t("device_id")}</th>
                      <th className="text-left py-3 px-4">{t("device_name")}</th>
                      <th className="text-left py-3 px-4">{t("status")}</th>
                      <th className="text-left py-3 px-4">{t("last_temp")}</th>
                      <th className="text-left py-3 px-4">{t("last_seen")}</th>
                      <th className="text-left py-3 px-4">{t("transporter_assigned")}</th>
                      <th className="text-right py-3 px-4">{t("actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devices.length === 0 && (
                      <tr><td colSpan={7} className="py-10 text-center text-slate-400">{t("no_devices")}</td></tr>
                    )}
                    {devices.map((d) => (
                      <tr key={d.device_id} className="border-b border-slate-100 hover:bg-slate-50/50" data-testid={`device-row-${d.device_id}`}>
                        <td className="py-3 px-4 mono text-slate-900">{d.device_id}</td>
                        <td className="py-3 px-4 text-slate-700">{d.name || "—"}</td>
                        <td className="py-3 px-4"><StatusBadge status={d.live_status} t={t} /></td>
                        <td className="py-3 px-4"><TempBadge value={d.last_temperature} /></td>
                        <td className="py-3 px-4 text-slate-600 mono text-xs">{fmtTime(d.last_seen)}</td>
                        <td className="py-3 px-4 text-slate-700">
                          <select
                            value={d.transporter_email || ""}
                            onChange={(e) => assignTransporter(d.device_id, e.target.value)}
                            className="text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                            data-testid={`assign-${d.device_id}`}
                          >
                            <option value="">{t("none")}</option>
                            {transporters.map((tr) => (
                              <option key={tr.id} value={tr.email}>{tr.name} · {tr.email}</option>
                            ))}
                          </select>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Link to={`/devices/${d.device_id}`}>
                            <Button size="sm" variant="outline" className="border-slate-200" data-testid={`view-${d.device_id}`}>{t("view")}</Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="alerts" className="mt-4">
            <Card className="p-0 overflow-hidden border-slate-200">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left py-3 px-4">{t("severity")}</th>
                      <th className="text-left py-3 px-4">{t("device_id")}</th>
                      <th className="text-left py-3 px-4">{t("message")}</th>
                      <th className="text-left py-3 px-4">{t("timestamp")}</th>
                      <th className="text-right py-3 px-4">{t("actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.length === 0 && (
                      <tr><td colSpan={5} className="py-10 text-center text-slate-400">{t("no_alerts")}</td></tr>
                    )}
                    {alerts.map((a) => (
                      <tr key={a.id} className={`border-b border-slate-100 ${!a.acknowledged ? "" : "opacity-60"}`} data-testid={`alert-row-${a.id}`}>
                        <td className="py-3 px-4"><SeverityBadge severity={a.severity} t={t} /></td>
                        <td className="py-3 px-4 mono">{a.device_id}</td>
                        <td className="py-3 px-4 text-slate-700">{a.message}</td>
                        <td className="py-3 px-4 mono text-xs text-slate-600">{fmtTime(a.ts)}</td>
                        <td className="py-3 px-4 text-right">
                          {!a.acknowledged && (
                            <Button size="sm" variant="outline" className="border-slate-200" onClick={() => ackAlert(a.id)} data-testid={`ack-${a.id}`}>
                              {t("acknowledge")}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="users" className="mt-4 space-y-4">
            <EmailAlertsCard />
            <UsersManager />
          </TabsContent>

          <TabsContent value="audit" className="mt-4">
            <AuditLog />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
