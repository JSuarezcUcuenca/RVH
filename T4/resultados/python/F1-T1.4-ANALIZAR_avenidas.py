
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET

import pandas as pd
import sumolib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RETO = Path(__file__).resolve().parents[2]
SALIDA = RETO / "resultados" / "salida"
GRAFICAS = RETO / "resultados" / "graficas"

SALIDA.mkdir(parents=True, exist_ok=True)
GRAFICAS.mkdir(parents=True, exist_ok=True)

NET = RETO / "cuenca_ciudad.net.xml"
MACRO = SALIDA / "F1-T1.4-MACRO.xml"

def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

# 1. Identificar avenidas por nombre
net = sumolib.net.readNet(str(NET))

patrones = {
    "Circunvalacion Sur": ["circunvalacion"],
    "Huayna Capac": ["huayna"],
    "Av. de las Americas": ["americas"]
}

aristas_avenidas = {}
longitudes = {}

for edge in net.getEdges():
    eid = edge.getID()
    calle = normalizar(edge.getName() or "")
    longitudes[eid] = edge.getLength() / 1000

    for avenida, palabras in patrones.items():
        if any(p in calle for p in palabras):
            aristas_avenidas[eid] = avenida
            break

print("\n=== ARISTAS IDENTIFICADAS ===")

for avenida in patrones:
    ids = [
        eid for eid, nombre in aristas_avenidas.items()
        if nombre == avenida
    ]
    print(f"{avenida}: {len(ids)} aristas")

if not aristas_avenidas:
    raise RuntimeError(
        "No se identificaron avenidas. "
        "Revisar los nombres de las calles."
    )

# 2. Leer mediciones de SUMO
raiz = ET.parse(MACRO).getroot()
filas = []

for intervalo in raiz.findall("interval"):
    inicio = float(intervalo.get("begin"))
    fin = float(intervalo.get("end"))

    # Solo período estacionario: 15-180 min
    if inicio < 900 or fin > 10800:
        continue

    duracion = fin - inicio

    for edge in intervalo.findall("edge"):
        eid = edge.get("id")

        if eid not in aristas_avenidas:
            continue

        longitud = longitudes[eid]

        if longitud <= 0:
            continue

        # No sustituir mediciones ausentes por cero
        densidad = edge.get("density")
        velocidad = edge.get("speed")

        if densidad is None or velocidad is None:
            continue

        k = float(densidad)
        v = float(velocidad) * 3.6

        filas.append({
            "avenida": aristas_avenidas[eid],
            "arista": eid,
            "inicio": inicio,
            "fin": fin,
            "longitud_km": longitud,
            "densidad": k,
            "velocidad": v,
            "flujo_kv": k * v,
            "entered": float(edge.get("entered", 0)),
            "duracion": duracion
        })

df = pd.DataFrame(filas)

if df.empty:
    raise RuntimeError(
        "No hay mediciones para las avenidas seleccionadas."
    )

# 3. Promediar por intervalo y avenida
intervalos = []

for (avenida, inicio), g in df.groupby(["avenida", "inicio"]):
    L = g["longitud_km"].sum()

    k = (g["densidad"] * g["longitud_km"]).sum() / L

    # Velocidad coherente con la relación q = k*v:
    peso = g["densidad"] * g["longitud_km"]

    if peso.sum() > 0:
        v = (g["velocidad"] * peso).sum() / peso.sum()
    else:
        v = float("nan")

    q_kv = k * v if pd.notna(v) else 0

    # Flujo de entradas: indicador diferente a q=k*v
    q_entradas = (
        g["entered"].sum() * 3600 / g["duracion"].iloc[0]
    )

    intervalos.append({
        "avenida": avenida,
        "inicio": inicio,
        "longitud_km": L,
        "q_kv": q_kv,
        "q_entradas": q_entradas,
        "k": k,
        "v": v
    })

intervalos = pd.DataFrame(intervalos)

# 4. Resumen estacionario de cada avenida
resumen = []

for avenida, g in intervalos.groupby("avenida"):
    resumen.append({
        "Avenida": avenida,
        "Aristas": sum(
            nombre == avenida
            for nombre in aristas_avenidas.values()
        ),
        "q_veh_h": g["q_kv"].mean(),
        "k_veh_km": g["k"].mean(),
        "v_km_h": g["v"].mean(),
        "q_entradas_veh_h": g["q_entradas"].mean()
    })

res = pd.DataFrame(resumen)

csv = SALIDA / "F1-T1.4-AVENIDAS_indicadores.csv"
res.to_csv(csv, index=False)

intervalos.to_csv(
    SALIDA / "F1-T1.4-AVENIDAS_intervalos.csv",
    index=False
)

print("\n=== RESULTADOS POR AVENIDA ===")
print(res.round(2).to_string(index=False))

# 5. Gráfico comparativo
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

columnas = [
    ("q_veh_h", "Flujo q", "veh/h"),
    ("k_veh_km", "Densidad k", "veh/km"),
    ("v_km_h", "Velocidad v", "km/h")
]

for ax, (columna, titulo, unidad) in zip(axes, columnas):
    bars = ax.bar(res["Avenida"], res[columna])
    ax.set_title(titulo)
    ax.set_ylabel(unidad)
    ax.tick_params(axis="x", labelrotation=25)

    for bar in bars:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{bar.get_height():.1f}",
            ha="center",
            va="bottom"
        )

fig.suptitle("F1-T1.4 - Comparación de tres avenidas")
fig.tight_layout()
fig.savefig(
    GRAFICAS / "F1-T1.4-AVENIDAS_comparacion.png",
    dpi=300
)
plt.close(fig)

# 6. Diagrama q-k de las avenidas
plt.figure(figsize=(10, 6))

for avenida, g in intervalos.groupby("avenida"):
    plt.scatter(
        g["k"], g["q_kv"],
        label=avenida,
        s=50
    )

plt.title("F1-T1.4 - Flujo vs densidad por avenida")
plt.xlabel("Densidad (veh/km)")
plt.ylabel("Flujo estimado q=k*v (veh/h)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(
    GRAFICAS / "F1-T1.4-AVENIDAS_qk.png",
    dpi=300
)
plt.close()

print("\nArchivos generados:")
print(csv)
print(GRAFICAS / "F1-T1.4-AVENIDAS_comparacion.png")
print(GRAFICAS / "F1-T1.4-AVENIDAS_qk.png")

