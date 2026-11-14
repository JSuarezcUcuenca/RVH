from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

base = Path(__file__).resolve().parent.parent
config = ET.parse(base / "cuenca.sumocfg").getroot()

archivo = Path(
    config.find("./output/emission-output").get("value")
)
if not archivo.is_absolute():
    archivo = base / archivo

paso = float(config.find("./time/step-length").get("value"))
salida = base / "Graficas" / archivo.parent.name
salida.mkdir(parents=True, exist_ok=True)

filas = []

for _, elemento in ET.iterparse(archivo, events=("end",)):
    if elemento.tag != "timestep":
        continue

    tiempo = float(elemento.get("time"))
    vehiculos = elemento.findall("vehicle")

    tasa_mg_s = sum(
        float(v.get("CO2", 0))
        for v in vehiculos
    )

    filas.append((tiempo, tasa_mg_s / 1000, len(vehiculos)))
    elemento.clear()

df = pd.DataFrame(
    filas,
    columns=["tiempo_s", "co2_g_s", "vehiculos"],
).sort_values("tiempo_s")

if df.empty:
    raise SystemExit("No hay datos de emisiones.")

if len(df) > 1:
    diferencias = np.diff(df["tiempo_s"])
    if not np.allclose(diferencias, paso):
        raise SystemExit(
            "El muestreo no coincide con el paso configurado. "
            "Se requiere revisar la integración."
        )

df["co2_acumulado_kg"] = (
    df["co2_g_s"] * paso / 1000
).cumsum()

df.to_csv(salida / "co2_temporal.csv", index=False)

fig, ejes = plt.subplots(
    2, 1,
    figsize=(13, 8),
    sharex=True,
    constrained_layout=True,
)

ejes[0].plot(df["tiempo_s"], df["co2_g_s"], linewidth=0.8)
ejes[0].set_title("Emisiones instantáneas de la red")
ejes[0].set_ylabel("CO₂ (g/s)")

ejes[1].plot(
    df["tiempo_s"],
    df["co2_acumulado_kg"],
    color="crimson",
)
ejes[1].set_title("Emisiones acumuladas")
ejes[1].set_ylabel("CO₂ (kg)")
ejes[1].set_xlabel("Tiempo de simulación (s)")

for ax in ejes:
    ax.grid(alpha=0.25)

total = df["co2_acumulado_kg"].iloc[-1]
fig.suptitle(
    f"CO₂ | Escenario 3800 veh/h | Total: {total:.3f} kg"
)

fig.savefig(
    salida / "T5_CO2_temporal_Suarez.png",
    dpi=250,
    bbox_inches="tight",
)
plt.close(fig)

pico = df.loc[df["co2_g_s"].idxmax()]

print(f"CO₂ total: {total:.3f} kg")
print(f"Tasa media: {df['co2_g_s'].mean():.3f} g/s")
print(
    f"Tasa máxima: {pico['co2_g_s']:.3f} g/s "
    f"en t = {pico['tiempo_s']:.0f} s"
)
print("Gráfica:", salida / "T5_CO2_temporal_Suarez.png")
