import React from "react";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { Snowflake, LogOut, Globe, KeyRound, ChevronDown } from "lucide-react";
import { Button } from "./ui/button";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel } from "./ui/dropdown-menu";
import { Link, useLocation } from "react-router-dom";
import { useState } from "react";
import ChangeMyPasswordDialog from "./ChangeMyPasswordDialog";

export default function Topbar() {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const loc = useLocation();
  const isAdmin = user && user.role === "admin";
  const [openPwd, setOpenPwd] = useState(false);

  return (
    <header className="sticky top-0 z-30 bg-white border-b border-slate-200" data-testid="topbar">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to={isAdmin ? "/dashboard" : "/transporter"} className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-md bg-sky-700 text-white grid place-items-center">
              <Snowflake size={18} />
            </div>
            <div className="font-heading font-semibold text-slate-900">ColdChain</div>
          </Link>
          <div className="hidden md:block ml-2 px-2 py-0.5 text-[10px] uppercase tracking-[0.2em] rounded bg-emerald-50 text-emerald-700 border border-emerald-200 mono">
            {t("range_2_8")}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            data-testid="lang-toggle"
            onClick={() => setLang(lang === "es" ? "en" : "es")}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600"
          >
            <Globe size={14} /> {lang.toUpperCase()}
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                data-testid="user-menu-trigger"
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-50 border border-slate-200 hover:bg-slate-100"
              >
                <div className="text-xs text-left">
                  <div className="text-slate-900 font-medium">{user?.name}</div>
                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                    {isAdmin ? t("role_admin") : t("role_transporter")}
                  </div>
                </div>
                <ChevronDown size={14} className="text-slate-400" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[220px]">
              <DropdownMenuLabel className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{user?.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem data-testid="menu-change-password" onClick={() => setOpenPwd(true)}>
                <KeyRound size={14} className="mr-2" /> {t("change_my_password")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem data-testid="menu-logout" onClick={logout} className="text-rose-700">
                <LogOut size={14} className="mr-2" /> {t("logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button onClick={logout} variant="ghost" data-testid="logout-btn" className="sm:hidden text-slate-600 hover:text-slate-900 hover:bg-slate-100">
            <LogOut size={16} className="mr-1.5" />
            {t("logout")}
          </Button>
        </div>
      </div>
      <ChangeMyPasswordDialog open={openPwd} onOpenChange={setOpenPwd} />
    </header>
  );
}
