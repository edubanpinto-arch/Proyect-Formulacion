import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatErr } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card } from "../components/ui/card";
import { ShieldCheck, Snowflake, Globe } from "lucide-react";
import { toast } from "sonner";

const HERO_IMG = "https://images.unsplash.com/photo-1716643863806-989dd76ae093?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzF8MHwxfHNlYXJjaHwyfHxjbGVhbiUyMGxhYm9yYXRvcnklMjB3YXJlaG91c2V8ZW58MHx8fHwxNzc3OTA1ODUyfDA&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { user, setUser, setSession, refresh } = useAuth();
  const { t, lang, setLang } = useI18n();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState("login"); // login | change_password | enroll_2fa | verify_2fa
  const [tempToken, setTempToken] = useState(null);
  const [enrollData, setEnrollData] = useState(null);
  const [code, setCode] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [newPwd2, setNewPwd2] = useState("");
  const [loading, setLoading] = useState(false);

  // If already authenticated, redirect immediately
  React.useEffect(() => {
    if (user) {
      const target = user.role === "admin" ? "/dashboard" : "/transporter";
      navigate(target, { replace: true });
    }
  }, [user, navigate]);

  const handleSuccess = (token, userObj) => {
    if (token) localStorage.setItem("cc_token", token);
    if (userObj) {
      localStorage.setItem("cc_user", JSON.stringify(userObj));
      setUser(userObj);
    }
    const target = userObj?.role === "admin" ? "/dashboard" : "/transporter";
    navigate(target, { replace: true });
  };

  const submitLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      if (data.step === "change_password") {
        setTempToken(data.temp_token);
        setStep("change_password");
      } else if (data.step === "enroll_2fa") {
        setTempToken(data.temp_token);
        setEnrollData({ secret: data.secret, qr: data.qr_data_url });
        setStep("enroll_2fa");
      } else if (data.step === "verify_2fa") {
        setTempToken(data.temp_token);
        setStep("verify_2fa");
      } else if (data.step === "ok") {
        if (data.user) {
          handleSuccess(data.access_token, data.user);
        } else {
          if (data.access_token) localStorage.setItem("cc_token", data.access_token);
          const u = await refresh();
          if (u) handleSuccess(data.access_token, u);
        }
      }
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail, t("invalid_credentials")));
    } finally {
      setLoading(false);
    }
  };

  const submitChangePwd = async (e) => {
    e.preventDefault();
    if (newPwd !== newPwd2) {
      toast.error("Las contraseñas no coinciden");
      return;
    }
    if (newPwd.length < 8) {
      toast.error("Mínimo 8 caracteres");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/change-password", {
        temp_token: tempToken,
        new_password: newPwd,
      });
      if (data.step === "enroll_2fa") {
        setTempToken(data.temp_token);
        setEnrollData({ secret: data.secret, qr: data.qr_data_url });
        setStep("enroll_2fa");
      } else if (data.step === "ok") {
        if (data.user) {
          handleSuccess(data.access_token, data.user);
        } else {
          if (data.access_token) localStorage.setItem("cc_token", data.access_token);
          const u = await refresh();
          if (u) handleSuccess(data.access_token, u);
        }
      }
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail));
    } finally { setLoading(false); }
  };

  const submitEnroll = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/2fa/enroll-verify", { temp_token: tempToken, code });
      if (data.user) {
        handleSuccess(data.access_token, data.user);
      } else {
        if (data.access_token) localStorage.setItem("cc_token", data.access_token);
        const u = await refresh();
        if (u) handleSuccess(data.access_token, u);
      }
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail, t("wrong_code")));
    } finally { setLoading(false); }
  };

  const submitVerify = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/2fa/verify", { temp_token: tempToken, code });
      if (data.user) {
        handleSuccess(data.access_token, data.user);
      } else {
        if (data.access_token) localStorage.setItem("cc_token", data.access_token);
        const u = await refresh();
        if (u) handleSuccess(data.access_token, u);
      }
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail, t("wrong_code")));
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2" data-testid="login-page">
      {/* Left - form */}
      <div className="flex flex-col p-8 lg:p-14 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-md bg-sky-700 text-white grid place-items-center">
              <Snowflake size={18} strokeWidth={2} />
            </div>
            <div className="font-heading font-semibold text-slate-900 text-lg">{t("app_title")}</div>
          </div>
          <button
            data-testid="lang-toggle"
            onClick={() => setLang(lang === "es" ? "en" : "es")}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600"
          >
            <Globe size={14} /> {lang.toUpperCase()}
          </button>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-sm">
            {step === "login" && (
              <form onSubmit={submitLogin} className="space-y-5" data-testid="login-form">
                <div>
                  <h1 className="text-3xl sm:text-4xl font-heading font-semibold text-slate-900 tracking-tight">{t("sign_in")}</h1>
                  <p className="text-sm text-slate-500 mt-1.5">{t("app_subtitle")}</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("email")}</Label>
                  <Input id="email" data-testid="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("password")}</Label>
                  <Input id="password" data-testid="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
                <Button data-testid="login-submit" type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11">
                  {loading ? "…" : t("enter")}
                </Button>
              </form>
            )}

            {step === "change_password" && (
              <form onSubmit={submitChangePwd} className="space-y-5" data-testid="change-password-form">
                <div>
                  <h1 className="text-2xl font-heading font-semibold text-slate-900">{t("must_change_password_title")}</h1>
                  <p className="text-sm text-slate-500 mt-1">{t("must_change_password_desc")}</p>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("new_password")}</Label>
                  <Input data-testid="change-pwd-new" type="password" required value={newPwd} onChange={(e) => setNewPwd(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("confirm_password")}</Label>
                  <Input data-testid="change-pwd-confirm" type="password" required value={newPwd2} onChange={(e) => setNewPwd2(e.target.value)} />
                </div>
                <Button data-testid="change-pwd-submit" type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11">
                  {t("save")}
                </Button>
              </form>
            )}

            {step === "enroll_2fa" && enrollData && (
              <form onSubmit={submitEnroll} className="space-y-5" data-testid="enroll-2fa-form">
                <div>
                  <h1 className="text-2xl font-heading font-semibold text-slate-900 flex items-center gap-2">
                    <ShieldCheck size={22} /> {t("enroll_2fa_title")}
                  </h1>
                  <p className="text-sm text-slate-500 mt-1">{t("enroll_2fa_desc")}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 flex flex-col items-center">
                  <img src={enrollData.qr} alt="QR" className="w-44 h-44 rounded-md bg-white p-1" data-testid="totp-qr" />
                  <div className="mt-3 text-xs text-slate-500 uppercase tracking-[0.18em]">{t("secret_key")}</div>
                  <div className="mono text-sm text-slate-700 select-all break-all" data-testid="totp-secret">{enrollData.secret}</div>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("code")}</Label>
                  <Input data-testid="totp-code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="mono tracking-widest text-center text-lg" />
                </div>
                <Button data-testid="enroll-2fa-submit" type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11">
                  {t("verify")}
                </Button>
              </form>
            )}

            {step === "verify_2fa" && (
              <form onSubmit={submitVerify} className="space-y-5" data-testid="verify-2fa-form">
                <div>
                  <h1 className="text-2xl font-heading font-semibold text-slate-900 flex items-center gap-2">
                    <ShieldCheck size={22} /> {t("verify_2fa_title")}
                  </h1>
                  <p className="text-sm text-slate-500 mt-1">{t("verify_2fa_desc")}</p>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-[0.18em] text-slate-500">{t("code")}</Label>
                  <Input data-testid="verify-totp-code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="mono tracking-widest text-center text-lg" />
                </div>
                <Button data-testid="verify-2fa-submit" type="submit" disabled={loading} className="w-full bg-sky-700 hover:bg-sky-800 text-white h-11">
                  {t("verify")}
                </Button>
              </form>
            )}
          </div>
        </div>

        <div className="text-xs text-slate-400 mono mt-6">v1.0 · ColdChain · 2 — 8°C</div>
      </div>

      {/* Right - hero */}
      <div className="hidden lg:block relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${HERO_IMG})` }}
        />
        <div className="absolute inset-0 bg-gradient-to-br from-sky-900/70 via-sky-900/30 to-slate-900/40" />
        <div className="relative h-full flex flex-col justify-end p-12 text-white">
          <div className="text-xs uppercase tracking-[0.3em] mb-3 opacity-80">{t("range_2_8")}</div>
          <div className="font-heading text-3xl font-semibold leading-tight max-w-md">
            Trazabilidad y precisión térmica para preservar la cadena de frío.
          </div>
        </div>
      </div>
    </div>
  );
}
