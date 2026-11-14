import React, { useState } from "react";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { toast } from "sonner";

export default function HwUnlockForm({ onUnlocked }) {
  const { t } = useI18n();
  const [pwd, setPwd] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/transporter/access", { device_password: pwd });
      toast.success(`Acceso concedido: ${data.device_id}`);
      setPwd("");
      onUnlocked(data.device_id);
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("password")}</Label>
        <Input data-testid="hw-password" type="password" required value={pwd} onChange={(e) => setPwd(e.target.value)} />
      </div>
      <Button type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11" data-testid="hw-unlock-submit">
        {loading ? "…" : t("unlock")}
      </Button>
    </form>
  );
}
