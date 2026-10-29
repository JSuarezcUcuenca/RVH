
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSIDAD DE CUENCA
REDES VEHICULARES Y HETEROGENEAS

FASE 2 - HOSPITALES Y FLOTA DE AMBULANCIAS

T2.1: Ubicacion de hospitales
T2.2: Flota y disponibilidad aleatoria
T2.3: Ambulancia de prueba VCM -> IESS

Compatible con SUMO 1.12.0.
"""

from pathlib import Path
from collections import deque
import csv
import os
import random
import math
import sys

# Utilizar TraCI incluido con SUMO 1.12
sys.path.insert(0, "/usr/share/sumo/tools")

import traci


# ====================================================
# CONFIGURACION
# ====================================================

RETO = Path(__file__).resolve().parents[2]
SALIDA = RETO / "resultados" / "salida"

SALIDA.mkdir(parents=True, exist_ok=True)

CONFIG = RETO / "F2-reto.sumocfg"

SEMILLA = 42
PROB_RECHAZO = 0.25
DESPACHO_SEGUNDO = 120
TIEMPO_LIMITE = 3600

rng = random.Random(SEMILLA)


# ====================================================
# PRESENTACION DE RESULTADOS
# ====================================================

ANCHO = 94


def titulo(texto):
    print()
    print("=" * ANCHO)
    print(texto.center(ANCHO))
    print("=" * ANCHO)


def subtitulo(texto):
    print()
    print("-" * ANCHO)
    print(texto)
    print("-" * ANCHO)


def mensaje(texto):
    print(f"  {texto}")


def resultado(etiqueta, valor):
    print(f"  {etiqueta:<35}: {valor}")


def correcto(texto):
    print(f"  [OK] {texto}")


def advertencia(texto):
    print(f"  [AVISO] {texto}")


def tabla(encabezados, filas, anchos):
    formato = " | ".join(
        "{:<" + str(a) + "}" for a in anchos
    )

    print(formato.format(*encabezados))
    print("-" * (sum(anchos) + 3 * (len(anchos) - 1)))

    for fila in filas:
        print(formato.format(*[
            str(v) for v in fila
        ]))


# ====================================================
# HOSPITALES
# ====================================================

HOSPITALES = {
    "VCM": {
        "nombre": "Vicente Corral Moscoso",
        "tipo": "Publico",
        "lon": -78.992923,
        "lat": -2.911098
    },
    "IESS_JCA": {
        "nombre": "Jose Carrasco Arteaga",
        "tipo": "Publico",
        "lon": -78.970118,
        "lat": -2.898698
    },
    "MILITAR": {
        "nombre": "Militar Tarqui",
        "tipo": "Publico",
        "lon": -79.003968,
        "lat": -2.903146
    },
    "MUNI_PAT": {
        "nombre": "Municipal Patamarca",
        "tipo": "Publico",
        "lon": -78.982263,
        "lat": -2.866103
    },
    "MUNI_VALLE": {
        "nombre": "Municipal El Valle",
        "tipo": "Publico",
        "lon": -78.961959,
        "lat": -2.919522
    },
    "MONTE_SINAI": {
        "nombre": "Monte Sinai",
        "tipo": "Privado",
        "lon": -79.007373,
        "lat": -2.908606
    },
    "DEL_RIO": {
        "nombre": "Hospital del Rio",
        "tipo": "Privado",
        "lon": -78.960796,
        "lat": -2.892939
    }
}


# ====================================================
# GUARDAR CSV
# ====================================================

def guardar_csv(nombre, registros):

    if not registros:
        return

    archivo = SALIDA / nombre

    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(registros[0].keys())
        )

        writer.writeheader()
        writer.writerows(registros)

    return archivo


# ====================================================
# F2 - T2.1: UBICACION DE HOSPITALES
# ====================================================

def tarea_21():

    titulo("F2 - T2.1 | UBICACION DE HOSPITALES")

    mensaje("Ubicando hospitales mediante coordenadas WGS84...")
    mensaje("Buscando aristas aptas para vehiculos de emergencia.")

    registros = []
    filas = []

    for hid, hospital in HOSPITALES.items():

        lon = hospital["lon"]
        lat = hospital["lat"]

        edge, pos, lane = traci.simulation.convertRoad(
            lon,
            lat,
            isGeo=True,
            vClass="emergency"
        )

        if not edge or edge.startswith(":"):
            raise RuntimeError(
                f"Arista no valida para {hid}: {edge}"
            )

        calle = traci.edge.getStreetName(edge)

        hx, hy = traci.simulation.convertGeo(
            lon, lat, fromGeo=True
        )

        ex, ey = traci.simulation.convert2D(
            edge, pos, lane
        )

        distancia = math.hypot(hx - ex, hy - ey)

        hospital["edge"] = edge
        hospital["pos"] = pos
        hospital["lane"] = lane
        hospital["distancia"] = distancia

        # POI compatible con SUMO 1.12.0
        traci.poi.add(
            poiID="HOSP_" + hid,
            x=hx,
            y=hy,
            color=(255, 0, 0),
            poiType="hospital",
            layer=100
        )

        estado = "OK" if distancia < 150 else "REVISAR"

        filas.append([
            hid,
            hospital["tipo"],
            edge,
            f"{distancia:.1f}",
            estado
        ])

        registros.append({
            "hospital": hid,
            "nombre": hospital["nombre"],
            "tipo": hospital["tipo"],
            "lon": lon,
            "lat": lat,
            "arista": edge,
            "posicion_m": round(pos, 2),
            "carril": lane,
            "calle": calle,
            "distancia_m": round(distancia, 2),
            "estado": estado
        })

    subtitulo("TABLA 2.1 - HOSPITALES LOCALIZADOS")

    tabla(
        ["Hospital", "Tipo", "Arista SUMO", "Dist. m", "Estado"],
        filas,
        [14, 9, 24, 9, 8]
    )

    validos = sum(
        h["distancia"] < 150
        for h in HOSPITALES.values()
    )

    subtitulo("VALIDACION T2.1")

    resultado("Hospitales registrados", len(HOSPITALES))
    resultado("Hospitales a menos de 150 m", f"{validos}/7")

    distancia_max = max(
        h["distancia"] for h in HOSPITALES.values()
    )

    resultado(
        "Distancia maxima",
        f"{distancia_max:.2f} m"
    )

    if validos == 7:
        correcto("T2.1 APROBADA: todos los hospitales cumplen.")
    else:
        advertencia("Existen hospitales pendientes de revisar.")

    archivo = guardar_csv(
        "F2-T2.1-HOSPITALES_ubicaciones.csv",
        registros
    )

    mensaje(f"CSV: {archivo.name}")

    return validos == 7


# ====================================================
# F2 - T2.2: FLOTA ALEATORIA
# ====================================================

def tarea_22():

    titulo("F2 - T2.2 | FLOTA Y DISPONIBILIDAD")

    mensaje("Generando ambulancias con semilla 42...")
    mensaje("Hospitales publicos: 1 a 3 unidades.")
    mensaje("Hospitales privados: 0 a 1 unidad.")

    contador = 1
    registros = []
    filas = []

    for hid, hospital in HOSPITALES.items():

        if hospital["tipo"] == "Publico":
            stock = rng.randint(1, 3)
        else:
            stock = rng.randint(0, 1)

        unidades = deque()

        for _ in range(stock):
            unidad = f"U{contador:02d}"
            unidades.append(unidad)
            contador += 1

        hospital["unidades"] = unidades
        hospital["stock_inicial"] = stock
        hospital["rechazos_sin_stock"] = 0
        hospital["rechazos_aleatorios"] = 0

        filas.append([
            hid,
            hospital["tipo"],
            stock,
            ", ".join(unidades) or "SIN UNIDADES"
        ])

        registros.append({
            "hospital": hid,
            "tipo": hospital["tipo"],
            "stock_inicial": stock,
            "unidades": ";".join(unidades)
        })

    subtitulo("TABLA 2.2 - INVENTARIO INICIAL")

    tabla(
        ["Hospital", "Tipo", "Stock", "Ambulancias"],
        filas,
        [16, 10, 7, 28]
    )

    total = sum(
        h["stock_inicial"]
        for h in HOSPITALES.values()
    )

    sin_stock = [
        hid
        for hid, h in HOSPITALES.items()
        if h["stock_inicial"] == 0
    ]

    subtitulo("VALIDACION T2.2")

    resultado("Total de ambulancias", total)
    resultado("Semilla utilizada", SEMILLA)
    resultado("Probabilidad de rechazo", "25 %")
    resultado("Politica de inventario", "FIFO (deque)")
    resultado("Hospitales sin unidades", len(sin_stock))
    resultado(
        "Lista de hospitales sin stock",
        ", ".join(sin_stock) or "Ninguno"
    )

    reglas_validas = all(
        (
            1 <= h["stock_inicial"] <= 3
            if h["tipo"] == "Publico"
            else 0 <= h["stock_inicial"] <= 1
        )
        for h in HOSPITALES.values()
    )

    if reglas_validas:
        correcto("T2.2 APROBADA: stock dentro de los rangos.")
    else:
        advertencia("Hay hospitales con stock fuera de rango.")

    mensaje(
        "La probabilidad de rechazo se utilizara "
        "en los despachos de F4."
    )

    archivo = guardar_csv(
        "F2-T2.2-FLOTA_inicial.csv",
        registros
    )

    mensaje(f"CSV: {archivo.name}")

    return reglas_validas


# ====================================================
# GESTION DE DISPONIBILIDAD
# ====================================================

def solicitar_unidad(hid):

    hospital = HOSPITALES[hid]

    if not hospital["unidades"]:
        hospital["rechazos_sin_stock"] += 1
        return None

    if rng.random() < PROB_RECHAZO:
        hospital["rechazos_aleatorios"] += 1
        return None

    return hospital["unidades"].popleft()


def devolver_unidad(hid, unidad):
    HOSPITALES[hid]["unidades"].append(unidad)


# ====================================================
# F2 - T2.3: DESPACHO DE AMBULANCIA
# ====================================================

def tarea_23_despacho():

    titulo("F2 - T2.3 | PRUEBA DE AMBULANCIA")

    origen_id = "VCM"
    destino_id = "IESS_JCA"

    origen = HOSPITALES[origen_id]
    destino = HOSPITALES[destino_id]

    ruta = traci.simulation.findRoute(
        origen["edge"],
        destino["edge"],
        vType="ambulance"
    )

    if not ruta.edges:
        raise RuntimeError(
            "No existe una ruta VCM -> IESS."
        )

    if not origen["unidades"]:
        raise RuntimeError(
            "VCM no tiene ambulancias disponibles."
        )

    traci.route.add(
        "F2_RUTA_PRUEBA",
        list(ruta.edges)
    )

    # Prueba controlada: no aplicar rechazo aleatorio
    unidad = origen["unidades"].popleft()
    vehiculo = "F2_AMB_" + unidad

    traci.vehicle.add(
        vehID=vehiculo,
        routeID="F2_RUTA_PRUEBA",
        typeID="ambulance",
        depart="now",
        departPos=str(max(0, origen["pos"] - 1)),
        departSpeed="0"
    )

    tiempo = traci.simulation.getTime()

    subtitulo("DATOS DE LA MISION")

    resultado("Unidad despachada", unidad)
    resultado("Origen", origen["nombre"])
    resultado("Destino", destino["nombre"])
    resultado("Segundo de despacho", f"{tiempo:.0f} s")
    resultado("Aristas de la ruta", len(ruta.edges))
    resultado("Distancia estimada", f"{ruta.length:.2f} m")
    resultado("ETA estimada", f"{ruta.travelTime:.2f} s")

    correcto("Despacho solicitado correctamente.")

    return {
        "unidad": unidad,
        "vehiculo": vehiculo,
        "origen": origen_id,
        "destino": destino_id,
        "t_despacho": tiempo,
        "t_insercion": None,
        "eta": ruta.travelTime,
        "distancia": ruta.length,
        "aristas": len(ruta.edges)
    }


# ====================================================
# F2 - T2.3: LLEGADA Y EVALUACION
# ====================================================

def tarea_23_llegada(mision, tiempo):

    real = tiempo - mision["t_despacho"]
    diferencia = real - mision["eta"]

    porcentaje = (
        diferencia / mision["eta"] * 100
        if mision["eta"] > 0 else 0
    )

    subtitulo("RESULTADOS DE LA MISION")

    resultado(
        "Unidad",
        mision["unidad"]
    )
    resultado(
        "Tiempo de despacho",
        f"{mision['t_despacho']:.0f} s"
    )
    resultado(
        "Tiempo de insercion",
        f"{mision['t_insercion']:.0f} s"
        if mision["t_insercion"] is not None
        else "No registrado"
    )
    resultado(
        "Tiempo de llegada",
        f"{tiempo:.0f} s"
    )
    resultado(
        "Tiempo estimado (ETA)",
        f"{mision['eta']:.2f} s"
    )
    resultado(
        "Tiempo real",
        f"{real:.2f} s"
    )
    resultado(
        "Diferencia real - ETA",
        f"{diferencia:+.2f} s"
    )
    resultado(
        "Variacion respecto a ETA",
        f"{porcentaje:+.2f} %"
    )

    subtitulo("VALIDACION T2.3")

    correcto("La ambulancia llego al hospital destino.")
    correcto("La ruta y los tiempos fueron registrados.")

    registros = [{
        "unidad": mision["unidad"],
        "origen": mision["origen"],
        "destino": mision["destino"],
        "t_despacho": mision["t_despacho"],
        "t_insercion": mision["t_insercion"],
        "t_llegada": tiempo,
        "tiempo_real_s": round(real, 2),
        "eta_s": round(mision["eta"], 2),
        "diferencia_s": round(diferencia, 2),
        "variacion_pct": round(porcentaje, 2),
        "distancia_ruta_m": round(mision["distancia"], 2),
        "aristas": mision["aristas"]
    }]

    archivo = guardar_csv(
        "F2-T2.3-AMBULANCIA_prueba.csv",
        registros
    )

    mensaje(f"CSV: {archivo.name}")

    # Devolucion logica, no desplazamiento fisico.
    devolver_unidad(
        mision["destino"],
        mision["unidad"]
    )

    mensaje(
        "Unidad incorporada al inventario del IESS "
        "(retorno logico de prueba)."
    )


# ====================================================
# RESUMEN FINAL
# ====================================================

def resumen_final(estados):

    titulo("RESUMEN FINAL | FASE 2")

    tabla(
        ["Tarea", "Descripcion", "Estado"],
        [
            [
                "T2.1",
                "Ubicacion de 7 hospitales",
                "COMPLETADA" if estados["T2.1"] else "REVISAR"
            ],
            [
                "T2.2",
                "Flota inicial aleatoria",
                "COMPLETADA" if estados["T2.2"] else "REVISAR"
            ],
            [
                "T2.3",
                "Recorrido VCM - IESS",
                "COMPLETADA" if estados["T2.3"] else "REVISAR"
            ]
        ],
        [10, 40, 15]
    )

    subtitulo("ARCHIVOS GENERADOS")

    for nombre in [
        "F2-T2.1-HOSPITALES_ubicaciones.csv",
        "F2-T2.2-FLOTA_inicial.csv",
        "F2-T2.3-AMBULANCIA_prueba.csv"
    ]:

        archivo = SALIDA / nombre
        estado = "[OK]" if archivo.exists() else "[PENDIENTE]"
        mensaje(f"{estado} {nombre}")

    print()

    if all(estados.values()):
        correcto("FASE 2: TODAS LAS TAREAS COMPLETADAS.")
    else:
        advertencia("FASE 2: EXISTEN VALIDACIONES PENDIENTES.")

    print("=" * ANCHO)


# ====================================================
# PROGRAMA PRINCIPAL
# ====================================================

def ejecutar():

    titulo("RETO ACCIDENTES BUS-MOTO Y AMBULANCIAS")
    mensaje("Universidad de Cuenca")
    mensaje("Fase 2: Hospitales y flota de ambulancias")
    mensaje("SUMO 1.12.0 + TraCI")
    mensaje(f"Semilla de simulacion: {SEMILLA}")

    if not CONFIG.exists():
        raise FileNotFoundError(
            f"No existe: {CONFIG}"
        )

    os.chdir(RETO)

    binario = (
        "sumo-gui"
        if "--gui" in sys.argv
        else "sumo"
    )

    # Suprimir advertencias y mensajes de paso
    # en consola; el archivo de resultados CSV
    # sigue generandose normalmente.
    traci.start([
        binario,
        "-c", str(CONFIG),
        "--seed", str(SEMILLA),
        "--start",
        "--no-step-log", "true",
        "--no-warnings", "true"
    ])

    estados = {
        "T2.1": False,
        "T2.2": False,
        "T2.3": False
    }

    try:

        estados["T2.1"] = tarea_21()
        estados["T2.2"] = tarea_22()

        subtitulo("EJECUCION DE LA SIMULACION")
        mensaje(
            f"Despacho programado en t={DESPACHO_SEGUNDO} s."
        )

        mision = None
        despacho_realizado = False

        while traci.simulation.getTime() < TIEMPO_LIMITE:

            traci.simulationStep()
            tiempo = traci.simulation.getTime()

            if (
                tiempo >= DESPACHO_SEGUNDO
                and not despacho_realizado
            ):
                despacho_realizado = True
                mision = tarea_23_despacho()

            if mision is None:
                continue

            activos = set(traci.vehicle.getIDList())
            llegados = set(
                traci.simulation.getArrivedIDList()
            )

            if (
                mision["t_insercion"] is None
                and mision["vehiculo"] in activos
            ):
                mision["t_insercion"] = tiempo
                mensaje(
                    f"Ambulancia insertada en t={tiempo:.0f} s."
                )

            if mision["vehiculo"] in llegados:

                tarea_23_llegada(mision, tiempo)

                estados["T2.3"] = True
                break

        if not estados["T2.3"]:
            advertencia(
                "La ambulancia no llego antes "
                f"de t={TIEMPO_LIMITE} s."
            )

        resumen_final(estados)

    finally:
        traci.close()


if __name__ == "__main__":
    ejecutar()
