import React, { useState, useEffect, useCallback } from "react";
import Topbar from "../components/Topbar";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Lock, Plus } from "lucide-react";
import HwUnlockForm from "../components/HwUnlockForm";
import TransporterDeviceView from "../components/TransporterDeviceView";
import { TempBadge } from "../components/Badges";

export default function TransporterPage() {
  const { t } = useI18n();
  const [list, setList] = useState(null);
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    try { setList((await api.get("/transporter/devices")).data); } catch (e) { setList({ devices: [], assigned_total: 0 }); }
  }, []);

  useEffect(() => {
    load();
    const i = setInterval(load, 8000);
    return () => clearInterval(i);
  }, [load]);

  const devices = list?.devices || [];
  const current = devices.find((d) => d.device_id === selected) ? selected : devices[0]?.device_id;

  const onUnlocked = (id) => { setSelected(id); setAddOpen(false); load(); };

  if (!list) return <div className="min-h-screen bg-slate-50"><Topbar /></div>;

  if (devices.length === 0) {
    return (
      <div className="min-h-screen bg-slate-50">
        <Topbar />
        <main className="max-w-md mx-auto px-6 py-16" data-testid="transporter-unlock">
          <div className="text-center mb-8">
            <div className="w-12 h-12 rounded-md bg-sky-700 text-white grid place-items-center mx-auto"><Lock size={20} /></div>
            <h1 className="text-3xl font-heading font-semibold text-slate-900 mt-4">{t("transporter_view")}</h1>
            <p className="text-sm text-slate-500 mt-1">{t("enter_hw_password")}</p>
          </div>
          <Card className="p-6 border-slate-200"><HwUnlockForm onUnlocked={onUnlocked} /></Card>
        </main>
      </div>
    );
  }

  const missing = Math.max(0, list.assigned_total - devices.length);

  return (
    <div className="min-h-screen bg-slate-50">
      <Topbar />
      <main className="max-w-[1100px] mx-auto px-6 lg:px-10 py-8">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 font-semibold">{t("my_devices")}</div>
            <div className="text-sm text-slate-600 mt-1" data-testid="transporter-connected-count">
              {devices.length} {t("connected_of")} {list.assigned_total} {t("assigned_word")}
            </div>
          </div>
          <Button onClick={() => setAddOpen(true)} className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="connect-another-btn">
            <Plus size={14} className="mr-1" /> {t("connect_another")}
          </Button>
        </div>

        {missing > 0 && (
          <Card className="mb-4 px-4 py-3 border-amber-200 bg-amber-50 text-sm text-amber-800" data-testid="pending-connect-hint">
            {t("pending_connect_hint")} ({missing})
          </Card>
        )}

        <div className="flex flex-wrap gap-2 mb-6" data-testid="transporter-device-tabs">
          {devices.map((d) => (
            <button key={d.device_id} onClick={() => setSelected(d.device_id)} data-testid={`transporter-tab-${d.device_id}`}
              className={`flex items-center gap-3 px-4 py-2 rounded-md border text-sm transition-colors ${d.device_id === current ? "bg-white border-sky-600 ring-1 ring-sky-600" : "bg-white/60 border-slate-200 hover:bg-white"}`}>
              <span className="mono text-slate-900">{d.device_id}</span>
              <TempBadge value={d.last_temperature} />
            </button>
          ))}
        </div>

        {current && <TransporterDeviceView deviceId={current} />}
      </main>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent data-testid="connect-another-dialog">
          <DialogHeader><DialogTitle className="font-heading">{t("connect_another")}</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-500">{t("enter_hw_password")}</p>
          <HwUnlockForm onUnlocked={onUnlocked} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
