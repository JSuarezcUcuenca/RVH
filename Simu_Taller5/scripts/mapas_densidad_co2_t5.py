from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd

base = Path(__file__).resolve().parent.parent
config = ET.parse(base / "cuenca.sumocfg").getroot()

def resolver(ruta):
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else base / ruta

red = resolver(config.find("./input/net-file").get("value"))
carpeta = resolver(
    config.find("./output/tripinfo-output").get("value")
).parent

salida = base / "Graficas" / carpeta.name
salida.mkdir(parents=True, exist_ok=True)

def leer_intervalo(archivo):
    root = ET.parse(archivo).getroot()
    intervalos = root.findall("interval")

    if len(intervalos) != 1:
        raise SystemExit(
            f"{archivo.name}: se esperaba un intervalo horario, "
            f"pero hay {len(intervalos)}."
        )

    intervalo = intervalos[0]
    ventana = (
        float(intervalo.get("begin")),
        float(intervalo.get("end")),
    )

    datos = {
        e.get("id"): dict(e.attrib)
        for e in intervalo.findall("edge")
    }
    return ventana, datos

ventana_d, densidades = leer_intervalo(carpeta / "edgedata.xml")
ventana_e, emisiones = leer_intervalo(carpeta / "emissions.xml")

if ventana_d != ventana_e:
    raise SystemExit(
        "Los intervalos de densidad y emisiones no coinciden."
    )

inicio, fin = ventana_d
duracion = fin - inicio
if duracion <= 0:
    raise SystemExit("Intervalo de duración inválida.")

# Geometría de las calles externas.
geometrias = {}
longitudes = {}

for edge in ET.parse(red).getroot().findall("edge"):
    eid = edge.get("id")

    if edge.get("function") == "internal" or eid.startswith(":"):
        continue

    carriles = edge.findall("lane")
    if not carriles:
        continue

    # Usar un carril como línea representativa del tramo.
    carril = carriles[0]
    forma = carril.get("shape", "")
    longitud = float(carril.get("length", 0))

    if not forma or longitud <= 0:
        continue

    puntos = np.array([
        [float(v) for v in punto.split(",")[:2]]
        for punto in forma.split()
    ])

    if len(puntos) >= 2:
        geometrias[eid] = puntos
        longitudes[eid] = longitud

filas = []

for eid in sorted(set(densidades) | set(emisiones)):
    d = densidades.get(eid, {})
    e = emisiones.get(eid, {})

    densidad = float(d["density"]) if "density" in d else np.nan
    co2_mg = float(e["CO2_abs"]) if "CO2_abs" in e else np.nan

    longitud = longitudes.get(eid, np.nan)
    co2_kg = co2_mg / 1e6

    intensidad = (
        (co2_mg / 1000) / duracion / (longitud / 1000)
        if np.isfinite(longitud) else np.nan
    )

    filas.append({
        "calle": eid,
        "densidad_veh_km": densidad,
        "co2_kg": co2_kg,
        "co2_g_s_km": intensidad,
        "longitud_m": longitud,
        "con_geometria": eid in geometrias,
    })

tabla = pd.DataFrame(filas).set_index("calle")
tabla.to_csv(salida / "densidad_co2_por_calle.csv")

plt.rcParams.update({"font.size": 11})

def dibujar_mapa(ax, columna, titulo, unidad, paleta):
    ax.add_collection(LineCollection(
        list(geometrias.values()),
        colors="#d2d7dd",
        linewidths=1,
    ))

    seleccion = tabla[
        tabla["con_geometria"] & tabla[columna].notna()
    ]

    if seleccion.empty:
        raise SystemExit(f"No hay datos para representar: {columna}")

    vmax = max(float(seleccion[columna].max()), 1e-12)

    capa = LineCollection(
        [geometrias[eid] for eid in seleccion.index],
        cmap=paleta,
        norm=Normalize(vmin=0, vmax=vmax),
        linewidths=3,
    )
    capa.set_array(seleccion[columna].to_numpy())
    ax.add_collection(capa)

    ax.autoscale()
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(titulo)
    ax.set_xlabel("X SUMO (m)")
    ax.set_ylabel("Y SUMO (m)")

    ax.figure.colorbar(
        capa, ax=ax, label=unidad, shrink=0.8
    )

def guardar(fig, nombre):
    fig.savefig(
        salida / nombre,
        dpi=250,
        bbox_inches="tight",
    )
    plt.close(fig)
    print("Guardado:", nombre)

# Mapas individuales para el informe.
for columna, titulo, unidad, paleta, nombre in [
    (
        "densidad_veh_km",
        "Densidad vehicular media",
        "veh/km",
        "YlOrRd",
        "T5_densidad_Suarez.png",
    ),
    (
        "co2_kg",
        "Emisiones acumuladas de CO₂ por calle",
        "kg de CO₂",
        "inferno",
        "T5_emisiones_Suarez.png",
    ),
]:
    fig, ax = plt.subplots(
        figsize=(12, 7), constrained_layout=True
    )
    dibujar_mapa(ax, columna, titulo, unidad, paleta)
    fig.suptitle(f"Escenario 3800 veh/h | {inicio:g}–{fin:g} s")
    guardar(fig, nombre)

# Dos mapas sobre la misma geometría.
fig, ejes = plt.subplots(
    1, 2, figsize=(17, 7), constrained_layout=True
)

dibujar_mapa(
    ejes[0],
    "densidad_veh_km",
    "Densidad vehicular media",
    "veh/km",
    "YlOrRd",
)
dibujar_mapa(
    ejes[1],
    "co2_kg",
    "CO₂ acumulado por calle",
    "kg de CO₂",
    "inferno",
)

fig.suptitle(
    f"Densidad y CO₂ | {inicio:g}–{fin:g} s\n"
    "Calles externas; gris: sin valor representado"
)
guardar(fig, "T5_comparacion_mapas_Suarez.png")

# Comparación estadística en calles con ambas métricas.
pares = tabla[
    tabla["con_geometria"]
].dropna(subset=["densidad_veh_km", "co2_kg", "co2_g_s_km"])

if len(pares) < 3:
    raise SystemExit("Hay menos de tres calles comparables.")

fig, ejes = plt.subplots(
    1, 2, figsize=(13, 5), constrained_layout=True
)

for ax, columna, etiqueta in [
    (ejes[0], "co2_kg", "CO₂ acumulado (kg)"),
    (ejes[1], "co2_g_s_km", "Intensidad de CO₂ (g/s/km)"),
]:
    r = pares["densidad_veh_km"].corr(pares[columna])

    ax.scatter(
        pares["densidad_veh_km"],
        pares[columna],
        s=24,
        alpha=0.65,
    )
    ax.set_xlabel("Densidad media (veh/km)")
    ax.set_ylabel(etiqueta)
    ax.set_title(f"Correlación de Pearson: r = {r:.3f}")
    ax.grid(alpha=0.25)

guardar(fig, "T5_relacion_densidad_CO2_Suarez.png")

# Comprobar cobertura de las emisiones.
total_exportado = tabla["co2_kg"].sum()
total_mapeado = tabla.loc[
    tabla["con_geometria"], "co2_kg"
].sum()

print(f"\nIntervalo: {inicio:g}–{fin:g} s")
print(f"Calles con geometría en la red: {len(geometrias)}")
print(f"Calles comparables: {len(pares)}")
print(f"CO₂ en emissions.xml: {total_exportado:.3f} kg")
print(f"CO₂ asociado al mapa: {total_mapeado:.3f} kg")

if total_exportado > 0:
    print(
        "Cobertura respecto a emissions.xml: "
        f"{100 * total_mapeado / total_exportado:.2f} %"
    )

sin_geometria = tabla.loc[~tabla["con_geometria"]]
if not sin_geometria.empty:
    sin_geometria.to_csv(salida / "calles_sin_geometria.csv")
    print("Identificadores sin geometría:", len(sin_geometria))

print("\nDIEZ CALLES CON MAYOR EMISIÓN")
print(
    tabla.nlargest(10, "co2_kg")[
        ["densidad_veh_km", "co2_kg", "co2_g_s_km"]
    ].round(3).to_string()
)

print("\nResultados:", salida)
print(
    "\nLa cobertura indicada se refiere a emissions.xml, "
    "no necesariamente al total de co2.xml. "
    "Las conexiones internas pueden quedar fuera de edgeData."
)
