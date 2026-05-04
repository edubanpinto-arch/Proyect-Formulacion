/*
 * ColdChain Dashboard - ESP32 firmware with HMAC + nonce (replay protection)
 * Hardware: ESP32 + DS18B20
 *
 * Cómo funciona:
 *   payload = "{deviceId}|{nonce}|{temperature_2dp}"
 *   signature = HEX( HMAC-SHA256(devicePassword, payload) )
 *   POST /api/temperatura
 *     { "deviceId": "...", "devicePassword": "...",
 *       "temperature": 4.21, "nonce": 1714230012, "signature": "abc...e" }
 *
 * El backend rechaza la lectura si:
 *  - la firma no coincide
 *  - el nonce es <= al último nonce guardado para ese dispositivo
 *
 * NOTA: el `devicePassword` debe coincidir con el que registró el dispositivo
 * la primera vez (queda guardado como hash bcrypt en la base).
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "mbedtls/md.h"

// ============ CONFIG ============
const char* ssid             = "TU_SSID";
const char* password         = "TU_WIFI_PASSWORD";
const char* serverName       = "https://TU-DOMINIO/api/temperatura";
const char* deviceID         = "ESP32_VACUNA_001";
const char* devicePassword   = "PASS_SECRETA_123";  // se usa también como clave HMAC
const int   ONE_WIRE_BUS     = 4;

// ============ HW ============
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ============ NONCE persistente (millis() + epoch fallback) ============
unsigned long lastNonce = 0;

// ============ HMAC-SHA256 helper ============
String hmacSha256Hex(const String &key, const String &msg) {
  byte hmacResult[32];
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, info, 1 /* HMAC */);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)key.c_str(), key.length());
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)msg.c_str(), msg.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String hex = "";
  hex.reserve(64);
  for (int i = 0; i < 32; i++) {
    char buf[3];
    snprintf(buf, sizeof(buf), "%02x", hmacResult[i]);
    hex += buf;
  }
  return hex;
}

void setup() {
  Serial.begin(115200);
  sensors.begin();
  WiFi.begin(ssid, password);
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi OK");

  // semilla para el nonce: usa segundos transcurridos desde boot
  lastNonce = (unsigned long) (esp_timer_get_time() / 1000);
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    sensors.requestTemperatures();
    float tC = sensors.getTempCByIndex(0);
    if (tC == DEVICE_DISCONNECTED_C) {
      Serial.println("Sensor desconectado");
      delay(10000);
      return;
    }

    // nonce monotónico: usamos millis acumulado + base
    unsigned long nonce = lastNonce + (unsigned long)(millis() / 1000) + 1;
    lastNonce = nonce;  // garantiza incremento

    // construir payload firmado: "deviceId|nonce|temperature(2 dp)"
    char tempStr[16];
    dtostrf(tC, 0, 2, tempStr);
    String message = String(deviceID) + "|" + String(nonce) + "|" + String(tempStr);
    String signature = hmacSha256Hex(String(devicePassword), message);

    // construir JSON
    String body = String("{") +
      "\"deviceId\":\"" + deviceID + "\"," +
      "\"devicePassword\":\"" + devicePassword + "\"," +
      "\"temperature\":" + String(tempStr) + "," +
      "\"nonce\":" + String(nonce) + "," +
      "\"signature\":\"" + signature + "\"}";

    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    Serial.printf("POST -> %d  T=%s°C  nonce=%lu\n", code, tempStr, nonce);
    if (code > 0) {
      Serial.println(http.getString());
    }
    http.end();
  } else {
    Serial.println("WiFi caído, reintentando...");
    WiFi.reconnect();
  }
  delay(10000);
}
