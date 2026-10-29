#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F5: estadísticas finales del reto SUMO+TraCI; reutiliza los CSV de F4.
Ejecutar desde cualquier directorio: python3 resultados/python/F5-T5.1_5.4-ESTADISTICAS_finales.py
"""
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median
import csv
import math
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RETO = Path(__file__).resolve().parents[2]
OUT = RETO / 'resultados' / 'salida'
FIG = RETO / 'resultados' / 'graficas'
FIG.mkdir(parents=True, exist_ok=True)
A_PATH = OUT / 'F4-T4.4-ACCIDENTES_atencion.csv'
S_PATH = OUT / 'F4-T4.4-STOCK_hospitales.csv'
E_PATH = OUT / 'F4-T4.4-EVENTOS.csv'
L_PATH = OUT / 'F4-T4.1_4.4-EVENTOS.log'


def rows(path):
    if not path.exists():
        raise FileNotFoundError(f'No existe {path}')
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def dump(name, data, fields):
    p = OUT / name
    with p.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(data)
    print('  CSV:', p.relative_to(RETO))


def sec(t):
    print('\n' + '=' * 82)
    print(t)
    print('=' * 82)


def build():
    a_rows = rows(A_PATH)
    s_rows = rows(S_PATH)
    e_rows = rows(E_PATH)
    log = L_PATH.read_text(encoding='utf-8', errors='replace') if L_PATH.exists() else ''

    sec('F5-T5.1 | ACCIDENTES Y TIEMPOS DE RESPUESTA')
    accidents = []
    for r in a_rows:
        ta, td, tl = [number(r.get(k)) for k in ('t_accident', 't_dispatch', 't_arrival')]
        ts, tr = [number(r.get(k)) for k in ('t_end_service', 't_return')]
        response = tl-td if tl is not None and td is not None else None
        delay = td-ta if td is not None and ta is not None else None
        service = ts-tl if ts is not None and tl is not None else None
        total = tr-ta if tr is not None and ta is not None else None
        accidents.append({
            'id': r.get('id',''), 'hora': int((ta // 3600)+1) if ta is not None else '',
            't_accidente_s': ta, 't_despacho_s': td, 't_llegada_s': tl,
            'espera_despacho_s': delay, 'respuesta_s': response,
            'atencion_s': service, 't_retorno_s': tr, 'ciclo_total_s': total,
            'hospital_origen': r.get('hospital_origen',''),
            'hospital_retorno': r.get('hospital_retorno',''),
            'unidad': r.get('unit',''), 'modo_llegada': r.get('arrival_mode',''),
            'estado': r.get('state','')
        })
    accidents.sort(key=lambda x: (x['t_accidente_s'] is None, x['t_accidente_s'] or 0))
    dump('F5-T5.1-ACCIDENTES_estadisticas.csv', accidents, list(accidents[0]) if accidents else [
        'id','hora','t_accidente_s','t_despacho_s','t_llegada_s','espera_despacho_s',
        'respuesta_s','atencion_s','t_retorno_s','ciclo_total_s','hospital_origen',
        'hospital_retorno','unidad','modo_llegada','estado'])
    responses = [a['respuesta_s'] for a in accidents if a['respuesta_s'] is not None]
    print(f'  Accidentes: {len(accidents)}; misiones terminadas: {sum(a["estado"] == "TERMINADO" for a in accidents)}')
    if responses:
        print(f'  Respuesta media: {mean(responses):.1f} s; mediana: {median(responses):.1f} s; max: {max(responses):.1f} s')
    else:
        print('  No hay tiempos de respuesta completos')

    sec('F5-T5.2 | ACTIVIDAD HOSPITALARIA')
    dispatched = Counter(x['hospital_origen'] for x in accidents if x['hospital_origen'])
    returned = Counter(x['hospital_retorno'] for x in accidents if x['hospital_retorno'] and x['t_retorno_s'] is not None)
    hospitals = sorted(set(dispatched) | set(returned))
    hospital_rows = [{
        'hospital': h, 'despachos': dispatched[h], 'retornos_confirmados': returned[h],
        'diferencia_retornos_menos_despachos': returned[h]-dispatched[h]
    } for h in hospitals]
    dump('F5-T5.2-HOSPITALES_estadisticas.csv', hospital_rows,
         ['hospital','despachos','retornos_confirmados','diferencia_retornos_menos_despachos'])
    distintos = sum(x['hospital_origen'] != x['hospital_retorno'] for x in accidents
                   if x['hospital_origen'] and x['hospital_retorno'] and x['t_retorno_s'] is not None)
    print('  Despachos:', sum(dispatched.values()), 'Retornos:', sum(returned.values()),
          'Retornos a hospital diferente:', distintos)

    sec('F5-T5.3 | EVOLUCION DEL STOCK')
    print('  Columnas originales STOCK_hospitales.csv:', ', '.join(s_rows[0].keys()) if s_rows else '(vacío)')
    # El CSV original se conserva sin reinterpretar nombres de columnas desconocidos.
    # Para comparación homogénea, reconstruimos el total de unidades disponibles mediante
    # eventos de despacho y retorno; la base es el stock inicial calculado desde F2.
    f2 = OUT / 'F2-T2.2-FLOTA_inicial.csv'
    initial = None
    if f2.exists():
        initial = sum(number(r.get('stock_inicial')) or 0 for r in rows(f2))
    elif s_rows:
        # No inferir stock desde columnas que podrían ser snapshots parciales.
        print('  Aviso: falta CSV inicial de F2; no se inferirá stock total.')
    timeline = []
    if initial is not None:
        current = int(initial)
        timeline.append({'tiempo_s': 0.0, 'evento': 'STOCK_INICIAL', 'stock_disponible':current})
        movements = []
        for ev in e_rows:
            t = number(ev.get('tiempo_s'))
            typ = ev.get('evento','')
            if t is None:
                continue
            if typ == 'AMBULANCIA_DESPACHADA':
                movements.append((t, -1, typ))
            elif typ == 'UNIDAD_DISPONIBLE':
                movements.append((t, 1, typ))
        for t, delta, typ in sorted(movements, key=lambda z:z[0]):
            current += delta
            timeline.append({'tiempo_s': t, 'evento': typ, 'stock_disponible': current})
        if current < 0 or any(x['stock_disponible'] < 0 for x in timeline):
            print('  ALERTA: stock disponible negativo; revisar eventos o stock inicial.')
        print('  Stock inicial:', int(initial), 'Stock final:',current)
    else:
        print('  Gráfica temporal de stock omitida: falta stock inicial verificable.')
    dump('F5-T5.3-STOCK_evolucion.csv', timeline, ['tiempo_s','evento','stock_disponible'])

    sec('F5-T5.4 | GRAFICAS Y VALIDACION')
    if accidents:
        plt.figure(figsize=(12, 5))
        plt.bar([x['id'] for x in accidents], [x['respuesta_s'] or 0 for x in accidents])
        plt.xlabel('Accidente'); plt.ylabel('Respuesta (s)')
        plt.title('F5 - Tiempo de respuesta por accidente')
        plt.xticks(rotation=45); plt.tight_layout()
        plt.savefig(FIG / 'F5-T5.4-TIEMPOS_respuesta.png', dpi=180); plt.close()
    if hospitals:
        xs = list(range(len(hospitals)))
        plt.figure(figsize=(12, 5))
        plt.bar([x-.2 for x in xs], [dispatched[h] for h in hospitals], width=.4, label='Despachos')
        plt.bar([x+.2 for x in xs], [returned[h] for h in hospitals], width=.4, label='Retornos')
        plt.xticks(xs, hospitals, rotation=35, ha='right')
        plt.ylabel('Misiones'); plt.title('F5 - Despachos y retornos por hospital')
        plt.legend(); plt.tight_layout()
        plt.savefig(FIG / 'F5-T5.4-HOSPITALES_utilizacion.png', dpi=180); plt.close()
    if timeline:
        plt.figure(figsize=(11, 5))
        plt.step([x['tiempo_s']/60 for x in timeline],
                 [x['stock_disponible'] for x in timeline], where='post')
        plt.xlabel('Tiempo simulado (min)'); plt.ylabel('Ambulancias disponibles')
        plt.title('F5 - Evolución del stock disponible total')
        plt.grid(alpha=.25); plt.tight_layout()
        plt.savefig(FIG / 'F5-T5.4-STOCK_evolucion.png', dpi=180); plt.close()
    by_hour = Counter(x['hora'] for x in accidents)
    plt.figure(figsize=(7, 5))
    plt.bar(['Hora 1','Hora 2','Hora 3'], [by_hour[h] for h in (1,2,3)])
    plt.axhline(5, linestyle='--', label='Objetivo: 5/h')
    plt.title('F5 - Accidentes por hora'); plt.ylabel('Accidentes confirmados')
    plt.legend(); plt.tight_layout()
    plt.savefig(FIG / 'F5-T5.4-ACCIDENTES_por_hora.png', dpi=180); plt.close()

    match = re.findall(r'Teleports:\s*(\d+)', log)
    teleports = int(match[-1]) if match else None
    checks = {
        '15 accidentes': len(accidents)==15 and len(set(x['id'] for x in accidents))==15,
        '5 accidentes por hora': all(by_hour[h]==5 for h in (1,2,3)),
        '15 misiones terminadas': sum(x['estado']=='TERMINADO' for x in accidents)==15,
        '15 retornos con instante': sum(x['t_retorno_s'] is not None for x in accidents)==15,
        '120 s de atención en todas': len(accidents)==15 and all(
            x['atencion_s'] is not None and abs(x['atencion_s']-120)<.001 for x in accidents),
        '0 teleports': teleports == 0,
        'Stock sin valores negativos': bool(timeline) and all(x['stock_disponible']>=0 for x in timeline)
    }
    for name, valid in checks.items():
        print(f'  {"[OK]" if valid else "[REVISAR]"} {name}')
    print('  Teleports leídos del log:',teleports)
    print('  Figuras en:', FIG)
    print('\n  RESULTADO:', 'VALIDACIONES PRINCIPALES OK' if all(checks.values()) else 'REVISAR INDICADORES')

if __name__ == '__main__':
    try:
        build()
    except (FileNotFoundError, KeyError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)
