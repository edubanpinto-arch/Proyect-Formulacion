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

## Diagrama de contexto (arquitectura)

```mermaid
flowchart LR
    subgraph Campo["Transporte / Campo"]
        S["Sensor DS18B20"] -- OneWire GPIO 4 --> E["ESP32<br/>(firmware HMAC)"]
    end

    subgraph Servidor["Servidor"]
        API["Backend FastAPI<br/>/api/*<br/>JWT · 2FA · HMAC+Nonce<br/>Alertas · Auditoría · Exportación"]
        DB[("MongoDB<br/>users · devices · readings<br/>alerts · audit_log")]
        API <--> DB
    end

    WEB["Frontend React<br/>(Dashboard)"]
    ADM(["Administrador<br/>contraseña + 2FA"])
    TRA(["Transportador<br/>contraseña + clave del dispositivo"])
    TOTP["App autenticadora<br/>Google Authenticator / Authy"]

    E -- "POST /api/temperatura<br/>HTTPS JSON (firma HMAC)" --> API
    ADM --> WEB
    TRA --> WEB
    WEB -- "REST /api (JWT)" --> API
    ADM -. código TOTP .- TOTP
    API -- "CSV / PDF" --> WEB
```

| Actor / Componente | Rol |
|--------------------|-----|
| **ESP32 + DS18B20** | Mide la temperatura y la envía a la API cada pocos segundos (opcionalmente firmada con HMAC). |
| **Backend FastAPI** | Valida dispositivos, guarda lecturas, genera alertas, registra auditoría y exporta reportes. |
| **MongoDB** | Persistencia de usuarios, dispositivos, lecturas, alertas y auditoría. |
| **Frontend React** | Dashboard para administradores y transportadores. |
| **App autenticadora** | Genera el código 2FA de los administradores. |

## Tecnologías

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11, FastAPI, Motor (MongoDB async), JWT, pyotp, ReportLab |
| Frontend | React, Tailwind CSS, Shadcn UI, Axios |
| Base de datos | MongoDB |
| Hardware | ESP32 + DS18B20 (`ESP32_firmware_HMAC.ino`) |

## Estructura

```
backend/
  server.py        Capa API (endpoints FastAPI, autenticación, traducción de errores a HTTP)
  services.py      Servicios de aplicación y reglas de negocio de RF-01 y RF-02
  repositories.py  Capa de persistencia (consultas a MongoDB)
  models.py        Contratos de entrada (Pydantic)
  seed_demo.py     Datos de demostración idempotentes y reinicio de datos de prueba
  tests/           Pruebas funcionales y scripts de RNF
frontend/          Aplicación React (src/pages, src/components)
documentacion/     Entregas del curso y evidencias de pruebas
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

Crear `backend/.env` (o copiar `backend/.env.example`):

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=coldchain_db
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
Si la terminal no reconoce yarn como comando usar `npm install -g yarn`.

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

#### Diagrama de conexión DS18B20 → ESP32

El firmware usa el pin **GPIO 4** como bus OneWire (`ONE_WIRE_BUS = 4`).

```
        DS18B20 (sonda)                      ESP32 DevKit
   ┌──────────────────────┐
   │  Rojo     (VDD)  ────┼──────────┬───────── 3V3
   │                      │          │
   │                      │       [ 4.7 kΩ ]   ← resistencia pull-up
   │                      │          │
   │  Amarillo (DATA) ────┼──────────┴───────── GPIO 4
   │                      │
   │  Negro    (GND)  ────┼──────────────────── GND
   └──────────────────────┘
```

| Cable DS18B20 | Función | Pin ESP32 |
|---------------|---------|-----------|
| Rojo | Alimentación (VDD) | **3V3** |
| Amarillo (a veces blanco) | Datos (DQ) | **GPIO 4** |
| Negro | Tierra | **GND** |

Notas:
- La **resistencia de 4.7 kΩ entre DATA y 3V3 es obligatoria**; sin ella el sensor devuelve `-127 °C` o `85 °C`.
- Alimentar con **3.3 V** (no 5 V) para no exceder el nivel lógico del ESP32.
- En la versión TO-92 (encapsulado tipo transistor), con la cara plana hacia ti: pines **GND – DATA – VDD** de izquierda a derecha.
- Librerías necesarias en Arduino IDE: **OneWire** y **DallasTemperature**.
- Para usar otro pin, cambia `ONE_WIRE_BUS` en `ESP32_firmware_HMAC.ino`.

#### Configuración del firmware
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
| GET | `/api/alerts?active_only=true` | Listar alertas (RF-02) |
| POST | `/api/alerts/{id}/ack` | Reconocer alerta (RF-02) |
| POST | `/api/devices/{id}/alerts/ack-all` | Reconocer todas las alertas de un dispositivo (RF-02) |

Los contratos completos (entradas, respuestas y errores) están en `documentacion/ColdChain_Dashboard_Semana14_pruebas.md`.

## Pruebas (Semana 14)

Con el backend corriendo en `http://localhost:8001`, desde la carpeta `backend`:

```bash
# RF-01, RF-02 y RNF-01, 02, 05, 06 (25 pruebas, ~80 s)
REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/test_semana14_rf.py -v
#   Windows PowerShell: $env:REACT_APP_BACKEND_URL="http://localhost:8001"; pytest tests/test_semana14_rf.py -v

# RNF-03: latencia p95 de 100 lecturas (umbral 500 ms)
python tests/rnf03_latencia.py --base-url http://localhost:8001 --n 100 --out ../documentacion/evidencias/rnf03_latencia.json

# RNF-04: persistencia tras reiniciar backend y MongoDB (dos fases)
python tests/rnf04_reinicio.py antes   --base-url http://localhost:8001 --state ../documentacion/evidencias/rnf04_estado.json
#   ...reiniciar uvicorn y MongoDB...
python tests/rnf04_reinicio.py despues --base-url http://localhost:8001 --state ../documentacion/evidencias/rnf04_estado.json --out ../documentacion/evidencias/rnf04_reinicio.json

# Reiniciar datos de prueba (borra TEST_*) y cargar dispositivos demo
python seed_demo.py --reset
```

### Matriz RF-RNF (resultados del 2026-11-14)

| RF / RNF | Calidad ISO/IEC 25010:2023 | Meta | Resultado | Evidencia |
|----------|----------------------------|------|-----------|-----------|
| RF-01 / RNF-01 | Seguridad / Autenticidad | 100 % de contraseñas inválidas rechazadas (401) sin guardar | Cumple (10/10) | `tests/test_semana14_rf.py` |
| RF-01 / RNF-02 | Seguridad / Integridad | 100 % de HMAC inválido (401) y replay (409) rechazados | Cumple (5/5) | `tests/test_semana14_rf.py` |
| RF-01 / RNF-03 | Eficiencia / Comportamiento temporal | p95 ≤ 500 ms en 100 solicitudes | Cumple (p95 = 270 ms) | `documentacion/evidencias/rnf03_latencia.json` |
| RF-01 / RNF-04 | Fiabilidad / Recuperabilidad | 100 % de lecturas consultables tras reinicio | Cumple (20/20) | `documentacion/evidencias/rnf04_reinicio.json` |
| RF-02 / RNF-05 | Adecuación funcional / Corrección | 7 valores límite clasificados correctamente | Cumple (7/7) | `tests/test_semana14_rf.py` |
| RF-02 / RNF-06 | Fiabilidad / Ausencia de fallos | Inactivo tras más de 60 s sin lecturas | Cumple | `tests/test_semana14_rf.py` |

Detalle completo, contratos y checklist: `documentacion/ColdChain_Dashboard_Semana14_pruebas.pdf`.


## Semana 15 — Interfaz e integración del corte vertical

La Semana 15 incorpora la **capa de interfaz (React)** que consume los contratos vigentes de la API y demuestra ambos RF de extremo a extremo:

> **Interfaz → API → Servicio → Repositorio → Base de datos**

No se modifican los RF ni los RNF-01 a RNF-06: se conservan los identificadores, la prioridad y el alcance acordados en la Semana 14.

La novedad es la integración visual y la verificación de los flujos completos desde la pantalla.

### Diagrama de integración (corte vertical)

```mermaid
flowchart LR
    UI["Frontend React<br/>AdminDashboard · AlertsPanel · DeviceDetail"]
    API["Backend FastAPI<br/>server.py"]
    SVC["services.py<br/>IngestionService · AlertService"]
    REPO["repositories.py"]
    DB[("MongoDB<br/>readings · alerts")]

    UI -- "REST /api (Axios · JWT)" --> API
    API --> SVC
    SVC --> REPO
    REPO <--> DB
```

### RF y prioridad (sin cambios de alcance)

| RF | Prioridad | Acción desde la interfaz |
|---|---|---|
| **RF-01** | 1 (alta) | El administrador aprueba un dispositivo pendiente desde `AdminDashboard.jsx`; la siguiente lectura se persiste con su `reading_id` real y se ve en `DeviceDetail.jsx`. |
| **RF-02** | 2 | El administrador lista alertas en `AlertsPanel.jsx`, reconoce una (`ack`) y reconoce todas (`ack-all`). |

**Justificación de prioridad:**

RF-01 va primero porque RF-02 consume las lecturas que RF-01 valida y guarda.

### Componentes de la interfaz (Semana 15)

```text
frontend/
└── src/
    ├── AdminDashboard.jsx
    │   └── RF-01: Aprobación de dispositivos
    │       pendientes y panel de control.
    │
    ├── AlertsPanel.jsx
    │   └── RF-02: Lista de alertas y diálogo
    │       de reconocimiento (ack / ack-all).
    │
    └── DeviceDetail.jsx
        └── Detalle del dispositivo con
            lecturas y reading_id real.
```

**Endpoints consumidos por la interfaz:**

| Método | Endpoint | Función |
|---|---|---|
| API | `/api/devices/approve` | Aprobar dispositivos pendientes |
| API | `/api/alerts` | Consultar alertas |
| API | `/api/alerts/{id}/ack` | Reconocer una alerta |
| API | `/api/devices/{id}/alerts/ack-all` | Reconocer todas las alertas de un dispositivo |

La comunicación se realiza mediante **Axios**, utilizando la variable de entorno `REACT_APP_BACKEND_URL`.

### Escenarios de integración

Con el backend y el frontend en ejecución, preparar los datos iniciales:

```bash
python seed_demo.py --reset
```

**1. RF-01 — Aprobación de dispositivos y persistencia**

1. Iniciar sesión como administrador con autenticación 2FA.
2. Acceder a `AdminDashboard.jsx`.
3. Aprobar un dispositivo pendiente.
4. Enviar una lectura de temperatura.
5. Verificar que la lectura se almacena en MongoDB.
6. Comprobar el `reading_id` real en `DeviceDetail.jsx`.

**2. RF-02 — Gestión y reconocimiento de alertas**

1. Recargar la interfaz.
2. Acceder a `AlertsPanel.jsx`.
3. Listar las alertas generadas.
4. Abrir el diálogo de reconocimiento.
5. Reconocer una alerta mediante `ack`.
6. Ejecutar el reconocimiento general mediante `ack-all`.

**3. Casos de error**

| RF | Error HTTP | Escenario |
|---|---|---|
| RF-01 | **403 Forbidden** | Dispositivo no aprobado o credenciales inválidas, según el escenario documentado. |
| RF-02 | **404 Not Found** | Intento de reconocimiento individual de una alerta inexistente. |

### Guion breve de demostración

**Paso 1 — Presentación de los RF**

Presentar RF-01 y RF-02, explicando su prioridad.

RF-01 es prioritario porque RF-02 depende de las lecturas validadas y almacenadas por RF-01.

**Paso 2 — Demostración de RF-01**

Desde `AdminDashboard.jsx`:

- Aprobar un dispositivo pendiente.
- Enviar una lectura de temperatura.
- Verificar su almacenamiento.
- Comprobar el identificador real de lectura.

**Paso 3 — Demostración de RF-02**

Desde `AlertsPanel.jsx`:

- Listar las alertas del dispositivo.
- Abrir el diálogo de reconocimiento.
- Reconocer una alerta individual (`ack`).
- Ejecutar el reconocimiento general (`ack-all`).
- Mostrar los escenarios de error HTTP 403 y 404.

**Paso 4 — Identificación del corte vertical**

Localizar los siguientes componentes:

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Interfaz | `AdminDashboard.jsx` / `AlertsPanel.jsx` | Interacción con el usuario |
| API | `server.py` | Exposición de endpoints |
| Servicio | `services.py` | Lógica de negocio |
| Repositorio | `repositories.py` | Acceso a persistencia |
| Base de datos | MongoDB | Almacenamiento de lecturas y alertas |

**Paso 5 — Evidencia de calidad**

Explicar el cumplimiento de RNF-03:

- **RNF:** RNF-03.
- **Característica:** Eficiencia.
- **Métrica:** Tiempo de respuesta p95.
- **Meta:** Menor o igual a 500 ms.
- **Resultado:** 270,01 ms.
- **Estado:** Cumple.

Informar también el incumplimiento conocido de `ack-all`.

### Calidad y matriz RF–RNF

Los RNF-01 a RNF-06 fueron verificados durante la Semana 14.

Sus identificadores, condiciones, métricas, umbrales y resultados se mantienen sin modificaciones.

La Semana 15 consolida estas evidencias y agrega la verificación visual mediante **Playwright**.

**Reporte de pruebas de interfaz:**

```text
test_reports/iteration_4.json
```

**Resultados destacados:**

| RNF | Característica | Meta | Resultado | Estado |
|---|---|---|---|---|
| RNF-03 | Eficiencia | p95 ≤ 500 ms | 270,01 ms | Cumple |
| RNF-04 | Fiabilidad / Recuperabilidad | 20/20 lecturas consultables después del reinicio | 20/20 lecturas | Cumple |

**RNF-03 — Eficiencia**

El sistema registró un tiempo de respuesta p95 de **270,01 ms**, por debajo del límite de 500 ms establecido.

**RNF-04 — Fiabilidad y recuperabilidad**

Se verificó que las **20 de 20 lecturas** continuaban disponibles para consulta después de reiniciar el sistema.

### Limitación conocida

La funcionalidad **`ack-all` de RF-02** presenta una discrepancia en la integración.

**Estado de las operaciones:**

| Operación | Resultado |
|---|---|
| Reconocimiento individual (`ack`) | Funciona correctamente |
| Reconocimiento general (`ack-all`) | No cumple |

Esta limitación se informa explícitamente y no se oculta en los resultados.

Para mayor detalle, consultar la **Sección 9** del documento de la Semana 15.

### Documento de referencia

El análisis completo incluye:

- Matriz RF–RNF consolidada.
- Contratos de integración.
- Evidencias de ejecución.
- Resultados de pruebas.
- Limitaciones identificadas.
- Checklist final de verificación.

**Documento:**

```text
documentacion/
└── ColdChain_Dashboard_Semana15_Interfaz_integracion.pdf
```

### Conclusión de la Semana 15

La Semana 15 permite demostrar la integración del corte vertical del sistema ColdChain Dashboard, conectando la interfaz React con los servicios del backend FastAPI y la persistencia en MongoDB.

Se demuestra el flujo de aprobación de dispositivos, almacenamiento de lecturas y gestión de alertas desde la interfaz.

Los resultados de calidad se conservan respecto a la Semana 14 y se complementan con pruebas de interfaz mediante Playwright.

Se mantiene documentada la discrepancia de `ack-all` como una limitación pendiente de corrección.

