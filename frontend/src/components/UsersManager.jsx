import React, { useEffect, useState, useCallback } from "react";
import { api, formatErr } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useAuth } from "../lib/auth";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "./ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "./ui/alert-dialog";
import { Plus, KeyRound, ShieldOff, ShieldCheck, Trash2, Power, PowerOff, RefreshCw } from "lucide-react";
import { toast } from "sonner";

function RoleBadge({ role, t }) {
  const cls = role === "admin"
    ? "bg-sky-50 text-sky-700 border-sky-200"
    : "bg-slate-100 text-slate-700 border-slate-300";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold ${cls}`}>
      {role === "admin" ? t("role_admin") : t("role_transporter")}
    </span>
  );
}

function StatusPill({ disabled, t }) {
  return disabled ? (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold bg-rose-50 text-rose-700 border-rose-200">
      <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> {t("disabled")}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider border font-semibold bg-emerald-50 text-emerald-700 border-emerald-200">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t("enabled")}
    </span>
  );
}

export default function UsersManager() {
  const { t } = useI18n();
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [openCreate, setOpenCreate] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "transporter", must_change_password: true });

  const [resetTarget, setResetTarget] = useState(null);
  const [resetPwd, setResetPwd] = useState("");
  const [resetMustChange, setResetMustChange] = useState(true);

  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/users");
      setUsers(data);
    } catch {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const submitCreate = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/users", form);
      toast.success(t("user_created"));
      setOpenCreate(false);
      setForm({ name: "", email: "", password: "", role: "transporter", must_change_password: true });
      load();
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
  };

  const toggleDisabled = async (u) => {
    try {
      await api.patch(`/admin/users/${u.id}`, { disabled: !u.disabled });
      toast.success(t("user_updated"));
      load();
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
  };

  const reset2FA = async (u) => {
    try {
      await api.patch(`/admin/users/${u.id}`, { reset_2fa: true });
      toast.success("2FA " + t("disabled").toLowerCase());
      load();
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
  };

  const submitReset = async () => {
    if (resetPwd.length < 6) { toast.error("Mínimo 6 caracteres"); return; }
    try {
      await api.post(`/admin/users/${resetTarget.id}/reset-password`, {
        new_password: resetPwd, must_change_password: resetMustChange,
      });
      toast.success(t("password_updated"));
      setResetTarget(null); setResetPwd(""); setResetMustChange(true);
      load();
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
  };

  const confirmDelete = async () => {
    try {
      await api.delete(`/admin/users/${deleteTarget.id}`);
      toast.success(t("user_deleted"));
      setDeleteTarget(null);
      load();
    } catch (err) { toast.error(formatErr(err.response?.data?.detail)); }
  };

  const isSelf = (u) => me && u.id === me.id;

  return (
    <Card className="p-6 border-slate-200" data-testid="users-manager">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-heading font-medium text-slate-900">{t("users")}</h3>
        <Dialog open={openCreate} onOpenChange={setOpenCreate}>
          <DialogTrigger asChild>
            <Button className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="add-user-btn">
              <Plus size={14} className="mr-1" /> {t("add_user")}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>{t("add_user")}</DialogTitle></DialogHeader>
            <form onSubmit={submitCreate} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("role")}</Label>
                  <select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                    className="w-full text-sm border border-slate-200 rounded-md px-3 h-10 bg-white"
                    data-testid="new-user-role"
                  >
                    <option value="transporter">{t("new_user_transporter")}</option>
                    <option value="admin">{t("new_user_admin")}</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("name")}</Label>
                  <Input data-testid="new-user-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("email")}</Label>
                <Input data-testid="new-user-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("password")}</Label>
                <Input data-testid="new-user-password" type="text" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={form.must_change_password} onChange={(e) => setForm({ ...form, must_change_password: e.target.checked })} data-testid="new-user-mustchange" />
                {t("force_password_change")}
              </label>
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={() => setOpenCreate(false)}>{t("cancel")}</Button>
                <Button type="submit" className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="create-user-submit">{t("create")}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-[0.18em] text-slate-500 bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left py-3 px-3">{t("name")}</th>
              <th className="text-left py-3 px-3">{t("email")}</th>
              <th className="text-left py-3 px-3">{t("role")}</th>
              <th className="text-left py-3 px-3">{t("status")}</th>
              <th className="text-left py-3 px-3">{t("twofa_status")}</th>
              <th className="text-left py-3 px-3">{t("must_change_label")}</th>
              <th className="text-right py-3 px-3">{t("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-slate-100" data-testid={`user-row-${u.id}`}>
                <td className="py-3 px-3 text-slate-900">{u.name}{isSelf(u) && <span className="ml-2 text-[10px] uppercase tracking-wider text-sky-700 mono">(yo)</span>}</td>
                <td className="py-3 px-3 mono text-slate-600">{u.email}</td>
                <td className="py-3 px-3"><RoleBadge role={u.role} t={t} /></td>
                <td className="py-3 px-3"><StatusPill disabled={u.disabled} t={t} /></td>
                <td className="py-3 px-3">
                  {u.totp_enabled ? (
                    <span className="inline-flex items-center gap-1.5 text-emerald-700 text-xs"><ShieldCheck size={14} /> {t("twofa_on")}</span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-slate-500 text-xs"><ShieldOff size={14} /> {t("twofa_off")}</span>
                  )}
                </td>
                <td className="py-3 px-3 text-slate-700 text-xs">{u.must_change_password ? t("yes") : t("no")}</td>
                <td className="py-3 px-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    <Button size="sm" variant="outline" className="border-slate-200" onClick={() => { setResetTarget(u); setResetPwd(""); setResetMustChange(true); }} data-testid={`reset-pwd-${u.id}`}>
                      <KeyRound size={14} />
                    </Button>
                    {u.role === "admin" && u.totp_enabled && (
                      <Button size="sm" variant="outline" className="border-slate-200" onClick={() => reset2FA(u)} data-testid={`reset-2fa-${u.id}`} title={t("reset_2fa")}>
                        <RefreshCw size={14} />
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      className={u.disabled ? "border-emerald-200 text-emerald-700 hover:bg-emerald-50" : "border-amber-200 text-amber-700 hover:bg-amber-50"}
                      onClick={() => toggleDisabled(u)}
                      disabled={isSelf(u)}
                      data-testid={`toggle-disabled-${u.id}`}
                      title={u.disabled ? t("enable") : t("disable")}
                    >
                      {u.disabled ? <Power size={14} /> : <PowerOff size={14} />}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-rose-200 text-rose-700 hover:bg-rose-50"
                      onClick={() => setDeleteTarget(u)}
                      disabled={isSelf(u)}
                      data-testid={`delete-${u.id}`}
                      title={t("delete")}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Reset password dialog */}
      <Dialog open={!!resetTarget} onOpenChange={(v) => !v && setResetTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("reset_password")}</DialogTitle>
          </DialogHeader>
          {resetTarget && (
            <div className="space-y-3">
              <div className="text-sm text-slate-600">{resetTarget.name} <span className="mono text-slate-400">{resetTarget.email}</span></div>
              <div className="space-y-1">
                <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("new_password")}</Label>
                <Input data-testid="reset-new-pwd" type="text" minLength={6} value={resetPwd} onChange={(e) => setResetPwd(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={resetMustChange} onChange={(e) => setResetMustChange(e.target.checked)} data-testid="reset-mustchange" />
                {t("force_password_change")}
              </label>
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={() => setResetTarget(null)}>{t("cancel")}</Button>
                <Button onClick={submitReset} className="bg-sky-700 hover:bg-sky-800 text-white" data-testid="reset-pwd-submit">{t("save")}</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("delete")} · {deleteTarget?.name}</AlertDialogTitle>
            <AlertDialogDescription>{t("confirm_delete")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-rose-600 hover:bg-rose-700 text-white" data-testid="confirm-delete-btn">{t("delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
