#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F4: Accidentes bus-moto, despacho, atención de 120 s y retorno.

Ejecutar desde /home/vanet/results/reto:
    python3 -u resultados/python/F4-T4.1_4.4-DESPACHO_ambulancias.py

Para SUMO 1.12 se usa /usr/share/sumo/tools antes de importar traci.
Los retornos solo se confirman por llegada real (fin de ruta o proximidad).
"""
from pathlib import Path
from collections import deque, Counter
import csv
import math
import os
import random
import sys

sys.path.insert(0, "/usr/share/sumo/tools")
import traci

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "resultados" / "salida"
OUT.mkdir(parents=True, exist_ok=True)
CFG = ROOT / "F4-reto.sumocfg"
SEED = 42
rng = random.Random(SEED)
END = 12600
DEMAND_END = 10800
SERVICE = 120
RETRY_DISPATCH = 30
REFUSAL = 0.25
ACCIDENT_TARGET = 15
HOURLY = 5
INITIAL_TIMES = [h * 3600 + t for h in range(3) for t in (300, 900, 1500, 2100, 2700)]
ATTEMPT_WAIT = 12
MAX_ATTEMPTS_PER_EVENT = 30
RETURN_REROUTE = 180
RETURN_STUCK = 600
RETURN_DIAGNOSTIC = 300
RETURN_MAX = 2400  # No afirmar un retorno inexistente
WIDTH = 96

HOSP = {
    "VCM": ("publico", -78.992923, -2.911098),
    "IESS_JCA": ("publico", -78.970118, -2.898698),
    "MILITAR": ("publico", -79.003968, -2.903146),
    "MUNI_PAT": ("publico", -78.982263, -2.866103),
    "MUNI_VALLE": ("publico", -78.961959, -2.919522),
    "MONTE_SINAI": ("privado", -79.007373, -2.908606),
    "DEL_RIO": ("privado", -78.960796, -2.892939),
}

hosp = {}
accidents = []
missions = {}
events = []
stocks = []
forced_pairs = {}  # (bus, moto) -> intento
forced_seen = set()
extra_seen = set()
buses_used = set()
active_attempt = None
attempt_seq = 0
attempt_counts = Counter()


def section(text):
    print("\n" + "=" * WIDTH, flush=True)
    print(text.center(WIDTH), flush=True)
    print("=" * WIDTH, flush=True)


def log(t, name, **fields):
    detail = "; ".join(f"{k}={v}" for k, v in fields.items())
    events.append({"tiempo_s": round(float(t), 1), "evento": name, "detalle": detail})
    print(f"[t={t:7.0f}] {name} | {detail}", flush=True)


def save(name, rows, columns):
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)
    print("  CSV:", path, flush=True)


def stock_snapshot(t, reason):
    for hid, h in hosp.items():
        stocks.append({"tiempo_s": round(t, 1), "evento": reason,
                       "hospital": hid, "disponibles": len(h["units"]),
                       "rechazos": h["rejects"]})


def init_hospitals():
    section("F4-T4.1 | SIETE HOSPITALES Y STOCK INICIAL")
    n = 1
    for hid, (typ, lon, lat) in HOSP.items():
        edge, pos, lane = traci.simulation.convertRoad(lon, lat, isGeo=True, vClass="emergency")
        x, y = traci.simulation.convertGeo(lon, lat, fromGeo=True)
        ex, ey = traci.simulation.convert2D(edge, pos, lane)
        dist = math.hypot(x-ex, y-ey)
        count = rng.randint(1, 3) if typ == "publico" else rng.randint(0, 1)
        units = deque()
        for _ in range(count):
            units.append(f"U{n:02d}")
            n += 1
        hosp[hid] = dict(type=typ, edge=edge, pos=pos, lane=lane, xy=(x, y),
                         distance=dist, units=units, initial=count, rejects=0)
        # TraCI de SUMO 1.12 acepta este formato básico del POI.
        traci.poi.add("HOSP_"+hid, x, y, (255, 0, 0), "hospital", 100)
        print(f"  {hid:12} | unidades={count} | via={edge:18} | distancia={dist:6.1f} m", flush=True)
    if any(h["distance"] >= 150 for h in hosp.values()):
        print("  [AVISO] Hay hospitales a 150 m o más de la vía.", flush=True)
    print("  TOTAL:", sum(h["initial"] for h in hosp.values()), "ambulancias", flush=True)
    stock_snapshot(0, "INICIAL")


def route(from_edge, to_edge):
    if not from_edge or from_edge.startswith(":"):
        return None
    try:
        r = traci.simulation.findRoute(from_edge, to_edge, vType="ambulance")
        return r if len(r.edges) > 0 and math.isfinite(r.travelTime) else None
    except (traci.exceptions.TraCIException, ValueError):
        return None


def choose_bus():
    candidates = []
    for vid in traci.vehicle.getIDList():
        if vid in buses_used or traci.vehicle.getTypeID(vid) != "bus":
            continue
        try:
            road = traci.vehicle.getRoadID(vid)
            lane = traci.vehicle.getLaneID(vid)
            pos = traci.vehicle.getLanePosition(vid)
            speed = traci.vehicle.getSpeed(vid)
            if road.startswith(":") or speed <= 4 or pos <= 60:
                continue
            if traci.lane.getLength(lane)-pos <= 28:
                continue
            moto_pos = pos - 35
            if moto_pos <= 5:
                continue
            occupied = any(abs(traci.vehicle.getLanePosition(o)-moto_pos) < 14
                           for o in traci.lane.getLastStepVehicleIDs(lane) if o != vid)
            if occupied:
                continue
            candidates.append((vid, road, lane, pos, moto_pos,
                               traci.vehicle.getLaneIndex(vid)))
        except traci.exceptions.TraCIException:
            continue
    return rng.choice(candidates) if candidates else None


def insert_attempt(event_number, t):
    global attempt_seq
    chosen = choose_bus()
    if chosen is None:
        return None
    bus, road, lane, buspos, motopos, lane_index = chosen
    attempt_seq += 1
    aid = f"A{event_number:02d}"
    moto = f"F4_MOTO_{attempt_seq:03d}"
    rid = f"F4_RUTA_MOTO_{attempt_seq:03d}"
    try:
        busroute = list(traci.vehicle.getRoute(bus))
        index = traci.vehicle.getRouteIndex(bus)
        if index < 0 or not busroute[index:]:
            return None
        # Evitar destinos inalcanzables para motocicletas.
        last = busroute[-1]
        mr = traci.simulation.findRoute(road, last, vType="moto")
        if not mr.edges or mr.edges[0] != road:
            return None
        traci.route.add(rid, list(mr.edges))
        traci.vehicle.add(moto, rid, typeID="moto", depart="now",
                          departLane=str(lane_index), departPos=str(motopos), departSpeed="0")
    except traci.exceptions.TraCIException:
        return None
    attempt_counts[aid] += 1
    attempt = dict(aid=aid, bus=bus, moto=moto, lane=lane, road=road,
                   buspos=buspos, start=t, activated=False)
    log(t, "CHOQUE_INTENTADO", objetivo=aid, bus=bus, moto=moto)
    return attempt


def activate_attempt(attempt):
    bus, moto = attempt["bus"], attempt["moto"]
    ids = set(traci.vehicle.getIDList())
    if bus not in ids or moto not in ids:
        return False
    try:
        if traci.vehicle.getRoadID(bus) != traci.vehicle.getRoadID(moto):
            return False
        lane = traci.vehicle.getLaneID(bus)
        if lane.startswith(":"):
            return False
        buspos = traci.vehicle.getLanePosition(bus)
        motopos = buspos-30
        if motopos < 5:
            return False
        traci.vehicle.moveTo(moto, lane, motopos)
        traci.vehicle.setLaneChangeMode(moto, 0)
        traci.vehicle.setSpeedMode(moto, 0)
        traci.vehicle.setMaxSpeed(moto, 35)
        traci.vehicle.setSpeed(moto, 30)
        attempt["activated"] = True
        return True
    except traci.exceptions.TraCIException:
        return False


def remove_attempt(attempt):
    if attempt and attempt["moto"] in traci.vehicle.getIDList():
        try:
            traci.vehicle.remove(attempt["moto"])
        except traci.exceptions.TraCIException:
            pass


def freeze_collision(bus, moto):
    for vid in (bus, moto):
        if vid in traci.vehicle.getIDList():
            try:
                traci.vehicle.setSpeedMode(vid, 0)
                traci.vehicle.setLaneChangeMode(vid, 0)
                traci.vehicle.setSpeed(vid, 0)
            except traci.exceptions.TraCIException:
                pass


def detect_collisions(t, attempt):
    result = None
    for c in traci.simulation.getCollisions():
        pair = frozenset((c.collider, c.victim))
        if attempt and pair == frozenset((attempt["bus"], attempt["moto"])):
            if pair in forced_seen:
                continue
            forced_seen.add(pair)
            bus, moto = attempt["bus"], attempt["moto"]
            buses_used.add(bus)
            freeze_collision(bus, moto)
            try:
                x, y = traci.vehicle.getPosition(bus)
                lane = traci.vehicle.getLaneID(bus)
                edge = traci.vehicle.getRoadID(bus)
                pos = traci.vehicle.getLanePosition(bus)
            except traci.exceptions.TraCIException:
                # La colisión se confirma, pero no se dispone de coordenadas útiles.
                log(t, "COLISION_SIN_POSICION", objetivo=attempt["aid"])
                continue
            aid = attempt["aid"]
            accident = dict(id=aid, hour=int(t // 3600)+1, t_accident=t,
                            bus=bus, moto=moto, edge=edge, pos=pos, lane=lane,
                            x=x, y=y, hospital_origen="", hospital_retorno="",
                            unit="", t_dispatch="", t_arrival="", t_end_service="",
                            t_return="", arrival_mode="", eta="", state="PENDIENTE",
                            last_retry=t-RETRY_DISPATCH)
            accidents.append(accident)
            result = accident
            log(t, "ACCIDENTE_CONFIRMADO", accidente=aid, bus=bus, moto=moto, edge=edge)
        else:
            # La misma pareja de vehículos solo se cuenta una vez; los contactos
            # posteriores a un accidente forzado no se llaman colisiones naturales.
            if pair not in extra_seen and pair not in forced_seen:
                extra_seen.add(pair)
    return result


def best_dispatch(a, t):
    options = []
    for hid, h in hosp.items():
        if not h["units"]:
            continue
        r = route(h["edge"], a["edge"])
        if r is not None:
            options.append((r.travelTime, hid, r))
    for _, hid, r in sorted(options):
        if rng.random() < REFUSAL:
            hosp[hid]["rejects"] += 1
            log(t, "HOSPITAL_RECHAZA", accidente=a["id"], hospital=hid)
            continue
        return hid, r
    return None, None


def dispatch(a, t):
    a["last_retry"] = t
    hid, r = best_dispatch(a, t)
    if not hid:
        log(t, "SIN_AMBULANCIA_REINTENTO_30S", accidente=a["id"])
        return
    h = hosp[hid]
    unit = h["units"].popleft()
    vid = "F4_AMB_" + unit
    rid = "F4_RUTA_IDA_" + a["id"]
    try:
        traci.route.add(rid, list(r.edges))
        traci.vehicle.add(vid, rid, typeID="ambulance", depart="now",
                          departPos=str(max(0, h["pos"]-1)), departSpeed="0")
    except traci.exceptions.TraCIException as exc:
        h["units"].appendleft(unit)
        log(t, "DESPACHO_ERROR", accidente=a["id"], razon=str(exc)[:100])
        return
    a.update(state="EN_RUTA", hospital_origen=hid, unit=unit,
             t_dispatch=t, eta=round(r.travelTime, 2))
    missions[vid] = dict(vehicle=vid, unit=unit, accident=a, state="EN_RUTA",
                         time=t, last_reroute=t, return_hospital=None,
                         near_since=None)
    stock_snapshot(t, "despacho_"+a["id"])
    log(t, "AMBULANCIA_DESPACHADA", accidente=a["id"], unidad=unit,
        hospital=hid, eta=round(r.travelTime, 1))


def distance_to_accident(vid, a):
    try:
        x, y = traci.vehicle.getPosition(vid)
        return math.hypot(x-a["x"], y-a["y"])
    except traci.exceptions.TraCIException:
        return float("inf")


def arrive_scene(m, t, mode):
    a, vid = m["accident"], m["vehicle"]
    a.update(t_arrival=t, arrival_mode=mode, state="ATENDIENDO")
    m.update(state="ATENDIENDO", service_end=t+SERVICE)
    if vid in traci.vehicle.getIDList():
        traci.vehicle.setSpeedMode(vid, 0)
        traci.vehicle.setSpeed(vid, 0)
    log(t, "AMBULANCIA_EN_ESCENA", accidente=a["id"], unidad=m["unit"],
        modo=mode, respuesta_s=t-a["t_dispatch"])


def choose_return(m, from_edge=None):
    a, vid = m["accident"], m["vehicle"]
    edge = from_edge or (traci.vehicle.getRoadID(vid) if vid in traci.vehicle.getIDList() else a["edge"])
    options = []
    for hid, h in hosp.items():
        r = route(edge, h["edge"])
        if r is not None:
            options.append((r.travelTime, hid, r))
    return min(options) if options else None


def reactivate(vid, dest_edge, t=0, accident_id=""):
    """Restaurar control normal sin teletransportar ni forzar velocidad insegura."""
    if vid not in traci.vehicle.getIDList():
        return False
    try:
        try:
            stops = traci.vehicle.getStops(vid)
            if stops:
                try:
                    traci.vehicle.resume(vid)
                except traci.exceptions.TraCIException as exc:
                    log(t, "RETORNO_STOP_NO_LIBERADO", accidente=accident_id, razon=str(exc)[:90])
        except (AttributeError, traci.exceptions.TraCIException):
            pass
        traci.vehicle.setSpeedMode(vid, 31)
        traci.vehicle.setLaneChangeMode(vid, 1621)
        traci.vehicle.setSpeed(vid, -1)
        traci.vehicle.changeTarget(vid, dest_edge)
        return True
    except traci.exceptions.TraCIException as exc:
        log(t, "RETORNO_REACTIVACION_ERROR", accidente=accident_id, razon=str(exc)[:120])
        return False


def finish_service(m, t):
    a, vid = m["accident"], m["vehicle"]
    for vehicle in (a["bus"], a["moto"]):
        if vehicle in traci.vehicle.getIDList():
            try:
                traci.vehicle.remove(vehicle)
            except traci.exceptions.TraCIException:
                pass
    a["t_end_service"] = t
    option = choose_return(m)
    if option is None:
        a["state"] = "RETORNO_FALLIDO"
        m["state"] = "FALLIDO"
        log(t, "RETORNO_SIN_RUTA", accidente=a["id"], unidad=m["unit"])
        return
    _, hid, r = option
    try:
        if vid not in traci.vehicle.getIDList():
            rid = "F4_RUTA_RETORNO_"+a["id"]
            traci.route.add(rid, list(r.edges))
            traci.vehicle.add(vid, rid, typeID="ambulance", depart="now",
                              departPos=str(max(0, a["pos"]-1)), departSpeed="0")
            m["reinserted"] = True
        else:
            if not reactivate(vid, hosp[hid]["edge"], t, a["id"]):
                raise RuntimeError("No se pudo restablecer el movimiento")
    except (traci.exceptions.TraCIException, RuntimeError) as exc:
        a["state"] = "RETORNO_FALLIDO"
        m["state"] = "FALLIDO"
        log(t, "RETORNO_ERROR", accidente=a["id"], razon=str(exc)[:120])
        return
    a.update(hospital_retorno=hid, state="REGRESANDO")
    m.update(state="REGRESANDO", return_hospital=hid, last_reroute=t,
             return_started=t, return_dist_before=None, return_last_progress=t,
             return_last_log=t-RETURN_DIAGNOSTIC, return_recovery=False,
             return_blocked_reported=False)
    log(t, "FIN_ATENCION_RETORNO", accidente=a["id"], unidad=m["unit"], hospital=hid)


def finish_return(m, t, mode):
    a, vid, hid = m["accident"], m["vehicle"], m["return_hospital"]
    if vid in traci.vehicle.getIDList():
        try:
            traci.vehicle.remove(vid)
        except traci.exceptions.TraCIException:
            pass
    hosp[hid]["units"].append(m["unit"])
    a.update(t_return=t, state="TERMINADO")
    m["state"] = "TERMINADO"
    stock_snapshot(t, "retorno_"+a["id"])
    log(t, "UNIDAD_DISPONIBLE", accidente=a["id"], unidad=m["unit"],
        hospital=hid, modo=mode)


def recovery_return(m, t, edge, distance):
    """Un reintento no teletransporta ni garantiza movilidad."""
    a, vid, hid = m["accident"], m["vehicle"], m["return_hospital"]
    if not m["return_blocked_reported"]:
        log(t, "RETORNO_BLOQUEADO", accidente=a["id"], unidad=m["unit"],
            arista=edge, distancia_m=round(distance, 1))
        m["return_blocked_reported"] = True
    if m["return_recovery"]:
        return
    # Sólo un intento especial: liberar parada programada (si existe),
    # restablecer velocidad normal y calcular nueva ruta.
    success = reactivate(vid, hosp[hid]["edge"], t, a["id"])
    m["return_recovery"] = True
    log(t, "RETORNO_REACTIVADO" if success else "RETORNO_REACTIVACION_FALLIDA",
        accidente=a["id"], unidad=m["unit"], hospital=hid)


def update_missions(t):
    active = set(traci.vehicle.getIDList())
    arrived = set(traci.simulation.getArrivedIDList())
    for m in list(missions.values()):
        state, vid, a = m["state"], m["vehicle"], m["accident"]
        if state in ("TERMINADO", "FALLIDO"):
            continue
        if state == "EN_RUTA":
            if vid in arrived:
                arrive_scene(m, t, "FIN_RUTA")
                continue
            if vid not in active:
                if t-m["time"] > 120:
                    m["state"] = "FALLIDO"
                    a["state"] = "AMBULANCIA_PERDIDA"
                    log(t, "AMBULANCIA_NO_INSERTADA", accidente=a["id"], unidad=m["unit"])
                continue
            d = distance_to_accident(vid, a)
            if d <= 50:
                arrive_scene(m, t, "PROXIMIDAD_50M")
                continue
            if d <= 300 and traci.vehicle.getSpeed(vid) < .4:
                if m["near_since"] is None:
                    m["near_since"] = t
                if t-m["near_since"] >= 30:
                    arrive_scene(m, t, "CAMINATA_300M_30S")
                    continue
            else:
                m["near_since"] = None
            if t-m["last_reroute"] >= 90:
                try:
                    traci.vehicle.changeTarget(vid, a["edge"])
                except traci.exceptions.TraCIException:
                    pass
                m["last_reroute"] = t
            if t-a["t_dispatch"] >= 1800:
                m["state"] = "FALLIDO"
                a["state"] = "SIN_ATENCION"
                log(t, "TIEMPO_LIMITE_IDA", accidente=a["id"], unidad=m["unit"])
        elif state == "ATENDIENDO":
            if t >= m["service_end"]:
                finish_service(m, t)
        elif state == "REGRESANDO":
            hid = m["return_hospital"]
            h = hosp[hid]
            if vid in arrived:
                finish_return(m, t, "FIN_RUTA")
                continue
            if vid not in active:
                m["state"] = "FALLIDO"
                a["state"] = "RETORNO_INTERRUMPIDO"
                log(t, "RETORNO_INTERRUMPIDO", accidente=a["id"], unidad=m["unit"])
                continue
            x, y = traci.vehicle.getPosition(vid)
            d = math.hypot(x-h["xy"][0], y-h["xy"][1])
            if d <= 50:
                finish_return(m, t, "PROXIMIDAD_50M")
                continue
            edge = traci.vehicle.getRoadID(vid)
            speed = traci.vehicle.getSpeed(vid)
            before = m["return_dist_before"]
            if before is None or d < before-5:
                m["return_dist_before"] = d
                m["return_last_progress"] = t
            no_progress = t-m["return_last_progress"]
            if t-m["return_last_log"] >= RETURN_DIAGNOSTIC:
                log(t, "RETORNO_DIAGNOSTICO", accidente=a["id"], unidad=m["unit"],
                    hospital=hid, arista=edge, distancia_m=round(d, 1),
                    velocidad_ms=round(speed, 2), sin_progreso_s=no_progress)
                m["return_last_log"] = t
            if t-m["last_reroute"] >= RETURN_REROUTE:
                try:
                    traci.vehicle.changeTarget(vid, h["edge"])
                except traci.exceptions.TraCIException as exc:
                    log(t, "RETORNO_REROUTE_ERROR", accidente=a["id"], razon=str(exc)[:90])
                m["last_reroute"] = t
            if no_progress >= RETURN_STUCK and speed < .4:
                recovery_return(m, t, edge, d)
            if t-m["return_started"] >= RETURN_MAX:
                m["state"] = "FALLIDO"
                a["state"] = "RETORNO_NO_CONFIRMADO"
                log(t, "RETORNO_NO_CONFIRMADO", accidente=a["id"], unidad=m["unit"],
                    arista=edge, distancia_m=round(d, 1), velocidad_ms=round(speed, 2))


def write_results(t):
    section("F4-T4.4 | RESULTADOS Y VALIDACION")
    fields = ["id", "hour", "t_accident", "bus", "moto", "edge", "pos",
              "hospital_origen", "hospital_retorno", "unit", "t_dispatch",
              "t_arrival", "arrival_mode", "eta", "t_end_service", "t_return", "state"]
    save("F4-T4.4-ACCIDENTES_atencion.csv", accidents, fields)
    save("F4-T4.4-STOCK_hospitales.csv", stocks,
         ["tiempo_s", "evento", "hospital", "disponibles", "rechazos"])
    save("F4-T4.4-EVENTOS.csv", events, ["tiempo_s", "evento", "detalle"])
    counts = Counter(a["state"] for a in accidents)
    hourly = Counter(a["hour"] for a in accidents)
    print("  Accidentes confirmados:", len(accidents), flush=True)
    print("  Accidentes por hora:", {h: hourly[h] for h in (1, 2, 3)}, flush=True)
    print("  Estados:", dict(counts), flush=True)
    print("  Atenciones finalizadas:", sum(a["t_end_service"] != "" for a in accidents), flush=True)
    print("  Retornos completados:", sum(a["t_return"] != "" for a in accidents), flush=True)
    print("  Hospitales con inventario:", {h: len(x["units"]) for h, x in hosp.items()}, flush=True)
    print("  Pares extra de colision detectados:", len(extra_seen), flush=True)
    if len(accidents) == 15 and all(hourly[h] == 5 for h in (1, 2, 3)):
        print("  [OK] Se confirmaron 15 accidentes (5 por hora).", flush=True)
    else:
        print("  [PENDIENTE] No se confirmaron los 15 accidentes requeridos.", flush=True)
    if counts.get("TERMINADO", 0) == 15:
        print("  [OK] Las 15 misiones finalizaron con retorno confirmado.", flush=True)
    else:
        print("  [PENDIENTE] Hay misiones sin retorno confirmado.", flush=True)


def main():
    global active_attempt
    if not CFG.exists():
        raise FileNotFoundError(f"Falta {CFG}")
    os.chdir(ROOT)
    binary = "sumo-gui" if "--gui" in sys.argv else "sumo"
    section("FASE 4 | ACCIDENTES + DESPACHO + ATENCION + RETORNO")
    traci.start([binary, "-c", str(CFG), "--seed", str(SEED),
                 "--end", str(END), "--no-step-log", "true", "--start"])
    try:
        init_hospitals()
        section("F4-T4.2 | ACCIDENTES Y DESPACHO")
        section("F4-T4.3 | ATENCION DE 120 S Y RETORNO")
        target_index = 0
        next_attempt = INITIAL_TIMES[0]
        while traci.simulation.getTime() < END:
            traci.simulationStep()
            t = traci.simulation.getTime()
            # Las colisiones se consultan inmediatamente después de avanzar un paso.
            new_accident = detect_collisions(t, active_attempt)
            if new_accident:
                active_attempt = None
                target_index += 1
                if target_index < len(INITIAL_TIMES):
                    next_attempt = max(t+ATTEMPT_WAIT, INITIAL_TIMES[target_index])
            if active_attempt:
                if not active_attempt["activated"]:
                    if active_attempt["moto"] in traci.vehicle.getIDList():
                        if not activate_attempt(active_attempt):
                            remove_attempt(active_attempt)
                            active_attempt = None
                            next_attempt = t+ATTEMPT_WAIT
                    elif t-active_attempt["start"] > 20:
                        active_attempt = None
                        next_attempt = t+ATTEMPT_WAIT
                elif t-active_attempt["start"] > 12:
                    remove_attempt(active_attempt)
                    active_attempt = None
                    next_attempt = t+ATTEMPT_WAIT
            if target_index < len(INITIAL_TIMES) and active_attempt is None:
                scheduled = INITIAL_TIMES[target_index]
                end_hour = (scheduled//3600+1)*3600
                aid = f"A{target_index+1:02d}"
                if t >= end_hour or attempt_counts[aid] >= MAX_ATTEMPTS_PER_EVENT:
                    log(t, "ACCIDENTE_NO_CONFIRMADO", objetivo=aid)
                    target_index += 1
                    if target_index < len(INITIAL_TIMES):
                        next_attempt = INITIAL_TIMES[target_index]
                elif t >= scheduled and t >= next_attempt:
                    active_attempt = insert_attempt(target_index+1, t)
                    if active_attempt is None:
                        next_attempt = t+ATTEMPT_WAIT
            for a in accidents:
                if a["state"] == "PENDIENTE" and t-a["last_retry"] >= RETRY_DISPATCH:
                    dispatch(a, t)
            update_missions(t)
        if active_attempt:
            remove_attempt(active_attempt)
        write_results(END)
    finally:
        traci.close()


if __name__ == "__main__":
    main()
