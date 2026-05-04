import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = not logged in, object = logged in
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setUser(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const setSession = (token, userObj) => {
    if (token) localStorage.setItem("cc_token", token);
    if (userObj) setUser(userObj);
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) {}
    localStorage.removeItem("cc_token");
    setUser(false);
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, setSession, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
