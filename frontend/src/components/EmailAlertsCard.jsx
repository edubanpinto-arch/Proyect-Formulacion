import React, { useEffect, useState } from "react";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Mail, Send } from "lucide-react";
import { toast } from "sonner";

export default function EmailAlertsCard() {
  const { t } = useI18n();
  const [status, setStatus] = useState(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api.get("/admin/email/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  const sendTest = async () => {
    setSending(true);
    try {
      const r = await api.post("/admin/email/test");
      toast.success(`${t("email_test_sent")} ${r.data.to}`);
    } catch (e) {
      toast.error(formatErr(e.response?.data?.detail));
    } finally {
      setSending(false);
    }
  };

  const ok = status?.configured;
  return (
    <Card className="p-5 border-slate-200 flex flex-wrap items-center justify-between gap-4" data-testid="email-alerts-card">
      <div className="flex items-start gap-3 max-w-2xl">
        <div className="w-9 h-9 rounded-md grid place-items-center border text-sky-700 bg-sky-50 border-sky-200">
          <Mail size={16} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-heading font-medium text-slate-900">{t("email_alerts_title")}</h3>
            <span
              data-testid="email-alerts-status"
              className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border ${ok ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200"}`}
            >
              {ok ? t("email_configured") : t("email_not_configured")}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">{t("email_alerts_desc")}</p>
          {ok && <p className="text-xs text-slate-600 mt-1 mono" data-testid="email-alerts-sender">{t("email_sender")}: {status.sender}</p>}
        </div>
      </div>
      <Button size="sm" variant="outline" onClick={sendTest} disabled={!ok || sending} data-testid="email-send-test-btn">
        <Send size={14} className="mr-1" /> {t("email_send_test")}
      </Button>
    </Card>
  );
}
