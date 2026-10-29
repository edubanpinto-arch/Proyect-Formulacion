import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem("cc_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      localStorage.setItem("cc_user", JSON.stringify(data));
      return data;
    } catch (e) {
      if (!localStorage.getItem("cc_token")) {
        setUser(false);
        localStorage.removeItem("cc_user");
      }
      return false;
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const setSession = (token, userObj) => {
    if (token) localStorage.setItem("cc_token", token);
    if (userObj) {
      localStorage.setItem("cc_user", JSON.stringify(userObj));
      setUser(userObj);
    }
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) {}
    localStorage.removeItem("cc_token");
    localStorage.removeItem("cc_user");
    setUser(false);
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, setSession, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
