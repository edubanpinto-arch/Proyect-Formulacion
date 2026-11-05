# ColdChain Dashboard – PRD

## Original Problem Statement
Plataforma de monitoreo de cadena de frío (2°C – 8°C) para biológicos. Hardware ESP32 + DS18B20 hace POST cada 10s a `/api/temperatura` con `{deviceId, devicePassword, temperature}`. La app debe gestionar dispositivos pendientes/activos/inactivos, emitir alertas preventivas y críticas, y ofrecer dos vistas:
- Admin con 2FA TOTP, control total
- Transportador con login estándar + contraseña del hardware para ver SOLO su dispositivo

## Architecture
- **Backend:** FastAPI + Motor (async MongoDB), JWT (PyJWT), bcrypt, pyotp + qrcode
- **Frontend:** React 19 + react-router-dom 7, Tailwind, Shadcn/UI, Recharts
- **Idioma:** Bilingüe ES/EN (context propio)
- **DB:** MongoDB `coldchain_db`, colecciones: `users`, `devices`, `readings`, `alerts`, `events`

## User Personas
1. **Administrador (edubanpinto@gmail.com):** seguridad reforzada con 2FA TOTP, gestiona dispositivos, transportadores, alertas, ve todo.
2. **Transportador:** login simple; para visualizar el dispositivo necesita ingresar la contraseña única del hardware.
3. **Dispositivo ESP32:** cliente que postea `/api/temperatura` con su `devicePassword`.

## Core Requirements (static)
- Rango seguro 2°C–8°C, alerta preventiva ≤2.5° / ≥7.5°, crítica <2° / >8°
- Dispositivo nuevo → estado `pending` (no almacena lecturas hasta aprobación)
- Heartbeat: si no hay lectura en >60s → `inactive`
- Admin: 2FA obligatoria, cambio de contraseña en primer login
- Transportador solo ve su(s) dispositivo(s); auto-asignación al primer unlock con la contraseña correcta

## Implemented (2026-02)
- Auth completo: login → must_change_password → enroll_2fa (QR + secret) → verify_2fa → access
- Endpoints: `/api/auth/{login,change-password,2fa/enroll-verify,2fa/verify,me,logout}`
- Ingestión `/api/temperatura` (público) con auto-registro pending y verificación bcrypt de devicePassword
- Admin: `/api/devices`, `/devices/pending`, `/devices/approve`, `/devices/reject`, `/devices/{id}` (+ readings, alerts), `/alerts`, `/alerts/{id}/ack`, `/stats/summary`
- Transportador: `/api/transporter/access`, `/api/transporter/device/{id}`
- Gestión de transportadores (admin): `/api/admin/transporters` GET/POST
- UI: Login split-screen, AdminDashboard (KPIs + tabs Devices/Alerts/Transporters), DeviceDetail con TempChart (ReferenceArea zona segura), Transporter unlock + device view
- Internacionalización ES/EN, toggle visible
- Seeds: admin `edubanpinto@gmail.com / 1234567890` (must_change_password=true) y transportador demo `transportador@coldchain.com / transport123`
- Tests: 24/24 backend pytest + Playwright frontend ✅

## Docs (Nov 2026)
- README.md en español: descripción, ejecución local (Windows/Linux), diagrama de conexión DS18B20→ESP32 (GPIO 4 + pull-up 4.7kΩ), diagrama de contexto Mermaid de la arquitectura.
- Alertas por correo (Gmail SMTP) se implementaron y luego se RETIRARON a pedido del usuario. No reintroducir sin que lo pida.

## Backlog / Next Up
- **P1:** Rate limiting / brute-force lockout en `/api/auth/login`
- **P1:** Notificaciones push browser (web push)
- **P2:** Endpoint protegido del ESP32 con HMAC + nonce (mitigar replay)
- **P2:** Histórico exportable CSV/PDF de un dispositivo
- **P2:** Mapa con ubicación GPS del dispositivo (si el ESP32 envía coordenadas)
- **P2:** Multi-tenant (clínicas/distribuidores)
