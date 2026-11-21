import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import Topbar from "../components/Topbar";
import { api, API } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ChevronLeft, Thermometer, Activity, Download, FileText, ShieldCheck, ShieldOff, Wind, KeyRound, Eye, EyeOff } from "lucide-react";
import TempChart from "../components/TempChart";
import { StatusBadge, TempBadge, SeverityBadge } from "../components/Badges";
import { toast } from "sonner";

export default function DeviceDetail() {
  const { deviceId } = useParams();
  const { t } = useI18n();
  const [device, setDevice] = useState(null);
  const [readings, setReadings] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [hours, setHours] = useState(24);
  const [exporting, setExporting] = useState(null);
  const [devicePwd, setDevicePwd] = useState(null);   // null=no cargado, false=no disponible, string=contraseña
  const [pwdVisible, setPwdVisible] = useState(false);
  const [pwdLoading, setPwdLoading] = useState(false);

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

  const downloadExport = async (format) => {
    setExporting(format);
    try {
      const token = localStorage.getItem("cc_token");
      const url = `${API}/devices/${deviceId}/export?format=${format}&hours=${hours}`;
      const res = await fetch(url, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const a = document.createElement("a");
      const objUrl = URL.createObjectURL(blob);
      a.href = objUrl;
      a.download = `coldchain_${deviceId}_${hours}h.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(objUrl);
      toast.success(`${format.toUpperCase()} listo`);
    } catch (e) {
      toast.error("No se pudo exportar");
    } finally { setExporting(null); }
  };

  const toggleSecure = async () => {
    if (!device) return;
    try {
      await api.post("/devices/secure-mode", {
        device_id: device.device_id,
        require_hmac: !device.require_hmac,
      });
      toast.success(!device.require_hmac ? t("secure_mode_on") : t("secure_mode_off"));
      load();
    } catch (e) { toast.error("Error"); }
  };

  const fmtTime = (iso) => iso ? new Date(iso).toLocaleString() : "—";

  const loadPassword = async () => {
    if (devicePwd !== null) { setPwdVisible((v) => !v); return; }
    setPwdLoading(true);
    try {
      const { data } = await api.get(`/devices/${deviceId}/password`);
      setDevicePwd(data.device_password);
      setPwdVisible(true);
    } catch (e) {
      setDevicePwd(false);
      toast.error(e.response?.data?.detail || "No se pudo obtener la contraseña");
    } finally { setPwdLoading(false); }
  };

  // Lógica de histéresis del ventilador (espejada del firmware)
  // ≥ 8.0°C → ON · ≤ 7.0°C → OFF · 7–8°C → zona de histéresis (mantiene estado previo)
  const fanStatus = (temp) => {
    if (temp == null) return null;
    if (temp >= 8.0) return "on";
    if (temp <= 7.0) return "off";
    return "hysteresis"; // 7 < temp < 8
  };

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
            {/* Indicador de ventilador */}
            {(() => {
              const fs = fanStatus(device?.last_temperature);
              if (!fs) return null;
              const styles = {
                on:          "bg-rose-50   border-rose-200   text-rose-700",
                off:         "bg-slate-100 border-slate-200  text-slate-500",
                hysteresis:  "bg-amber-50  border-amber-200  text-amber-700",
              };
              const labels = {
                on:         "Ventilador ON",
                off:        "Ventilador OFF",
                hysteresis: "Histéresis (7–8°C)",
              };
              return (
                <Card className={`px-5 py-3 flex items-center gap-3 border ${styles[fs]}`}>
                  <Wind size={18} className={fs === "on" ? "animate-spin" : ""} style={fs === "on" ? { animationDuration: "2s" } : {}} />
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.22em] opacity-70">Control Térmico</div>
                    <div className="text-sm font-semibold">{labels[fs]}</div>
                  </div>
                </Card>
              );
            })()}
          </div>
        </div>

        {/* Tarjeta contraseña del dispositivo (solo admin) */}
        <Card className="mt-6 p-6 border-slate-200" data-testid="device-password-card">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-md grid place-items-center border bg-sky-50 border-sky-200 text-sky-700">
                <KeyRound size={18} />
              </div>
              <div>
                <div className="font-heading font-medium text-slate-900">Contraseña del dispositivo</div>
                <div className="text-xs text-slate-500 mt-0.5 max-w-xl">
                  Entrégala al transportador asignado para que pueda conectarse desde la app.
                  Cada consulta queda registrada en el log de auditoría.
                </div>
                {devicePwd && pwdVisible && (
                  <div className="mt-3 flex items-center gap-2">
                    <code className="bg-slate-100 border border-slate-200 px-3 py-1.5 rounded text-sm font-mono text-slate-900 select-all">
                      {devicePwd}
                    </code>
                    <button onClick={() => { navigator.clipboard.writeText(devicePwd); toast.success("Copiada al portapapeles"); }}
                      className="text-xs text-sky-700 hover:underline">Copiar</button>
                  </div>
                )}
              </div>
            </div>
            <Button
              variant="outline"
              className="border-slate-200"
              onClick={loadPassword}
              disabled={pwdLoading}
              data-testid="show-device-password-btn"
            >
              {pwdLoading ? "…" : pwdVisible ? <><EyeOff size={14} className="mr-1.5" />Ocultar</> : <><Eye size={14} className="mr-1.5" />Ver contraseña</>}
            </Button>
          </div>
        </Card>

        <Card className="p-6 border-slate-200">
          <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
            <h2 className="font-heading text-slate-900 font-medium flex items-center gap-2"><Activity size={18} /> {t("temperature_history")}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500 mr-1">{t("range")}</span>
              <select
                data-testid="export-range"
                value={hours}
                onChange={(e) => setHours(parseInt(e.target.value, 10))}
                className="text-xs border border-slate-200 rounded px-2 py-1.5 bg-white"
              >
                <option value={24}>{t("last_24h")}</option>
                <option value={168}>{t("last_7d")}</option>
                <option value={720}>{t("last_30d")}</option>
              </select>
              <Button
                size="sm"
                variant="outline"
                className="border-slate-200"
                onClick={() => downloadExport("csv")}
                disabled={exporting === "csv"}
                data-testid="export-csv-btn"
              >
                <Download size={14} className="mr-1.5" /> {t("export")} {t("export_csv")}
              </Button>
              <Button
                size="sm"
                className="bg-sky-700 hover:bg-sky-800 text-white"
                onClick={() => downloadExport("pdf")}
                disabled={exporting === "pdf"}
                data-testid="export-pdf-btn"
              >
                <FileText size={14} className="mr-1.5" /> {t("export")} {t("export_pdf")}
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs mb-3">
            <span className="flex items-center gap-1.5 text-emerald-700"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500" /> {t("safe_zone")}</span>
            <span className="flex items-center gap-1.5 text-amber-700"><span className="w-3 border-t-2 border-amber-500 border-dashed" /> 2.5° / 7.5°</span>
            <span className="flex items-center gap-1.5 text-rose-700"><span className="w-3 border-t-2 border-rose-500 border-dotted" /> 2° / 8°</span>
          </div>
          <TempChart readings={readings} />
        </Card>

        {/* Secure mode card */}
        <Card className="mt-6 p-6 border-slate-200" data-testid="secure-mode-card">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div className="flex items-start gap-3">
              <div className={`w-10 h-10 rounded-md grid place-items-center border ${device?.require_hmac ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-slate-100 border-slate-200 text-slate-500"}`}>
                {device?.require_hmac ? <ShieldCheck size={18} /> : <ShieldOff size={18} />}
              </div>
              <div>
                <div className="font-heading font-medium text-slate-900">{t("secure_mode")}</div>
                <div className="text-xs text-slate-500 mt-0.5 max-w-xl">{t("secure_mode_help")}</div>
                <div className="mt-2">
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold ${device?.require_hmac ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-slate-100 text-slate-600 border-slate-300"}`} data-testid="secure-mode-status">
                    {device?.require_hmac ? t("secure_mode_on") : t("secure_mode_off")}
                  </span>
                </div>
              </div>
            </div>
            <Button
              variant={device?.require_hmac ? "outline" : "default"}
              className={device?.require_hmac ? "border-rose-200 text-rose-700 hover:bg-rose-50" : "bg-sky-700 hover:bg-sky-800 text-white"}
              onClick={toggleSecure}
              data-testid="secure-mode-toggle"
            >
              {device?.require_hmac ? t("disable_secure_mode") : t("enable_secure_mode")}
            </Button>
          </div>
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
