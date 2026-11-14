
from pathlib import Path
import csv
import sumolib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Directorio principal del reto
RETO = Path(__file__).resolve().parents[2]
GRAFICAS = RETO / "resultados" / "graficas"
SALIDA = RETO / "resultados" / "salida"

GRAFICAS.mkdir(parents=True, exist_ok=True)
SALIDA.mkdir(parents=True, exist_ok=True)

archivos = {
    "Original": RETO / "red_original" / "cuenca_net.xml",
    "Avenidas": RETO / "cuenca_ciudad.net.xml"
}

datos = {}
red_avenidas = None

# 1. Analizar las dos redes
for nombre, archivo in archivos.items():
    print(f"Cargando {nombre}: {archivo.name}")

    net = sumolib.net.readNet(str(archivo))
    edges = net.getEdges()
    nodes = net.getNodes()
    tls = net.getTrafficLights()

    datos[nombre] = {
        "Aristas": len(edges),
        "Nodos": len(nodes),
        "Semáforos": len(tls),
        "Kilómetros": sum(
            edge.getLength() for edge in edges
        ) / 1000
    }

    if nombre == "Avenidas":
        red_avenidas = net

# 2. Mostrar tabla comparativa
print("\n========== FASE 0.3 ==========")
print(f"{'Indicador':<16}{'Original':>15}{'Avenidas':>15}")
print("-" * 46)

for indicador in datos["Original"]:
    a = datos["Original"][indicador]
    b = datos["Avenidas"][indicador]

    if indicador == "Kilómetros":
        print(f"{indicador:<16}{a:>15.2f}{b:>15.2f}")
    else:
        print(f"{indicador:<16}{a:>15}{b:>15}")

print("\nPORCENTAJES CONSERVADOS")

for indicador in ["Aristas", "Kilómetros"]:
    original = datos["Original"][indicador]
    avenidas = datos["Avenidas"][indicador]
    porcentaje = 100 * avenidas / original if original else 0
    print(f"{indicador}: {porcentaje:.2f}%")

# 3. Guardar tabla CSV
csv_file = SALIDA / "F0-T0.3-COMPARACION_redes.csv"

with open(csv_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Indicador", "Original", "Avenidas", "% conservado"])

    for indicador in datos["Original"]:
        a = datos["Original"][indicador]
        b = datos["Avenidas"][indicador]
        porcentaje = 100 * b / a if a else 0

        writer.writerow([
            indicador, round(a, 2), round(b, 2),
            round(porcentaje, 2)
        ])

# 4. Generar gráfica comparativa
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

indicadores = ["Aristas", "Nodos", "Semáforos", "Kilómetros"]

for ax, indicador in zip(axes.flat, indicadores):
    valores = [
        datos["Original"][indicador],
        datos["Avenidas"][indicador]
    ]

    bars = ax.bar(
        ["Original", "Avenidas"],
        valores,
        color=["#A0A0A0", "#174A7E"]
    )

    ax.set_title(indicador, fontweight="bold")
    ax.set_ylabel("km" if indicador == "Kilómetros" else "Cantidad")
    ax.bar_label(bars, fmt="%.1f" if indicador == "Kilómetros" else "%.0f")
    ax.set_ylim(0, max(valores) * 1.18 if max(valores) else 1)

fig.suptitle(
    "Fase 0.3 - Comparación de redes de Cuenca",
    fontsize=15,
    fontweight="bold"
)

fig.tight_layout()

grafica = GRAFICAS / "F0-T0.3-COMPARACION_redes.png"
fig.savefig(grafica, dpi=300, bbox_inches="tight")
plt.close(fig)

print("\nARCHIVOS GENERADOS")
print(csv_file)
print(grafica)

# 5. Verificar proximidad de tres hospitales
hospitales = {
    "Vicente Corral Moscoso": (-78.992923, -2.911098),
    "Jose Carrasco Arteaga": (-78.970118, -2.898698),
    "Hospital Militar Tarqui": (-79.003968, -2.903146)
}

print("\nHOSPITALES EN LA RED DE AVENIDAS")

ubicaciones = []

for nombre, (lon, lat) in hospitales.items():
    x, y = red_avenidas.convertLonLat2XY(lon, lat)

    vecinos = red_avenidas.getNeighboringEdges(
        x, y, r=500
    )

    aptos = [
        (edge, dist)
        for edge, dist in vecinos
        if edge.allows("emergency")
    ]

    if aptos:
        edge, distancia = min(
            aptos, key=lambda item: item[1]
        )

        print(
            f"{nombre}: {distancia:.1f} m | "
            f"Arista {edge.getID()}"
        )

        ubicaciones.append((nombre, x, y))
    else:
        print(f"{nombre}: SIN VIA cercana apta para ambulancias")

# 6. Crear marcadores para SUMO-GUI
archivo_pois = SALIDA / "F0-T0.3-HOSPITALES.add.xml"

import xml.etree.ElementTree as ET

root = ET.Element("additional")

for i, (nombre, x, y) in enumerate(ubicaciones, start=1):
    ET.SubElement(root, "poi", {
        "id": f"HOSPITAL_{i}",
        "type": nombre,
        "x": str(x),
        "y": str(y),
        "color": "255,0,0",
        "layer": "100",
        "width": "12",
        "height": "12"
    })

ET.ElementTree(root).write(
    archivo_pois,
    encoding="utf-8",
    xml_declaration=True
)

print("\nMarcadores SUMO-GUI:", archivo_pois)
print("FASE 0.3: comparación finalizada")
