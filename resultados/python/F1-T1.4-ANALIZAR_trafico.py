
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RETO = Path(__file__).resolve().parents[2]
SALIDA = RETO / "resultados" / "salida"
GRAFICAS = RETO / "resultados" / "graficas"

GRAFICAS.mkdir(parents=True, exist_ok=True)

archivo = SALIDA / "F1-T1.4-MACRO.xml"

raiz = ET.parse(archivo).getroot()

registros = []

for intervalo in raiz.findall("interval"):
    inicio = float(intervalo.get("begin"))
    fin = float(intervalo.get("end"))

    for edge in intervalo.findall("edge"):
        registros.append({
            "inicio": inicio,
            "fin": fin,
            "arista": edge.get("id"),
            "vehiculos": float(edge.get("entered", 0)),
            "densidad": float(edge.get("density", 0)),
            "velocidad": float(edge.get("speed", 0)) * 3.6
        })

df = pd.DataFrame(registros)

if df.empty:
    raise RuntimeError("No se encontraron mediciones edgeData")

# Flujo de entradas por arista (vehículos/h)
duracion = df["fin"] - df["inicio"]
df["flujo"] = df["vehiculos"] * 3600 / duracion

# Resumen temporal: media de las aristas que tienen medición.
resumen = df.groupby(["inicio", "fin"], as_index=False).agg({
    "flujo": "mean",
    "densidad": "mean",
    "velocidad": "mean"
})

resumen["minuto"] = resumen["inicio"] / 60

csv = SALIDA / "F1-T1.4-INDICADORES_trafico.csv"
resumen.to_csv(csv, index=False)

print("\nFASE 1.4 - INDICADORES DEL TRÁFICO")
print(resumen.to_string(index=False))

# Gráfico 1 - Flujo temporal
plt.figure(figsize=(10, 5))
plt.plot(resumen["minuto"], resumen["flujo"], marker="o")
plt.title("F1-T1.4 - Flujo vehicular")
plt.xlabel("Tiempo simulado (min)")
plt.ylabel("Flujo medio por arista (veh/h)")
plt.grid(True)
plt.tight_layout()
plt.savefig(
    GRAFICAS / "F1-T1.4-FLUJO_tiempo.png",
    dpi=300
)
plt.close()

# Gráfico 2 - Densidad temporal
plt.figure(figsize=(10, 5))
plt.plot(resumen["minuto"], resumen["densidad"], marker="o")
plt.title("F1-T1.4 - Densidad vehicular")
plt.xlabel("Tiempo simulado (min)")
plt.ylabel("Densidad media (veh/km)")
plt.grid(True)
plt.tight_layout()
plt.savefig(
    GRAFICAS / "F1-T1.4-DENSIDAD_tiempo.png",
    dpi=300
)
plt.close()

# Gráfico 3 - Velocidad temporal
plt.figure(figsize=(10, 5))
plt.plot(resumen["minuto"], resumen["velocidad"], marker="o")
plt.title("F1-T1.4 - Velocidad media")
plt.xlabel("Tiempo simulado (min)")
plt.ylabel("Velocidad (km/h)")
plt.grid(True)
plt.tight_layout()
plt.savefig(
    GRAFICAS / "F1-T1.4-VELOCIDAD_tiempo.png",
    dpi=300
)
plt.close()

# Gráfico 4 - Diagrama fundamental aproximado
plt.figure(figsize=(9, 6))
plt.scatter(resumen["densidad"], resumen["flujo"])
plt.title("F1-T1.4 - Diagrama flujo-densidad")
plt.xlabel("Densidad media (veh/km)")
plt.ylabel("Flujo medio por arista (veh/h)")
plt.grid(True)
plt.tight_layout()
plt.savefig(
    GRAFICAS / "F1-T1.4-DIAGRAMA_fundamental.png",
    dpi=300
)
plt.close()

print("\nArchivos generados correctamente.")
print("Tabla:", csv)
print("Gráficos:", GRAFICAS)
