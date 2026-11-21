/*
- ColdChain Dashboard - Firmware Definitivo
- Hardware: ESP32 + DS18B20 + Módulo Relé (Ventilador)
- Características: HMAC-SHA256, Nonce basado en NTP, Control Activo (Histéresis)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "mbedtls/md.h"
#include "time.h" // Librería para obtener la hora de internet (NTP)

// ============ CONFIGURACIÓN DE RED Y API ============
const char* ssid             = "TU_SSID_WIFI";
const char* password         = "TU_PASSWORD_WIFI";
const char* serverName       = "https://tu-dominio.com/api/temperatura";
const char* deviceID         = "ESP32_VACUNA_001";
const char* devicePassword   = "PASS_SECRETA_123";   // Contraseña y clave HMAC

// ============ PINES DEL HARDWARE ============
const int ONE_WIRE_BUS = 4; // Pin de datos del sensor DS18B20
const int FAN_PIN      = 5; // Pin de señal conectado al Módulo Relé

// ============ OBJETOS ============
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ============ FUNCIÓN HMAC-SHA256 ============
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
  
  // 1. Configurar el pin del relé/ventilador
  pinMode(FAN_PIN, OUTPUT);
  digitalWrite(FAN_PIN, LOW); // Asegurar que el ventilador inicie APAGADO
  
  // 2. Iniciar sensor de temperatura
  sensors.begin();
  
  // 3. Conectar a Wi-Fi
  WiFi.begin(ssid, password);
  Serial.print("Conectando a Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); 
    Serial.print(".");
  }
  Serial.println("\nWiFi OK");

  // 4. Sincronizar hora por internet (NTP) para el Nonce
  configTime(0, 0, "pool.ntp.org");
  Serial.print("Sincronizando hora real con NTP");
  struct tm timeinfo;
  while (!getLocalTime(&timeinfo)) {
    delay(500); 
    Serial.print(".");
  }
  Serial.println("\n¡Hora sincronizada!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    
    // --- LECTURA DE TEMPERATURA ---
    sensors.requestTemperatures();
    float tC = sensors.getTempCByIndex(0);
    
    if (tC == DEVICE_DISCONNECTED_C) {
      Serial.println("Error: Sensor DS18B20 desconectado");
      delay(10000);
      return;
    }

    // --- LÓGICA DE CONTROL (HISTÉRESIS) ---
    // Enciende el ventilador si llega a 8.0°C o más
    if (tC >= 8.0) {
      digitalWrite(FAN_PIN, HIGH);
      Serial.println("ALERTA: Límite superior alcanzado. Ventilador ENCENDIDO.");
    } 
    // Apaga el ventilador solo cuando baja a 7.0°C o menos
    else if (tC <= 7.0) {
      digitalWrite(FAN_PIN, LOW);
      Serial.println("Temperatura estabilizada. Ventilador APAGADO.");
    }

    // --- GENERACIÓN DEL NONCE ---
    time_t now;
    time(&now); // Obtiene la hora actual (Unix Epoch)
    unsigned long nonce = (unsigned long)now;

    // --- CREACIÓN DE LA FIRMA CRIPTOGRÁFICA ---
    char tempStr[16];
    dtostrf(tC, 0, 2, tempStr); // Convierte el float a String con 2 decimales
    String message = String(deviceID) + "|" + String(nonce) + "|" + String(tempStr);
    String signature = hmacSha256Hex(String(devicePassword), message);

    // --- CONSTRUCCIÓN DEL JSON ---
    String body = String("{") +
      "\"deviceId\":\"" + deviceID + "\"," +
      "\"devicePassword\":\"" + devicePassword + "\"," +
      "\"temperature\":" + String(tempStr) + "," +
      "\"nonce\":" + String(nonce) + "," +
      "\"signature\":\"" + signature + "\"}";

    // --- ENVÍO DE DATOS AL SERVIDOR ---
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");
    
    int httpResponseCode = http.POST(body);
    Serial.printf("POST -> %d  Temp = %s°C  Nonce = %lu\n", httpResponseCode, tempStr, nonce);
    
    if (httpResponseCode > 0) {
      Serial.println("Respuesta del servidor: " + http.getString());
    } else {
      Serial.println("Error en la conexión HTTP.");
    }
    http.end();
    
  } else {
    Serial.println("Conexión Wi-Fi perdida, intentando reconectar...");
    WiFi.reconnect();
  }
  
  // Esperar 10 segundos antes de la siguiente lectura
  delay(10000);
}