import React, { useState } from "react";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { toast } from "sonner";

export default function ChangeMyPasswordDialog({ open, onOpenChange }) {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next1, setNext1] = useState("");
  const [next2, setNext2] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next1 !== next2) { toast.error("Las contraseñas no coinciden"); return; }
    if (next1.length < 8) { toast.error("Mínimo 8 caracteres"); return; }
    setLoading(true);
    try {
      await api.post("/auth/change-my-password", { current_password: current, new_password: next1 });
      toast.success(t("password_updated"));
      setCurrent(""); setNext1(""); setNext2("");
      onOpenChange(false);
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("change_my_password")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("current_password")}</Label>
            <Input data-testid="my-current-pwd" type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("new_password")}</Label>
            <Input data-testid="my-new-pwd" type="password" required value={next1} onChange={(e) => setNext1(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("confirm_password")}</Label>
            <Input data-testid="my-confirm-pwd" type="password" required value={next2} onChange={(e) => setNext2(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("cancel")}</Button>
            <Button type="submit" disabled={loading} className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="my-change-pwd-submit">
              {t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
