# ColdChain Dashboard — Monitoreo de Cadena de Frío para Biológicos

Plataforma web para monitorear y gestionar la cadena de frío de biológicos (vacunas) que deben mantenerse entre **2 °C y 8 °C**. Dispositivos **ESP32** con sensores **DS18B20** envían lecturas de temperatura a la API, y el dashboard las muestra en tiempo real con alertas visuales.

## Funcionalidades principales

- **Roles**
  - **Administrador**: control total, protegido con contraseña + **2FA (TOTP)** (Google Authenticator / Authy).
  - **Transportador**: solo ve los dispositivos que transporta, ingresando la contraseña física del hardware.
- **Aprobación de dispositivos**: todo ESP32 nuevo queda "Pendiente" hasta que un administrador lo aprueba.
- **Alertas** cuando la temperatura sale del rango 2–8 °C (advertencia / crítica) con reconocimiento.
- **Modo Seguro (HMAC-SHA256 + Nonce)**: firma de cada lectura y protección anti-replay por dispositivo.
- **Exportación** de lecturas por dispositivo en **CSV** y **PDF**.
- **Gestión de usuarios**: crear, deshabilitar, restablecer contraseña y cambio de contraseña propio.
- **Auditoría**: registro de quién hizo qué, cuándo y desde qué IP.
- Interfaz en **Español / Inglés**.

## Tecnologías

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11, FastAPI, Motor (MongoDB async), JWT, pyotp, ReportLab |
| Frontend | React, Tailwind CSS, Shadcn UI, Axios |
| Base de datos | MongoDB |
| Hardware | ESP32 + DS18B20 (`ESP32_firmware_HMAC.ino`) |

## Estructura

```
backend/     API FastAPI (server.py, auth.py, models.py)
frontend/    Aplicación React (src/pages, src/components)
ESP32_firmware_HMAC.ino   Firmware de ejemplo para el ESP32
```

## Ejecución local

### Requisitos
- Python 3.11
- Node.js 20 y Yarn (`npm install -g yarn`)
- MongoDB en ejecución (local o MongoDB Atlas)

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> Si `pip` falla con `emergentintegrations` o `uvloop`, elimina esas líneas de `requirements.txt` (no son necesarias para este proyecto).

Crear `backend/.env`:

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=coldchain
CORS_ORIGINS=http://localhost:3000
JWT_SECRET=una_clave_larga_y_aleatoria
ADMIN_EMAIL=admin@ejemplo.com
ADMIN_PASSWORD=cambiar_esta_clave
```

Iniciar el servidor:

```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Al arrancar se crea automáticamente el administrador definido en `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Documentación de la API: http://localhost:8001/docs

### 2. Frontend

```bash
cd frontend
yarn install
```

Crear `frontend/.env`:

```
REACT_APP_BACKEND_URL=http://localhost:8001
```

Iniciar:

```bash
yarn start
```

Abrir http://localhost:3000. En el primer inicio de sesión el administrador debe **cambiar su contraseña** y **configurar el 2FA** escaneando el código QR.

### 3. Conectar el ESP32

1. En el firmware, configurar el WiFi y la URL del servidor usando la IP de la PC (no `localhost`), por ejemplo:
   `http://192.168.1.50:8001/api/temperatura`
2. El ESP32 y la PC deben estar en la misma red, con el puerto **8001** permitido en el firewall.
3. Al enviar la primera lectura, el dispositivo aparece como **Pendiente** en el dashboard; un administrador debe aprobarlo.

Ejemplo de lectura enviada por el ESP32:

```json
POST /api/temperatura
{
  "deviceId": "ESP32_VACUNA_001",
  "devicePassword": "PASS_SECRETA_123",
  "temperature": 5.4
}
```

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/login` | Inicio de sesión |
| POST | `/api/temperatura` | Ingesta de lecturas del ESP32 |
| GET | `/api/devices` | Lista de dispositivos |
| POST | `/api/devices/approve` | Aprobar dispositivo |
| GET | `/api/devices/{id}/export?format=csv\|pdf` | Exportar lecturas |
| POST | `/api/devices/{id}/secure-mode` | Activar/desactivar Modo Seguro |
| GET | `/api/admin/users` | Gestión de usuarios |
| GET | `/api/admin/audit` | Registro de auditoría |
