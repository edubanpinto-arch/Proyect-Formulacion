# ColdChain Dashboard – Semana 14: Lógica de negocio, API y pruebas del corte vertical

**Curso:** Arquitectura de Sistemas I · **Semana:** 14 (semana 2 del tercer corte) · **Fecha de ejecución de pruebas:** 2026-11-14

Este documento continúa `ColdChain_Dashboard_Semana13_Persistencia`. Se conservan los identificadores, la prioridad y el alcance de los dos RF y de los RNF-01 a RNF-06.

## 1. Requerimientos funcionales (sin cambios de alcance)

| RF | Prioridad | Descripción |
|----|-----------|-------------|
| RF-01 | 1 | El sistema recibe lecturas de temperatura de un ESP32, valida el dispositivo y las persiste solo si está aprobado. |
| RF-02 | 2 | El sistema evalúa cada lectura contra el rango 2-8 °C, genera alertas críticas o preventivas y permite al administrador listarlas y reconocerlas. |

RF-01 va primero porque RF-02 consume las lecturas que RF-01 valida y guarda.

**Ajustes justificados (no cambian el alcance):**

- Se agregó una regla de entrada a RF-01: la temperatura debe estar en el rango físico del DS18B20 (-55 a 125 °C). El valor -127 °C que entrega el sensor desconectado se rechaza con 422 y no se guarda.
- Reconocer una alerta inexistente ahora devuelve **404**. Antes devolvía 200 sin cambios.
- Se agregó `POST /api/devices/{device_id}/alerts/ack-all` para reconocer todas las alertas de un dispositivo. Usa el mismo caso de uso de reconocimiento de RF-02.

## 2. Arquitectura del backend

Flujo: **API (FastAPI) → Servicio de aplicación → Repositorio → MongoDB**.

| Capa | Archivo | Responsabilidad |
|------|---------|-----------------|
| API | `backend/server.py` | Recibe HTTP, valida el formato con Pydantic (`models.py`), autentica y delega en el servicio. Traduce las excepciones de dominio a códigos HTTP con un manejador global. |
| Servicio | `backend/services.py` | Contiene `IngestionService` (RF-01) y `AlertService` (RF-02). Ahí viven las reglas de negocio: aprobación, contraseña del dispositivo, HMAC y nonce, clasificación 2-8 °C e inactividad. No depende de HTTP. |
| Dominio | `backend/services.py` | `classify_temperature`, `compute_hmac`, `device_live_status` y las excepciones `InvalidCredentials` (401), `Forbidden` (403), `NotFound` (404) y `Conflict` (409). |
| Persistencia | `backend/repositories.py` | `DeviceRepository`, `ReadingRepository`, `AlertRepository` y `EventRepository` encapsulan todas las consultas de RF-01 y RF-02. Traducen `DuplicateKeyError` a `DuplicateDevice`. |

**Conexiones y escrituras:**

- Se usa un único `AsyncIOMotorClient` por proceso, con su pool de conexiones. Se crea al arrancar y se cierra en el evento `shutdown`. Los repositorios no abren conexiones propias.
- MongoDB corre en modo standalone, sin transacciones multi-documento. Por eso RF-01 ordena sus escrituras así:
  1. Insertar la lectura.
  2. Actualizar `last_seen`, `last_temperature` y `last_nonce` del dispositivo.
  3. Insertar la alerta, si corresponde.

  La respuesta 200 se envía solo después de confirmar estas escrituras (`insert_one`/`update_one` con write concern por defecto).
- **Riesgo documentado:** si el proceso cae entre los pasos 1 y 3, puede quedar una lectura sin su alerta. El riesgo es aceptado para el prototipo. La mitigación prevista es un replica set con transacciones.
- **Registros simultáneos:** el índice único `devices.device_id` complementa la comprobación del servicio. Si dos ESP32 se registran a la vez con el mismo ID, el `DuplicateKeyError` se traduce a **409 controlado**, no a un error 500.
- **Reintentos:** si el ESP32 pierde una respuesta, reenvía con un nonce nuevo. El nonce repetido se rechaza con 409, así que no se duplica la misma lectura firmada.
- Cualquier error no previsto se registra en el log del servidor con la traza y se responde `500 {"detail": "Error interno del servidor."}`, sin exponer detalles técnicos.

## 3. Servicios por RF (Actividad 1)

| RF | Servicio y método | Entrada | Reglas / condiciones | Métodos de repositorio | Resultado válido | Rechazo esperado |
|----|-------------------|---------|----------------------|------------------------|------------------|------------------|
| RF-01 | `IngestionService.ingest` | `deviceId`, `devicePassword`, `temperature`; `nonce` y `signature` opcionales | (1) Un dispositivo desconocido se registra como `pending`. (2) La contraseña se compara contra el hash bcrypt. (3) Si `require_hmac` está activo o viene firma: HMAC válido y `nonce` mayor que `last_nonce`. (4) `rejected` se bloquea; `pending` no guarda la lectura. (5) Solo `approved` persiste. | `DeviceRepository.find_by_device_id`, `insert`, `update_fields`; `ReadingRepository.insert`; `EventRepository.insert` | 200 `status=active` con el `reading_id` real | 401 (contraseña o firma), 403 (rechazado), 409 (replay o registro simultáneo), 422 (formato o rango físico) |
| RF-02 | `AlertService.evaluate` (invocado por RF-01) | Dispositivo, temperatura, `ts` | Menor que 2 o mayor que 8 °C: `critical`. Entre 2 y 2,5 °C o entre 7,5 y 8 °C (límites incluidos): `warning`. Otro valor: sin alerta. | `AlertRepository.insert` | Alerta guardada y `alert` en la respuesta de RF-01 | — |
| RF-02 | `AlertService.list_alerts` / `list_device_alerts` | `active_only`; `device_id` | Solo administradores. El dispositivo debe existir. | `AlertRepository.list`, `list_by_device`; `DeviceRepository.exists` | 200 con la lista ordenada por `ts` descendente | 401, 403, 404 |
| RF-02 | `AlertService.acknowledge` / `acknowledge_device` | `alert_id`; `device_id` | La alerta o el dispositivo deben existir. Se registra quién reconoce y cuándo. | `AlertRepository.find_by_id`, `acknowledge`, `acknowledge_all_for_device` | 200 con la alerta reconocida o con `count` | 401, 403, 404 |

## 4. Contratos de la API (Actividad 2)

URL base local: `http://localhost:8001`. Todas las rutas llevan el prefijo `/api`. Las fechas se manejan como texto ISO 8601 en UTC. Los endpoints de administrador requieren `Authorization: Bearer <token>`, que se obtiene con login + 2FA.

**Variantes de formato documentadas:**

- La validación de formato la hace FastAPI y responde **422** con `detail` como **lista** de errores (`loc`, `msg`, `type`). Los errores de negocio responden con `detail` como **texto**.
- El cuerpo de RF-01 usa `deviceId` y `devicePassword` en camelCase, en lugar del snake_case que recomienda la guía. Se mantienen para no romper el firmware ESP32 ya desplegado.

| RF | Método y ruta | Entrada | Éxito | Errores | Servicio |
|----|---------------|---------|-------|---------|----------|
| RF-01 | `POST /api/temperatura` (pública, para el ESP32) | JSON `deviceId` (1-64 caracteres), `devicePassword` (1-128), `temperature` (número entre -55 y 125); `nonce` (entero ≥ 0) y `signature` (hex) opcionales | 200 `pending` o `active` | 401, 403, 409, 422, 500 | `IngestionService.ingest` |
| RF-01 | `GET /api/devices/{device_id}/readings?limit=200` (admin) | `device_id` en la ruta; `limit` entre 1 y 5000 | 200 con lista de lecturas | 401, 403, 422 | Consulta de soporte |
| RF-01 | `POST /api/devices/approve` / `POST /api/devices/reject` (admin) | `{"device_id": "..."}` | 200 | 401, 403, 404 | Soporte de RF-01 |
| RF-02 | `GET /api/alerts?active_only=true\|false` (admin) | Query opcional | 200 con lista de alertas | 401, 403 | `AlertService.list_alerts` |
| RF-02 | `GET /api/devices/{device_id}/alerts` (admin) | `device_id` | 200 con lista | 401, 403, 404 | `AlertService.list_device_alerts` |
| RF-02 | `POST /api/alerts/{alert_id}/ack` (admin) | `alert_id`, sin cuerpo | 200 `{"ok": true, "alert": {...}}` | 401, 403, 404 | `AlertService.acknowledge` |
| RF-02 | `POST /api/devices/{device_id}/alerts/ack-all` (admin) | `device_id`, sin cuerpo | 200 `{"ok": true, "count": n}` | 401, 403, 404 | `AlertService.acknowledge_device` |

### 4.1 RF-01: ingesta (ejemplos reales del backend)

```
POST /api/temperatura
{"deviceId": "ESP32_VACUNA_001", "devicePassword": "Clave_Doc", "temperature": 5.4}

HTTP 200 (primer contacto)
{"ok": true, "status": "pending", "message": "Dispositivo registrado, esperando aprobación"}

HTTP 200 (dispositivo aprobado)
{"ok": true, "status": "active", "reading_id": "162c98c0-65f8-4796-9783-1298a780b864", "alert": null}

HTTP 200 (aprobado, 8.6 °C)
{"ok": true, "status": "active", "reading_id": "b2db5a38-...", "alert": "critical"}

HTTP 401  {"detail": "Contraseña del dispositivo inválida"}
HTTP 401  {"detail": "Firma HMAC inválida"}
HTTP 401  {"detail": "Falta nonce/signature (modo seguro activo)"}
HTTP 403  {"detail": "Dispositivo rechazado"}
HTTP 409  {"detail": "Nonce reutilizado (replay)"}
HTTP 409  {"detail": "El dispositivo ya está registrado; reintente el envío."}
HTTP 422  {"detail": [{"type": "greater_than_equal", "loc": ["body", "temperature"],
           "msg": "Input should be greater than or equal to -55", "input": -127, ...}]}
```

Firma HMAC: `HMAC-SHA256(clave=devicePassword, mensaje="{deviceId}|{nonce}|{temperature con 2 decimales}")` en hexadecimal.

### 4.2 RF-02: alertas (ejemplos reales del backend)

```
GET /api/alerts?active_only=true
HTTP 200
[{"id": "ee57e2a0-2c6a-4efb-93b9-bd6cb96e1d74", "device_id": "TEST_DOC_ESP32",
  "device_name": "TEST_DOC_ESP32", "severity": "critical", "type": "temperature_out_of_range",
  "message": "TEMPERATURA FUERA DE RANGO (8.60°C). Cadena de frío comprometida.",
  "temperature": 8.6, "ts": "2026-11-14T23:52:39.525846+00:00", "acknowledged": false}]

POST /api/alerts/ee57e2a0-2c6a-4efb-93b9-bd6cb96e1d74/ack
HTTP 200 {"ok": true, "alert": {..., "acknowledged": true, "acknowledged_by": "<admin>", "acknowledged_at": "..."}}

POST /api/alerts/00000000-0000-0000-0000-000000000000/ack
HTTP 404 {"detail": "La alerta no existe."}

POST /api/devices/NO_EXISTE/alerts/ack-all
HTTP 404 {"detail": "El dispositivo no existe."}

GET /api/alerts   (sin token)
HTTP 401 {"detail": "Not authenticated"}
```

## 5. Pruebas funcionales con base real (Actividad 3)

**Archivo:** `backend/tests/test_semana14_rf.py`, con 25 casos que pasan HTTP → API → servicio → repositorio → MongoDB.

**Persistencia:** se verifica con **otra conexión** (`pymongo.MongoClient`, independiente del backend).

**Datos de prueba:**
- Cada ejecución usa dispositivos con el prefijo `TEST_S14_<aleatorio>_` y un administrador temporal con 2FA.
- Todo se elimina al terminar, así que la prueba se puede repetir sobre la misma base.

**Evidencias:**
- `documentacion/evidencias/pytest_semana14.xml`
- `documentacion/evidencias/pytest_semana14.txt`

| RF / prueba | Estado inicial | Acción | Resultado esperado | Resultado obtenido |
|-------------|----------------|--------|--------------------|--------------------|
| RF-01 registro | `device_id` inexistente | POST 5.0 °C | 200 `pending`; dispositivo `pending` con hash; 0 lecturas | Cumple |
| RF-01 pendiente | Dispositivo `pending` | POST 6.0 °C | 200 `pending`; 0 lecturas | Cumple |
| RF-01 válido | Dispositivo aprobado | POST 5.25 °C | 200 `active` y `reading_id` real; la lectura se recupera desde otra conexión y por `GET /readings` | Cumple |
| RF-01 unicidad | `device_id` inexistente | 8 POST simultáneos | Exactamente 1 documento en `devices`; respuestas solo 200 o 409, sin 500 | Cumple |
| RF-01 entrada | — | Sin `deviceId`, sin contraseña, sin temperatura, temperatura "abc", -127 °C o `deviceId` vacío (6 casos) | 422; las cantidades de `devices` y `readings` no cambian | Cumple (6/6) |
| RF-01 rechazado | Dispositivo rechazado | POST 5.0 °C | 403; 0 lecturas | Cumple |
| RF-01 ausencia | — | `GET /devices/{inexistente}` y `/alerts` | 404 controlado | Cumple |
| RF-02 límites | Dispositivo aprobado | 1,9; 2,0; 2,5; 5,0; 7,5; 8,0; 8,1 °C | crítica; preventiva; preventiva; ninguna; preventiva; preventiva; crítica. Se crea +1 alerta solo cuando corresponde | Cumple (7/7) |
| RF-02 listar y reconocer | 2 alertas (9,0 y 7,6 °C) | GET `/alerts`, ack de una y ack-all | La lista contiene ambas sin `_id`; la alerta reconocida queda guardada con el actor; `active_only` la excluye; ack-all devuelve `count=1` | Cumple |
| RF-02 ausencia | — | ack de un id inexistente; ack-all de un dispositivo inexistente | 404; ninguna alerta cambia de estado | Cumple |
| RF-02 acceso | — | Sin token; con token de transportador | 401; 403 | Cumple |

**Regresión de toda la API:** 98 de 98 pruebas pasan (`documentacion/evidencias/pytest_regresion_completa.txt`). Esto incluye las 25 nuevas y las suites anteriores de usuarios, auditoría y multidispositivo.

## 6. Verificación de RNF (Actividad 4)

**Entorno de medición:**

| Elemento | Valor |
|----------|-------|
| Sistema | Linux 6.12 aarch64, 16 CPU (contenedor de vista previa) |
| Software | Python 3.11.18, FastAPI 0.110.1, MongoDB 7.0.45 local |
| Ubicación | API y base en el mismo equipo; cliente en el mismo equipo hacia `http://localhost:8001` |
| Caché | Sin caché de aplicación |

| RNF | ISO/IEC 25010:2023 | Escenario y medida | Umbral | Resultado observado | Estado | Evidencia |
|-----|--------------------|--------------------|--------|---------------------|--------|-----------|
| RNF-01 | Seguridad / Autenticidad | 10 lecturas con contraseña inválida a un dispositivo aprobado | 100 % rechazadas (401) sin guardarse | 10/10 con 401; 0 lecturas nuevas | **Verificado** | `test_rnf01_password_invalida_rechazada_100` |
| RNF-02 | Seguridad / Integridad | Firma alterada, temperatura manipulada, falta de firma en modo seguro, nonce repetido y nonce menor | 100 % rechazadas (401 por firma, 409 por replay) | 3/3 con 401 y 2/2 con 409; 0 lecturas nuevas; `last_nonce` sin cambios | **Verificado** | `TestRNF02::test_firma_y_nonce` |
| RNF-03 | Eficiencia de desempeño / Comportamiento temporal | 100 POST consecutivos de un dispositivo aprobado, MongoDB local, medición HTTP completa desde el cliente | p95 ≤ 500 ms | p50 266,96 ms; **p95 270,01 ms**; máx. 290,01 ms; 100/100 con 200; 101 lecturas guardadas | **Verificado** | `backend/tests/rnf03_latencia.py` → `evidencias/rnf03_latencia.json` |
| RNF-04 | Fiabilidad / Recuperabilidad | 20 lecturas confirmadas con 200; reinicio de MongoDB y backend (`supervisorctl restart mongodb backend`); consulta por API | 100 % siguen consultables | 20/20 (100 %); 20 antes y 20 después | **Verificado** | `backend/tests/rnf04_reinicio.py` → `evidencias/rnf04_reinicio.json` |
| RNF-05 | Adecuación funcional / Corrección funcional | 1,9; 2,0; 2,5; 5,0; 7,5; 8,0; 8,1 °C | 100 % coinciden con la regla de RF-02 | 7/7 (100 %) | **Verificado** (antes parcial) | `test_rnf05_clasificacion_limites[*]` |
| RNF-06 | Fiabilidad / Ausencia de fallos | Dispositivo aprobado que envía una lectura y luego deja de enviar; espera real de 65 s | Estado `inactive` tras más de 60 s | `active` al enviar, `inactive` a los 65 s | **Verificado** | `test_rnf06_inactivo_tras_60s` |

**Observaciones:**

- **RNF-03:**
  - Casi todo el tiempo de respuesta (~265 ms) se va en verificar con bcrypt la contraseña del dispositivo en cada lectura. Es una decisión de seguridad (RNF-01).
  - El margen frente al umbral es de unos 230 ms. Si el hardware de producción es más lento, el ajuste sería cachear la verificación por sesión de dispositivo o usar solo HMAC en modo seguro.
  - La prueba es secuencial con un cliente. No demuestra el comportamiento con concurrencia ni con otros volúmenes.
- **RNF-04:** se ejecutó en el entorno Linux de vista previa. En Windows se repite con el mismo script, reiniciando manualmente uvicorn y el servicio MongoDB (`net stop MongoDB` y `net start MongoDB`).

## 7. Matriz RF-RNF con evidencias

| RF / RNF | Calidad ISO/IEC 25010:2023 | Prueba y meta | Resultado y evidencia |
|----------|----------------------------|---------------|-----------------------|
| RF-01 / RNF-01 | Seguridad / Autenticidad | Contraseña inválida: 100 % con 401 sin guardar | Cumple: 10/10. `tests/test_semana14_rf.py::test_rnf01_password_invalida_rechazada_100` |
| RF-01 / RNF-02 | Seguridad / Integridad | HMAC inválido 401 y replay 409: 100 % | Cumple: 5/5. `tests/test_semana14_rf.py::TestRNF02` |
| RF-01 / RNF-03 | Eficiencia / Comportamiento temporal | 100 solicitudes; p95 ≤ 500 ms | Cumple: p95 = 270,01 ms. `evidencias/rnf03_latencia.json` |
| RF-01 / RNF-04 | Fiabilidad / Recuperabilidad | Reinicio de backend y MongoDB; 100 % consultables | Cumple: 20/20. `evidencias/rnf04_reinicio.json` |
| RF-02 / RNF-05 | Adecuación funcional / Corrección | 7 valores límite; 100 % correctos | Cumple: 7/7. `tests/test_semana14_rf.py::test_rnf05_clasificacion_limites` |
| RF-02 / RNF-06 | Fiabilidad / Ausencia de fallos | Inactivo tras más de 60 s | Cumple. `tests/test_semana14_rf.py::test_rnf06_inactivo_tras_60s` |

## 8. Ejecución y repetición de las pruebas

**Requisitos:** Python 3.11, MongoDB en `localhost:27017` y las dependencias de `backend/requirements.txt`.

1. **Configuración.** Copia `backend/.env.example` como `backend/.env`. La base es `DB_NAME=coldchain_db`, la misma que usa la app.
   ```
   MONGO_URL=mongodb://localhost:27017
   DB_NAME=coldchain_db
   CORS_ORIGINS=http://localhost:3000
   JWT_SECRET=<clave_larga_y_aleatoria>
   ADMIN_EMAIL=<correo_admin>
   ADMIN_PASSWORD=<clave_inicial>
   ```
2. **Backend.** Dentro de `backend`, ejecuta `uvicorn server:app --host 0.0.0.0 --port 8001`. Escucha en el puerto 8001; el frontend usa el 3000.
3. **Pruebas funcionales y RNF-01, 02, 05 y 06.** Desde `backend`, en otra terminal:
   - Linux o macOS: `REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/test_semana14_rf.py -v --junitxml=../documentacion/evidencias/pytest_semana14.xml`
   - Windows PowerShell: `$env:REACT_APP_BACKEND_URL="http://localhost:8001"; pytest tests/test_semana14_rf.py -v`

   Resultado esperado: 25 pruebas pasan en unos 80 s. La de RNF-06 espera 65 s.
4. **RNF-03.** `python tests/rnf03_latencia.py --base-url http://localhost:8001 --n 100 --out ../documentacion/evidencias/rnf03_latencia.json`
5. **RNF-04.**
   1. `python tests/rnf04_reinicio.py antes --base-url http://localhost:8001 --n 20 --state ../documentacion/evidencias/rnf04_estado.json`
   2. Reinicia uvicorn y MongoDB.
   3. `python tests/rnf04_reinicio.py despues --base-url http://localhost:8001 --state ../documentacion/evidencias/rnf04_estado.json --out ../documentacion/evidencias/rnf04_reinicio.json`

   El archivo `rnf04_estado.json` contiene credenciales temporales. Bórralo al terminar.
6. **Reinicio de datos de prueba.** `python seed_demo.py --reset`
   - Borra todo lo que tenga el prefijo `TEST_`.
   - Crea o restaura, de forma idempotente, `DEMO_ESP32_01` y `DEMO_ESP32_02` aprobados con 24 lecturas cada uno.
   - Evidencia de idempotencia: `evidencias/seed_idempotente.txt`. Dos ejecuciones dejan 1 dispositivo y 24 lecturas por cada demo.

Las pruebas crean su propio administrador temporal con 2FA directamente en la base y lo eliminan al terminar. No necesitan credenciales reales.

## 9. Relevo a la interfaz (semana 3)

- **Contratos:** los de la sección 4. El frontend React ya consume `/api/alerts`, `/api/alerts/{id}/ack`, `/api/devices/{id}/alerts/ack-all`, `/api/devices/{id}/readings` y la aprobación de dispositivos.
- **Datos disponibles:** `seed_demo.py` (dispositivos `DEMO_ESP32_01` y `02`, claves `Demo_Clave_01` y `02`). Para generar alertas desde la pantalla, envía lecturas fuera de rango con `POST /api/temperatura`.
- **CORS:** el origen local previsto es `http://localhost:3000` (`CORS_ORIGINS`).
- **Clientes:** si se pierde una respuesta de escritura, el cliente debe consultar el resultado (`GET /api/alerts` o `/readings`) antes de repetir. El ESP32 reintenta con un nonce nuevo.
- **Pendientes para la semana 3:**
  - Evidencia de ambos RF desde la pantalla.
  - Pruebas de exportación CSV/PDF.
  - Instalación cronometrada desde cero (RNF-10).
  - Retirar las contraseñas en texto plano de las pruebas antiguas y de la documentación (RNF-11).
  - Repetir RNF-03 con concurrencia si se define un escenario de carga.
- **Riesgo conocido:** no hay transacción multi-documento en RF-01 (sección 2).

## 10. Checklist de entrega

| Criterio | Cumple | Evidencia |
|----------|--------|-----------|
| Los dos RF mantienen la prioridad y el alcance de la semana 1 | Sí | Sección 1 |
| Ambos RF tienen servicios y endpoints identificables | Sí | Secciones 2-4; `services.py`, `repositories.py` |
| Los contratos describen el éxito, la entrada inválida y los errores pertinentes | Sí | Sección 4 |
| Hay un resultado válido y un rechazo o ausencia probados para cada RF | Sí | Sección 5 |
| Se verifica la persistencia real y la ausencia de escrituras indebidas | Sí | Conteos antes y después en las pruebas; lectura desde otra conexión |
| Las consultas quedan en persistencia y las reglas en el servicio o dominio | Sí | `repositories.py` / `services.py` (MongoDB, sin SQL) |
| Cada RF se vincula con sus RNF y atributos ISO/IEC 25010 | Sí | Sección 7 |
| Los RNF previstos tienen medidas observadas y evidencias | Sí (6/6) | Sección 6; `documentacion/evidencias/` |
| Se distinguen los incumplimientos y los pendientes de la semana 3 | Sí | Secciones 6 y 9 |
| El README permite ejecutar y repetir las pruebas | Sí | README, sección "Pruebas (Semana 14)", y sección 8 |

Referencia: ISO/IEC 25010:2023. Product quality model. https://www.iso.org/standard/78176.html · Fowler, M. (2002). *Patterns of Enterprise Application Architecture*.
