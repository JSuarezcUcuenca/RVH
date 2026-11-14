
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RETO ACCIDENTES BUS-MOTO Y AMBULANCIAS
UNIVERSIDAD DE CUENCA

FASE 3 - ACCIDENTES BUS-MOTO

T3.1 - Programacion de cinco accidentes por hora
T3.2 - Generacion y deteccion de colisiones
T3.3 - Registro, validacion y estadisticas

SUMO 1.12.0 + TraCI
"""

from pathlib import Path
from collections import Counter
import csv
import os
import random
import sys

sys.path.insert(0, "/usr/share/sumo/tools")

import traci


# ====================================================
# 1. CONFIGURACION
# ====================================================

RETO = Path(__file__).resolve().parents[2]
SALIDA = RETO / "resultados" / "salida"
GRAFICAS = RETO / "resultados" / "graficas"

SALIDA.mkdir(parents=True, exist_ok=True)
GRAFICAS.mkdir(parents=True, exist_ok=True)

CONFIG = RETO / "F3-reto.sumocfg"

SEMILLA = 42
rng = random.Random(SEMILLA)

FIN_DEMANDA = 10800
TOTAL_OBJETIVO = 15
POR_HORA = 5

# Espaciamiento de intentos iniciales
PROGRAMACION = [
    hora * 3600 + minuto
    for hora in range(3)
    for minuto in (300, 900, 1500, 2100, 2700)
]

DURACION_INTENTO = 12
INTERVALO_REINTENTO = 12
VELOCIDAD_IMPACTO = 30.0

ANCHO = 94

programados = []
confirmados = []
naturales = []
intentos = []
buses_usados = set()
pares_confirmados = set()
eventos_vistos = set()

# Motos forzadas pendientes de comprobacion
pendiente = None
siguiente_intento = 300
secuencia_intentos = 0


# ====================================================
# 2. IMPRESION FORMATEADA
# ====================================================

def titulo(texto):
    print("\n" + "=" * ANCHO, flush=True)
    print(texto.center(ANCHO), flush=True)
    print("=" * ANCHO, flush=True)


def seccion(texto):
    print("\n" + "-" * ANCHO, flush=True)
    print(texto, flush=True)
    print("-" * ANCHO, flush=True)


def dato(nombre, valor):
    print(f"  {nombre:<37}: {valor}", flush=True)


def aviso(texto):
    print(f"  [AVISO] {texto}", flush=True)


def ok(texto):
    print(f"  [OK] {texto}", flush=True)


def guardar_csv(nombre, filas, columnas):
    archivo = SALIDA / nombre
    with open(archivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)
    return archivo


# ====================================================
# 3. T3.1 - PROGRAMAR ACCIDENTES
# ====================================================

def tarea_31():

    titulo("F3 - T3.1 | PROGRAMACION DE ACCIDENTES")

    for i, tiempo in enumerate(PROGRAMACION, start=1):
        programados.append({
            "accidente": f"A{i:02d}",
            "hora": int(tiempo // 3600) + 1,
            "segundo_programado": tiempo,
            "minuto_programado": round(tiempo / 60, 2)
        })

    for hora in (1, 2, 3):
        tiempos = [
            p["segundo_programado"]
            for p in programados
            if p["hora"] == hora
        ]
        dato(
            f"Hora {hora} - cinco eventos",
            ", ".join(str(t) for t in tiempos)
        )

    dato("Accidentes objetivo", TOTAL_OBJETIVO)
    dato("Accidentes por hora", POR_HORA)
    dato("Primer accidente programado", "t = 300 s")
    dato("Duracion de demanda", "10800 s")
    dato("Semilla", SEMILLA)

    guardar_csv(
        "F3-T3.1-ACCIDENTES_programados.csv",
        programados,
        [
            "accidente", "hora",
            "segundo_programado", "minuto_programado"
        ]
    )

    ok("T3.1: programacion de 15 eventos creada.")


# ====================================================
# 4. BUSCAR AUTOBUS ADECUADO
# ====================================================

def seleccionar_bus():

    candidatos = []

    for vid in traci.vehicle.getIDList():

        if vid in buses_usados:
            continue

        if traci.vehicle.getTypeID(vid) != "bus":
            continue

        try:
            velocidad = traci.vehicle.getSpeed(vid)
            posicion = traci.vehicle.getLanePosition(vid)
            lane_id = traci.vehicle.getLaneID(vid)

            if lane_id.startswith(":"):
                continue

            largo = traci.lane.getLength(lane_id)

            # Bus movil y suficientemente lejos
            # del inicio y del final de la arista
            if velocidad <= 4.0:
                continue
            if posicion <= 60.0:
                continue
            if largo - posicion <= 25.0:
                continue

            ruta = list(traci.vehicle.getRoute(vid))
            indice = traci.vehicle.getRouteIndex(vid)

            if indice < 0:
                continue

            resto = ruta[indice:]

            if not resto:
                continue

            # Evitar insertar motos cerca de
            # otros vehiculos en el mismo carril
            pos_moto = posicion - 35.0

            if pos_moto < 5:
                continue

            ocupado = False

            for otro in traci.lane.getLastStepVehicleIDs(lane_id):

                if otro == vid:
                    continue

                p = traci.vehicle.getLanePosition(otro)

                if abs(p - pos_moto) < 12:
                    ocupado = True
                    break

            if ocupado:
                continue

            candidatos.append({
                "bus": vid,
                "lane": lane_id,
                "posicion_bus": posicion,
                "posicion_moto": pos_moto,
                "velocidad_bus": velocidad,
                "resto_ruta": resto,
                "edge": traci.vehicle.getRoadID(vid),
                "lane_index": traci.vehicle.getLaneIndex(vid)
            })

        except traci.exceptions.TraCIException:
            continue

    if not candidatos:
        return None

    return rng.choice(candidatos)


# ====================================================
# 5. T3.2 - INICIAR INTENTO DE ACCIDENTE
# ====================================================

def iniciar_intento(numero, tiempo):

    global secuencia_intentos

    candidato = seleccionar_bus()

    if candidato is None:
        return None

    secuencia_intentos += 1

    moto_id = f"F3_MOTO_{secuencia_intentos:03d}"
    ruta_id = f"F3_RUTA_{secuencia_intentos:03d}"

    # Construir una ruta utilizable por la moto.
    # Se intenta conservar parte de la ruta del bus.
    resto = candidato["resto_ruta"]

    try:
        ruta_moto = traci.simulation.findRoute(
            resto[0],
            resto[-1],
            vType="moto"
        )

        edges = list(ruta_moto.edges)

        if not edges or edges[0] != resto[0]:
            return None

        traci.route.add(ruta_id, edges)

        traci.vehicle.add(
            vehID=moto_id,
            routeID=ruta_id,
            typeID="moto",
            depart="now",
            departLane=str(candidato["lane_index"]),
            departPos=str(candidato["posicion_moto"]),
            departSpeed="0"
        )

    except traci.exceptions.TraCIException as exc:
        aviso(f"No fue posible crear la moto: {exc}")
        return None

    evento = {
        "objetivo": f"A{numero:02d}",
        "bus": candidato["bus"],
        "moto": moto_id,
        "lane": candidato["lane"],
        "edge": candidato["edge"],
        "t_inicio": tiempo,
        "bus_pos": candidato["posicion_bus"],
        "moto_pos": candidato["posicion_moto"],
        "insertada": False,
        "activada": False
    }

    intentos.append({
        "objetivo": evento["objetivo"],
        "tiempo": tiempo,
        "bus": evento["bus"],
        "moto": moto_id
    })

    print(
        f"  [INTENTO {evento['objetivo']}] "
        f"t={tiempo:.0f} s | "
        f"Bus={evento['bus']} | Moto={moto_id}",
        flush=True
    )

    return evento


# ====================================================
# 6. FORZAR APROXIMACION DE LA MOTOCICLETA
# ====================================================

def activar_intento(evento):

    moto = evento["moto"]
    bus = evento["bus"]

    activos = set(traci.vehicle.getIDList())

    if moto not in activos or bus not in activos:
        return False

    try:
        lane_actual = traci.vehicle.getLaneID(bus)

        if lane_actual.startswith(":"):
            return False

        pos_bus = traci.vehicle.getLanePosition(bus)
        pos_moto = max(5.0, pos_bus - 30.0)

        # La moto debe compartir la arista del bus
        if traci.vehicle.getRoadID(moto) != \
                traci.vehicle.getRoadID(bus):
            return False

        traci.vehicle.moveTo(
            moto, lane_actual, pos_moto
        )

        # Inhibir cambios de carril
        traci.vehicle.setLaneChangeMode(moto, 0)

        # Desactivar restricciones de velocidad y
        # distancia segura para provocar el impacto
        traci.vehicle.setSpeedMode(moto, 0)
        traci.vehicle.setMaxSpeed(moto, 35.0)
        traci.vehicle.setSpeed(moto, VELOCIDAD_IMPACTO)

        evento["activada"] = True

        return True

    except traci.exceptions.TraCIException:
        return False


# ====================================================
# 7. DETECTAR COLISIONES
# ====================================================

def detener_vehiculo(vid):

    if vid not in traci.vehicle.getIDList():
        return

    try:
        traci.vehicle.setSpeedMode(vid, 0)
        traci.vehicle.setLaneChangeMode(vid, 0)
        traci.vehicle.setSpeed(vid, 0)

    except traci.exceptions.TraCIException:
        pass


def procesar_colisiones(tiempo, evento):

    nueva_confirmacion = False

    for col in traci.simulation.getCollisions():

        veh1 = col.collider
        veh2 = col.victim

        clave = tuple(sorted((veh1, veh2)))

        if evento is not None:
            es_objetivo = (
                clave == tuple(
                    sorted((evento["bus"], evento["moto"]))
                )
            )
        else:
            es_objetivo = False

        if es_objetivo and clave not in pares_confirmados:

            pares_confirmados.add(clave)
            buses_usados.add(evento["bus"])

            detener_vehiculo(evento["bus"])
            detener_vehiculo(evento["moto"])

            registro = {
                "accidente": evento["objetivo"],
                "hora": int(tiempo // 3600) + 1,
                "tiempo_s": tiempo,
                "bus": evento["bus"],
                "moto": evento["moto"],
                "arista": evento["edge"],
                "carril": col.lane,
                "posicion_m": round(col.pos, 2),
                "tipo_colision": col.type,
                "confirmado": 1
            }

            confirmados.append(registro)

            print(
                f"  [COLISION CONFIRMADA] "
                f"{registro['accidente']} | "
                f"t={tiempo:.0f} s | "
                f"{veh1} / {veh2}",
                flush=True
            )

            nueva_confirmacion = True

        elif not es_objetivo:
            # Registrar colisiones naturales una sola vez
            # por pareja y segundo.
            llave_evento = clave

            if llave_evento not in eventos_vistos:
                eventos_vistos.add(llave_evento)

                naturales.append({
                    "tiempo_s": tiempo,
                    "collider": veh1,
                    "victim": veh2,
                    "tipo": col.type,
                    "carril": col.lane
                })

    return nueva_confirmacion


# ====================================================
# 8. LIMPIAR INTENTOS NO CONFIRMADOS
# ====================================================

def limpiar_intento(evento):

    moto = evento["moto"]

    if moto in traci.vehicle.getIDList():
        try:
            traci.vehicle.remove(moto)
        except traci.exceptions.TraCIException:
            pass

    # El bus no se inmoviliza si no hubo choque.
    # No fue alterado durante la prueba.


# ====================================================
# 9. T3.3 - ESTADISTICAS
# ====================================================

def tarea_33():

    titulo("F3 - T3.3 | VALIDACION Y ESTADISTICAS")

    guardar_csv(
        "F3-T3.2-ACCIDENTES_confirmados.csv",
        confirmados,
        [
            "accidente", "hora", "tiempo_s",
            "bus", "moto", "arista", "carril",
            "posicion_m", "tipo_colision", "confirmado"
        ]
    )

    guardar_csv(
        "F3-T3.2-COLISIONES_naturales.csv",
        naturales,
        ["tiempo_s", "collider", "victim", "tipo", "carril"]
    )

    conteo = Counter(x["hora"] for x in confirmados)

    por_hora = [
        {
            "hora": hora,
            "objetivo": 5,
            "confirmados": conteo[hora],
            "faltantes": 5 - conteo[hora]
        }
        for hora in (1, 2, 3)
    ]

    guardar_csv(
        "F3-T3.3-ACCIDENTES_por_hora.csv",
        por_hora,
        ["hora", "objetivo", "confirmados", "faltantes"]
    )

    seccion("ACCIDENTES POR HORA")

    for fila in por_hora:
        dato(
            f"Hora {fila['hora']}",
            f"{fila['confirmados']}/5 confirmados"
        )

    seccion("RESUMEN GENERAL")

    dato("Accidentes programados", 15)
    dato("Accidentes confirmados", len(confirmados))
    dato("Intentos de insercion", len(intentos))
    dato("Colisiones adicionales detectadas", len(naturales))

    correcto_total = (
        len(confirmados) == TOTAL_OBJETIVO
        and all(conteo[h] == 5 for h in (1, 2, 3))
    )

    resumen = [{
        "programados": 15,
        "confirmados": len(confirmados),
        "intentos": len(intentos),
        "colisiones_adicionales": len(naturales),
        "validacion": "OK" if correcto_total else "INCOMPLETA"
    }]

    guardar_csv(
        "F3-T3.3-ACCIDENTES_resumen.csv",
        resumen,
        [
            "programados", "confirmados", "intentos",
            "colisiones_adicionales", "validacion"
        ]
    )

    if correcto_total:
        ok("FASE 3: 15 accidentes, cinco por hora.")
    else:
        aviso(
            "FASE 3: no se confirmaron los 15 accidentes. "
            "Revisar el log antes de avanzar."
        )

    # Grafica
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        horas = [1, 2, 3]
        valores = [conteo[h] for h in horas]

        plt.figure(figsize=(8, 5))
        plt.bar(horas, valores)
        plt.axhline(
            y=5,
            linestyle="--",
            label="Objetivo: 5 por hora"
        )
        plt.xticks(horas, ["Hora 1", "Hora 2", "Hora 3"])
        plt.ylim(0, max(6, max(valores) + 1))
        plt.xlabel("Hora simulada")
        plt.ylabel("Accidentes confirmados")
        plt.title("F3-T3.3 - Accidentes bus-moto por hora")
        plt.legend()
        plt.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(
            GRAFICAS / "F3-T3.3-ACCIDENTES_por_hora.png",
            dpi=300
        )
        plt.close()

        ok("Grafica de accidentes generada.")

    except ImportError:
        aviso("Matplotlib no disponible: grafica omitida.")


# ====================================================
# 10. SIMULACION PRINCIPAL
# ====================================================

def ejecutar():

    global pendiente, siguiente_intento

    titulo("FASE 3 | ACCIDENTES BUS-MOTO")

    if not CONFIG.exists():
        raise FileNotFoundError(
            f"No existe {CONFIG}"
        )

    os.chdir(RETO)

    binario = "sumo-gui" if "--gui" in sys.argv else "sumo"

    # Usar TraCI de SUMO 1.12
    traci.start([
        binario,
        "-c", str(CONFIG),
        "--seed", str(SEMILLA),
        "--no-step-log", "true",
        "--no-warnings", "true",
        "--end", str(FIN_DEMANDA),
        "--start"
    ])

    try:
        if "bus" not in traci.vehicletype.getIDList():
            raise RuntimeError("Falta el vType bus")

        if "moto" not in traci.vehicletype.getIDList():
            raise RuntimeError("Falta el vType moto")

        tarea_31()

        titulo("F3 - T3.2 | GENERACION Y DETECCION")

        indice = 0

        while traci.simulation.getTime() < FIN_DEMANDA:

            traci.simulationStep()
            t = traci.simulation.getTime()

            # Verificar colisiones del paso anterior
            fue_confirmado = procesar_colisiones(t, pendiente)

            if fue_confirmado:
                pendiente = None
                indice += 1
                siguiente_intento = t + INTERVALO_REINTENTO

            # Gestionar moto de intento pendiente
            if pendiente is not None:

                if not pendiente["activada"]:
                    if pendiente["moto"] in traci.vehicle.getIDList():
                        if not activar_intento(pendiente):
                            # No se pudo poner detras del bus
                            limpiar_intento(pendiente)
                            pendiente = None
                            siguiente_intento = t + INTERVALO_REINTENTO

                elif t - pendiente["t_inicio"] > DURACION_INTENTO:

                    print(
                        f"  [REINTENTO] "
                        f"{pendiente['objetivo']} "
                        "sin colision confirmada.",
                        flush=True
                    )

                    limpiar_intento(pendiente)
                    pendiente = None
                    siguiente_intento = t + INTERVALO_REINTENTO

            if pendiente is not None:
                continue

            if indice >= len(PROGRAMACION):
                continue

            momento = PROGRAMACION[indice]

            # Evitar que una colision pendiente
            # pase a la hora siguiente y se cuente
            # como accidente de otra hora.
            limite_hora = (
                (momento // 3600) + 1
            ) * 3600

            if t >= limite_hora:
                aviso(
                    f"No se confirmo A{indice + 1:02d} "
                    "durante su hora programada."
                )

                indice += 1
                siguiente_intento = t + 1
                continue

            if t < momento or t < siguiente_intento:
                continue

            pendiente = iniciar_intento(indice + 1, t)

            if pendiente is None:
                siguiente_intento = t + INTERVALO_REINTENTO

        # Si el ultimo intento esta pendiente,
        # eliminar la moto sin confirmar.
        if pendiente is not None:
            limpiar_intento(pendiente)

        tarea_33()

        print("\nCerrando simulacion TraCI...")

    finally:
        traci.close()


if __name__ == "__main__":
    ejecutar()
