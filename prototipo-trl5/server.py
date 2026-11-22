import json
import math
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
ESTADO_SIMULACION = {
    "modo_fuga": False,
    "severidad_fuga": 0.30,  # 30% de pérdida diferencial por defecto al activar fuga
    "caudal_base": 15.0,
    "presion_base": 0.24,
    "volumen_n1": 0.0,
    "volumen_n2": 0.0,
    "alertas": [],
    "ultimo_alerta_ts": 0.0,
}


def generar_telemetria():
    ahora = time.time()
    t = ahora % 60.0
    oscilacion = 0.6 * math.sin(t * 0.25) + random.uniform(-0.25, 0.25)

    q1 = max(1.0, round(ESTADO_SIMULACION["caudal_base"] + oscilacion, 2))
    p1 = round(max(0.05, ESTADO_SIMULACION["presion_base"] + random.uniform(-0.01, 0.01)), 3)

    if ESTADO_SIMULACION["modo_fuga"]:
        perdida = ESTADO_SIMULACION["severidad_fuga"] + random.uniform(-0.02, 0.02)
        perdida = min(max(perdida, 0.16), 0.75)
        q2 = max(0.2, round(q1 * (1.0 - perdida), 2))
        p2 = round(max(0.02, p1 * (1.0 - perdida * 0.45)), 3)
    else:
        # Pequeña variación normal (< 3%) dentro de tolerancia
        variacion_normal = random.uniform(0.005, 0.028)
        q2 = max(0.5, round(q1 * (1.0 - variacion_normal), 2))
        p2 = round(max(0.04, p1 - random.uniform(0.002, 0.008)), 3)

    ESTADO_SIMULACION["volumen_n1"] = round(ESTADO_SIMULACION["volumen_n1"] + (q1 * (2.0 / 60.0)), 2)
    ESTADO_SIMULACION["volumen_n2"] = round(ESTADO_SIMULACION["volumen_n2"] + (q2 * (2.0 / 60.0)), 2)

    delta_q_pct = round((abs(q1 - q2) / max(q1, 0.01)) * 100.0, 2)
    fuga_detectada = delta_q_pct > 15.0
    estado_tramo = "POSIBLE FUGA" if fuga_detectada else "NORMAL"

    if fuga_detectada and (ahora - ESTADO_SIMULACION["ultimo_alerta_ts"] >= 4.0):
        ESTADO_SIMULACION["ultimo_alerta_ts"] = ahora
        ESTADO_SIMULACION["alertas"].insert(0, {
            "hora": time.strftime("%H:%M:%S", time.localtime(ahora)),
            "tramo": "Tramo Leticia Nodo_01 -> Nodo_02",
            "q1": q1,
            "q2": q2,
            "delta_q_pct": delta_q_pct,
            "presion_mpa": p2,
            "estado": "POSIBLE FUGA",
        })
        ESTADO_SIMULACION["alertas"] = ESTADO_SIMULACION["alertas"][:20]

    return {
        "timestamp": int(ahora),
        "hora_legible": time.strftime("%H:%M:%S", time.localtime(ahora)),
        "nodo_01": {
            "node_id": "ESP32_LET_01",
            "topic": "leticia/acueducto/nodo_01/telemetria",
            "flow_rate_lmin": q1,
            "pressure_mpa": p1,
            "total_volume_l": ESTADO_SIMULACION["volumen_n1"],
        },
        "nodo_02": {
            "node_id": "ESP32_LET_02",
            "topic": "leticia/acueducto/nodo_02/telemetria",
            "flow_rate_lmin": q2,
            "pressure_mpa": p2,
            "total_volume_l": ESTADO_SIMULACION["volumen_n2"],
        },
        "analitica": {
            "delta_q_pct": delta_q_pct,
            "umbral_pct": 15.0,
            "fuga_detectada": fuga_detectada,
            "estado_tramo": estado_tramo,
            "modo_fuga_activo": ESTADO_SIMULACION["modo_fuga"],
            "severidad_fuga": ESTADO_SIMULACION["severidad_fuga"],
        },
        "alertas": ESTADO_SIMULACION["alertas"],
    }


class ManejadorPrototipo(BaseHTTPRequestHandler):
    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            contenido = (BASE_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(contenido)
        elif ruta == "/api/telemetria":
            payload = json.dumps(generar_telemetria()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        ruta = urlparse(self.path).path
        longitud = int(self.headers.get("Content-Length", "0"))
        cuerpo = self.rfile.read(longitud).decode("utf-8") if longitud > 0 else "{}"
        datos = json.loads(cuerpo or "{}")

        if ruta == "/api/simular-fuga":
            ESTADO_SIMULACION["modo_fuga"] = bool(datos.get("activar", not ESTADO_SIMULACION["modo_fuga"]))
            if "severidad" in datos:
                ESTADO_SIMULACION["severidad_fuga"] = float(datos["severidad"])
            respuesta = {"ok": True, "modo_fuga": ESTADO_SIMULACION["modo_fuga"]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(respuesta).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    puerto = 8080
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), ManejadorPrototipo)
    print(f"Prototipo TRL 5 activo en http://127.0.0.1:{puerto}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()
