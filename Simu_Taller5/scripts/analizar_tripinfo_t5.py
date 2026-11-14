from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Localizar la ejecución configurada.
base = Path(__file__).resolve().parent.parent
config = ET.parse(base / "cuenca.sumocfg").getroot()

ruta_xml = Path(
    config.find("./output/tripinfo-output").get("value")
)
if not ruta_xml.is_absolute():
    ruta_xml = base / ruta_xml

entrada = ruta_xml.with_suffix(".csv")

if not entrada.is_file():
    raise SystemExit(
        f"No existe {entrada}\n"
        "Primero completa la conversión XML a CSV."
    )

# Cada ejecución tiene su propia carpeta de gráficas.
salida = base / "Graficas" / ruta_xml.parent.name
salida.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(entrada, sep=None, engine="python")

metricas = {
    "tripinfo_routeLength": ("Distancia recorrida", "m"),
    "tripinfo_duration": ("Duración del viaje", "s"),
    "tripinfo_waitingTime": ("Tiempo de espera", "s"),
    "emissions_CO2_abs": ("CO₂ por viaje", "mg"),
}

faltantes = set(metricas) - set(df.columns)
if faltantes:
    raise SystemExit(
        "Faltan columnas: " + ", ".join(sorted(faltantes))
    )

for columna in metricas:
    df[columna] = pd.to_numeric(df[columna], errors="coerce")

if df.empty:
    raise SystemExit("El CSV no contiene viajes.")

if df[list(metricas)].isna().any().any():
    raise SystemExit(
        "Hay valores vacíos o no numéricos. "
        "Revisa el CSV antes de calcular estadísticas."
    )

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 14,
    "figure.dpi": 120,
})

# Índices vinculados con los identificadores reales.
df = df.reset_index(drop=True)
df["indice_grafica"] = np.arange(1, len(df) + 1)

columnas_id = [
    c for c in ("indice_grafica", "tripinfo_id")
    if c in df.columns
]
df[columnas_id].to_csv(
    salida / "correspondencia_indices_vehiculos.csv",
    index=False,
)

def guardar(fig, nombre):
    fig.tight_layout()
    archivo = salida / nombre
    fig.savefig(archivo, dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("Guardado:", archivo.name)

# Gráficas individuales solicitadas en la Parte II.
graficas = [
    ("tripinfo_routeLength", "T5_distancia_Suarez.png"),
    ("emissions_CO2_abs", "T5_CO2_por_viaje_Suarez.png"),
    ("tripinfo_duration", "T5_duracion_Suarez.png"),
]

for columna, nombre in graficas:
    titulo, unidad = metricas[columna]

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.scatter(
        df["indice_grafica"],
        df[columna],
        s=12,
        alpha=0.7,
        color="#176b91",
    )
    ax.set_title(titulo + " por viaje completado")
    ax.set_xlabel("Índice del viaje en el CSV")
    ax.set_ylabel(f"{titulo} ({unidad})")
    ax.grid(alpha=0.25)

    guardar(fig, nombre)

# Histograma de duración.
duracion = df["tripinfo_duration"]

fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(
    duracion,
    bins="auto",
    color="#176b91",
    edgecolor="white",
)
ax.axvline(
    duracion.mean(),
    color="crimson",
    linestyle="--",
    label=f"Media: {duracion.mean():.2f} s",
)
ax.axvline(
    duracion.median(),
    color="darkorange",
    linestyle=":",
    label=f"Mediana: {duracion.median():.2f} s",
)
ax.set_title("Distribución de tiempos de viaje completados")
ax.set_xlabel("Duración (s)")
ax.set_ylabel("Número de viajes")
ax.legend()
ax.grid(axis="y", alpha=0.25)

guardar(fig, "T5_histograma_duracion_Suarez.png")

# Relación distancia-duración.
fig, ax = plt.subplots(figsize=(9, 6))
puntos = ax.scatter(
    df["tripinfo_routeLength"],
    df["tripinfo_duration"],
    c=df["tripinfo_waitingTime"],
    cmap="viridis",
    s=22,
    alpha=0.75,
)
fig.colorbar(puntos, ax=ax, label="Tiempo de espera (s)")
ax.set_title("Distancia frente a duración del viaje")
ax.set_xlabel("Distancia recorrida (m)")
ax.set_ylabel("Duración (s)")
ax.grid(alpha=0.25)

guardar(fig, "T5_distancia_duracion_Suarez.png")

# Estadísticas: desviación estándar muestral (n-1).
filas = []

for columna, (nombre, unidad) in metricas.items():
    valores = df[columna]
    filas.append({
        "Metrica": nombre,
        "Unidad": unidad,
        "Viajes": len(valores),
        "Media": valores.mean(),
        "Desviacion_estandar": valores.std(ddof=1),
        "Mediana": valores.median(),
        "Minimo": valores.min(),
        "Maximo": valores.max(),
    })

tabla = pd.DataFrame(filas)
tabla.to_csv(
    salida / "estadisticas_tripinfo.csv",
    index=False,
    float_format="%.6f",
)

print("\nESTADÍSTICAS DE VIAJES COMPLETADOS")
print(tabla.round(3).to_string(index=False))

print(f"\nViajes analizados: {len(df)}")
print(
    "CO₂ de los viajes incluidos: "
    f"{df['emissions_CO2_abs'].sum() / 1e6:.3f} kg"
)

tiempo_total = df["tripinfo_duration"].sum()
if tiempo_total > 0:
    porcentaje = (
        100 * df["tripinfo_waitingTime"].sum() / tiempo_total
    )
    print(
        "Espera / duración de viajes incluidos: "
        f"{porcentaje:.2f} %"
    )

print("\nCarpeta de resultados:", salida)
print(
    "Estas estadísticas corresponden a los viajes registrados "
    "en tripinfo; no incluyen los que seguían circulando al cierre."
)
