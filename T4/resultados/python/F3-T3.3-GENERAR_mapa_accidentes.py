#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F3-T3.3: mapa de los accidentes bus-moto confirmados en Cuenca.

Entradas:
  reto/cuenca_ciudad.net.xml
  reto/resultados/salida/F3-T3.2-ACCIDENTES_confirmados.csv
Salida:
  reto/resultados/graficas/F3-T3.3-MAPA_accidentes.png

Las posiciones se calculan a partir del ID del carril y posicion_m del
CSV (coordenadas SUMO). No se usan coordenadas de hospitales ni se inventan
puntos para accidentes cuyas aristas/carriles no puedan resolverse.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# Preferir la instalacion de herramientas correspondiente a SUMO 1.12.
SUMO_TOOLS = Path(os.environ.get("SUMO_HOME", "/usr/share/sumo")) / "tools"
if SUMO_TOOLS.is_dir():
    sys.path.insert(0, str(SUMO_TOOLS))

import sumolib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

RETO = Path(__file__).resolve().parents[2]
RED = RETO / "cuenca_ciudad.net.xml"
CSV = RETO / "resultados/salida/F3-T3.2-ACCIDENTES_confirmados.csv"
PNG = RETO / "resultados/graficas/F3-T3.3-MAPA_accidentes.png"


def punto_sobre_linea(shape, distancia):
    """Interpolacion sobre polilinea SUMO en metros; extremos limitados."""
    if not shape:
        raise ValueError("Geometria vacia")
    if len(shape) == 1:
        return shape[0]
    restante = max(0.0, float(distancia))
    for (x1, y1), (x2, y2) in zip(shape[:-1], shape[1:]):
        tramo = ((x2-x1)**2 + (y2-y1)**2)**0.5
        if tramo <= 0:
            continue
        if restante <= tramo:
            f = restante / tramo
            return (x1 + f*(x2-x1), y1 + f*(y2-y1))
        restante -= tramo
    return shape[-1]


def cargar_accidentes(red):
    with CSV.open(newline="", encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    puntos = []
    errores = []
    for fila in filas:
        if str(fila.get("confirmado", "")).strip() not in ("1", "true", "True"):
            continue
        acc = fila.get("accidente", "SIN_ID")
        try:
            edge = red.getEdge(fila["arista"])
            carril_id = fila.get("carril", "")
            carril = next((lane for lane in edge.getLanes() if lane.getID() == carril_id), None)
            # La posicion del CSV corresponde al carril de la colision.
            if carril is None:
                raise ValueError(f"Carril {carril_id!r} no encontrado en {fila['arista']!r}")
            pos = float(fila["posicion_m"])
            x, y = punto_sobre_linea(carril.getShape(), pos)
            puntos.append({"id": acc, "hora": int(float(fila["hora"])), "x": x, "y": y,
                           "arista": fila["arista"], "posicion": pos})
        except (KeyError, ValueError, TypeError) as exc:
            errores.append((acc, str(exc)))
    return filas, puntos, errores


def main():
    if not RED.is_file() or not CSV.is_file():
        raise SystemExit(f"Falta la red o el CSV:\n- {RED}\n- {CSV}")
    PNG.parent.mkdir(parents=True, exist_ok=True)
    print("=" * 65)
    print("F3-T3.3 - MAPA DE ACCIDENTES BUS-MOTO EN CUENCA")
    print("=" * 65)
    print("Red:", RED)
    print("CSV:", CSV)
    red = sumolib.net.readNet(str(RED), withInternal=True)
    filas, puntos, errores = cargar_accidentes(red)

    if not puntos:
        raise SystemExit("No se encontraron accidentes confirmados con geometria valida.")
    segmentos = []
    for edge in red.getEdges(withInternal=False):
        for lane in edge.getLanes():
            shape = lane.getShape()
            if len(shape) > 1:
                segmentos.extend([[shape[i], shape[i + 1]] for i in range(len(shape) - 1)])
                break  # Una polilinea por arista, no por carril

    fig, ax = plt.subplots(figsize=(13, 11))
    ax.add_collection(LineCollection(segmentos, colors="#a4aab1", linewidths=0.55,
                                     alpha=0.7, zorder=1))
    colores = {1: "#e34a33", 2: "#fd8d3c", 3: "#7a3db8"}
    for hora in (1, 2, 3):
        datos = [p for p in puntos if p["hora"] == hora]
        if not datos:
            continue
        ax.scatter([p["x"] for p in datos], [p["y"] for p in datos],
                   s=90, c=colores[hora], edgecolors="white", linewidths=1.1,
                   label=f"Hora {hora}: {len(datos)} accidentes", zorder=3)
    # Identificadores con un pequeno desplazamiento para leerlos con claridad.
    xs = [p["x"] for p in puntos]
    ys = [p["y"] for p in puntos]
    dx = max(max(xs)-min(xs), 1) * 0.012
    dy = max(max(ys)-min(ys), 1) * 0.012
    for i, p in enumerate(puntos):
        ax.annotate(p["id"], (p["x"], p["y"]),
                    xytext=(7 if i % 2 == 0 else -8, 7 if i % 3 else -10),
                    textcoords="offset points", fontsize=8, fontweight="bold",
                    color="#19293a", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                              alpha=0.82, edgecolor="none"))
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0.055)
    ax.set_title("F3-T3.3 - Localizacion de accidentes bus-moto en Cuenca",
                 fontsize=15, fontweight="bold", pad=16)
    ax.set_xlabel("Coordenada SUMO X (m)")
    ax.set_ylabel("Coordenada SUMO Y (m)")
    ax.legend(loc="upper right", frameon=True, title="Accidentes confirmados")
    ax.grid(alpha=0.13)
    ax.text(0.01, -0.09, "Fuente: cuenca_ciudad.net.xml y F3-T3.2-ACCIDENTES_confirmados.csv",
            transform=ax.transAxes, fontsize=9, color="#59636e")
    fig.subplots_adjust(bottom=0.14)
    fig.savefig(PNG, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Registros CSV: {len(filas)}")
    print(f"Accidentes georreferenciados: {len(puntos)}")
    for hora in (1, 2, 3):
        print(f"Hora {hora}: {sum(p['hora']==hora for p in puntos)}")
    if errores:
        print("[ADVERTENCIA] Eventos sin punto valido:")
        for acc, error in errores:
            print(f"  {acc}: {error}")
    print("Grafica generada:", PNG)
    if len(puntos) == 15 and all(sum(p['hora']==h for p in puntos) == 5 for h in (1,2,3)):
        print("[OK] Se ubicaron los 15 accidentes, 5 por hora.")
    else:
        print("[REVISAR] La cantidad de puntos no coincide con el objetivo 15 (5 por hora).")


if __name__ == "__main__":
    main()
