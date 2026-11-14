from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection

base = Path(__file__).resolve().parent.parent
config = ET.parse(base / "cuenca.sumocfg").getroot()

archivo = Path(
    config.find("./output/fcd-output").get("value")
)
if not archivo.is_absolute():
    archivo = base / archivo

if not archivo.is_file():
    raise SystemExit(f"No existe: {archivo}")

salida = base / "Graficas" / archivo.parent.name
salida.mkdir(parents=True, exist_ok=True)

paso = float(
    config.find("./time/step-length").get("value")
)

registros = []

print("Leyendo FCD...")

for _, elemento in ET.iterparse(archivo, events=("end",)):
    if elemento.tag != "timestep":
        continue

    tiempo = float(elemento.get("time"))

    for vehiculo in elemento.findall("vehicle"):
        registros.append((
            tiempo,
            vehiculo.get("id"),
            vehiculo.get("type", "sin_tipo"),
            float(vehiculo.get("x")),
            float(vehiculo.get("y")),
            float(vehiculo.get("speed")),
        ))

    elemento.clear()

df = pd.DataFrame(
    registros,
    columns=["tiempo", "id", "tipo", "x", "y", "velocidad"],
)
del registros

if df.empty:
    raise SystemExit("El FCD no contiene vehículos.")

df = df.sort_values(["id", "tiempo"])

# Comprobar que la salida corresponde a muestras regulares
# compatibles con el paso configurado.
tiempos = np.sort(df["tiempo"].unique())
if len(tiempos) > 1:
    diferencias = np.diff(tiempos)
    if not np.allclose(diferencias, paso):
        print(
            "AVISO: hay diferencias en el muestreo temporal. "
            "Las estadísticas siguientes son por muestra."
        )

plt.rcParams.update({"font.size": 11})

def guardar(fig, nombre):
    fig.tight_layout()
    fig.savefig(
        salida / nombre,
        dpi=250,
        bbox_inches="tight",
    )
    plt.close(fig)
    print("Guardado:", nombre)

# 1. Nube de posiciones: no une puntos.
fig, ax = plt.subplots(figsize=(11, 8))
ax.scatter(
    df["x"], df["y"],
    s=0.5, alpha=0.10,
    color="#126b91",
    rasterized=True,
)
ax.set(
    title="Posiciones vehiculares observadas en FCD",
    xlabel="X SUMO (m)",
    ylabel="Y SUMO (m)",
)
ax.set_aspect("equal", adjustable="box")
ax.grid(alpha=0.15)
guardar(fig, "T5_posiciones_Suarez.png")

# 2. Trayectorias, sin unir huecos temporales.
segmentos = []

for _, grupo in df.groupby("id", sort=False):
    puntos = grupo[["x", "y"]].to_numpy()
    tiempo = grupo["tiempo"].to_numpy()

    if len(grupo) < 2:
        continue

    consecutivos = np.isclose(np.diff(tiempo), paso)
    pares = np.stack([puntos[:-1], puntos[1:]], axis=1)
    segmentos.extend(pares[consecutivos])

fig, ax = plt.subplots(figsize=(11, 8))

if segmentos:
    coleccion = LineCollection(
        segmentos,
        colors="#126b91",
        linewidths=0.35,
        alpha=0.15,
        rasterized=True,
    )
    ax.add_collection(coleccion)
    ax.autoscale()

ax.set(
    title="Trayectorias FCD: muestras temporalmente consecutivas",
    xlabel="X SUMO (m)",
    ylabel="Y SUMO (m)",
)
ax.set_aspect("equal", adjustable="box")
ax.grid(alpha=0.15)
guardar(fig, "T5_trayectorias_Suarez.png")

# 3. Velocidad de los vehículos indicados en la guía.
seleccionados = ["veh1", "veh40"]
disponibles = set(df["id"])

seleccionados = [
    vid for vid in seleccionados if vid in disponibles
]

if not seleccionados:
    seleccionados = list(df["id"].drop_duplicates().head(2))

fig, ax = plt.subplots(figsize=(12, 5))

for vid in seleccionados:
    grupo = df[df["id"] == vid].sort_values("tiempo")

    # Separar líneas ante huecos temporales.
    bloques = (
        grupo["tiempo"].diff().fillna(paso) > paso * 1.01
    ).cumsum()

    for numero, (_, bloque) in enumerate(grupo.groupby(bloques)):
        ax.plot(
            bloque["tiempo"],
            bloque["velocidad"],
            linewidth=1,
            label=vid if numero == 0 else "_nolegend_",
            color=f"C{seleccionados.index(vid)}",
        )

ax.set(
    title="Velocidad de vehículos seleccionados",
    xlabel="Tiempo de simulación (s)",
    ylabel="Velocidad (m/s)",
)
ax.legend()
ax.grid(alpha=0.25)
guardar(fig, "T5_velocidad_Suarez.png")

# 4. Evolución de velocidad media y vehículos detenidos.
temporal = df.groupby("tiempo").agg(
    vehiculos=("id", "size"),
    velocidad_media_m_s=("velocidad", "mean"),
    detenidos=("velocidad", lambda v: (v < 0.1).sum()),
)
temporal["detenidos_pct"] = (
    100 * temporal["detenidos"] / temporal["vehiculos"]
)

fig, ejes = plt.subplots(
    2, 1, figsize=(12, 7), sharex=True
)

ejes[0].plot(
    temporal.index,
    temporal["velocidad_media_m_s"],
    linewidth=0.8,
)
ejes[0].set_ylabel("Velocidad media (m/s)")
ejes[0].set_title("Evolución de la movilidad en la red")

ejes[1].plot(
    temporal.index,
    temporal["detenidos_pct"],
    color="crimson",
    linewidth=0.8,
)
ejes[1].set_ylabel("Vehículos detenidos (%)")
ejes[1].set_xlabel("Tiempo de simulación (s)")

for ax in ejes:
    ax.grid(alpha=0.25)

guardar(fig, "T5_movilidad_temporal_Suarez.png")

# 5. Tablas para el informe.
por_tipo = df.groupby("tipo").agg(
    muestras=("velocidad", "size"),
    velocidad_media_m_s=("velocidad", "mean"),
    velocidad_maxima_m_s=("velocidad", "max"),
    espera_pct=("velocidad", lambda v: 100 * (v < 0.1).mean()),
)
por_tipo.to_csv(salida / "estadisticas_fcd_por_tipo.csv")
temporal.to_csv(salida / "movilidad_temporal.csv")

media = df["velocidad"].mean()
espera = 100 * (df["velocidad"] < 0.1).mean()

resumen = pd.DataFrame([{
    "vehiculos_observados": df["id"].nunique(),
    "muestras": len(df),
    "velocidad_media_m_s": media,
    "velocidad_media_km_h": media * 3.6,
    "velocidad_maxima_m_s": df["velocidad"].max(),
    "muestras_detenidas_pct": espera,
}])
resumen.to_csv(salida / "resumen_fcd.csv", index=False)

print("\nRESUMEN FCD")
print(resumen.round(3).to_string(index=False))

print("\nPOR TIPO DE VEHÍCULO")
print(por_tipo.round(3).to_string())

print("\nVehículos seleccionados:", ", ".join(seleccionados))
print("Carpeta de resultados:", salida)
print(
    "\nLa media global pondera cada muestra vehículo-tiempo. "
    "El FCD no registra el movimiento dentro del buffer "
    "de teleporting."
)
