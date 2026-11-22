#include <WiFi.h>
#include <PubSubClient.h>

// Configuración WiFi y MQTT
const char* ssid = "TU_RED_WIFI";
const char* password = "TU_PASSWORD_WIFI";
const char* mqtt_server = "broker.hivemq.com";
const char* mqtt_topic = "leticia/acueducto/nodo_01/telemetria";

// Pines del ESP32
const int PIN_FLUJO = 27;     // Interrupción digital para sensor YF-S201
const int PIN_PRESION = 34;   // Canal ADC1 (entrada con divisor resistivo 1k / 2k)
const float FACTOR_K = 7.5f;  // Constante YF-S201 (pulsos por segundo / L/min)
const float V_REF_ADC = 3.3f;
const int ADC_MAX = 4095;

volatile unsigned long pulsos = 0;
float volumenTotalLitros = 0.0f;
unsigned long ultimaLectura = 0;

WiFiClient espClient;
PubSubClient client(espClient);

void IRAM_ATTR contarPulso() {
  pulsos++;
}

void conectarWiFi() {
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
}

void conectarMQTT() {
  while (!client.connected()) {
    String clientId = "ESP32_LET_" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      break;
    }
    delay(1500);
  }
}

float leerPresionMPa() {
  int rawAdc = analogRead(PIN_PRESION);
  // Atenuación por divisor resistivo R1=1k, R2=2k -> V_nodo = V_adc * (3.0 / 2.0)
  float voltajeAdc = (rawAdc / (float)ADC_MAX) * V_REF_ADC;
  float voltajeSensor = voltajeAdc * 1.5f;

  // Sensor 0.5V - 4.5V mapeado a 0.0 - 1.2 MPa
  if (voltajeSensor < 0.5f) voltajeSensor = 0.5f;
  if (voltajeSensor > 4.5f) voltajeSensor = 4.5f;
  float presionMPa = ((voltajeSensor - 0.5f) / 4.0f) * 1.2f;
  return presionMPa;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FLUJO, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLUJO), contarPulso, RISING);
  analogReadResolution(12);

  conectarWiFi();
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWiFi();
  if (!client.connected()) conectarMQTT();
  client.loop();

  unsigned long ahora = millis();
  if (ahora - ultimaLectura >= 2000) {
    unsigned long dtMs = ahora - ultimaLectura;
    ultimaLectura = ahora;

    noInterrupts();
    unsigned long pulsosVentana = pulsos;
    pulsos = 0;
    interrupts();

    float frecuenciaHz = (pulsosVentana * 1000.0f) / (float)dtMs;
    float caudalLMin = frecuenciaHz / FACTOR_K;
    volumenTotalLitros += caudalLMin * (dtMs / 60000.0f);
    float presionMPa = leerPresionMPa();

    String payload = "{";
    payload += "\"node_id\":\"ESP32_LET_01\",";
    payload += "\"timestamp\":" + String(ahora / 1000) + ",";
    payload += "\"flow_rate_lmin\":" + String(caudalLMin, 2) + ",";
    payload += "\"pressure_mpa\":" + String(presionMPa, 3) + ",";
    payload += "\"total_volume_l\":" + String(volumenTotalLitros, 2) + ",";
    payload += "\"status\":\"OK\"}";

    client.publish(mqtt_topic, payload.c_str());
    Serial.println(payload);
  }
}
