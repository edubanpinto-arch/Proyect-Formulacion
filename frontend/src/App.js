import React from "react";
import { Routes, Route, Navigate, BrowserRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { I18nProvider } from "./lib/i18n";
import Login from "./pages/Login";
import AdminDashboard from "./pages/AdminDashboard";
import DeviceDetail from "./pages/DeviceDetail";
import TransporterPage from "./pages/Transporter";
import { Toaster } from "sonner";
import "./App.css";

function Protected({ children, role }) {
  const { user } = useAuth();
  
  const currentUser = user || (() => {
    try {
      const raw = localStorage.getItem("cc_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  const token = localStorage.getItem("cc_token");

  if (!token && !currentUser) {
    return <Navigate to="/login" replace />;
  }

  if (!currentUser) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-slate-500 mono">Cargando…</div>
      </div>
    );
  }

  if (role && currentUser.role !== role) {
    return <Navigate to={currentUser.role === "admin" ? "/dashboard" : "/transporter"} replace />;
  }

  return children;
}

function RootRedirect() {
  const { user } = useAuth();
  const currentUser = user || (() => {
    try {
      const raw = localStorage.getItem("cc_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();
  const token = localStorage.getItem("cc_token");

  if (!token && !currentUser) return <Navigate to="/login" replace />;
  if (!currentUser) return null;
  return <Navigate to={currentUser.role === "admin" ? "/dashboard" : "/transporter"} replace />;
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Toaster richColors position="top-right" />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/dashboard"
              element={<Protected role="admin"><AdminDashboard /></Protected>}
            />
            <Route
              path="/devices/:deviceId"
              element={<Protected role="admin"><DeviceDetail /></Protected>}
            />
            <Route
              path="/transporter"
              element={<Protected role="transporter"><TransporterPage /></Protected>}
            />
            <Route path="/" element={<RootRedirect />} />
            <Route path="*" element={<RootRedirect />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  );
}
