#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Imprime cronológicamente los eventos reales de F4 como en la guía docente.

Uso (desde /home/vanet/results/reto):
  python3 resultados/python/F4-T4.4-MOSTRAR_eventos.py
  python3 resultados/python/F4-T4.4-MOSTRAR_eventos.py --hasta 1050
  python3 resultados/python/F4-T4.4-MOSTRAR_eventos.py --accidente A05
  python3 resultados/python/F4-T4.4-MOSTRAR_eventos.py --guardar
"""
from pathlib import Path
import argparse
import csv

RETO = Path(__file__).resolve().parents[2]
CSV = RETO / 'resultados/salida/F4-T4.4-EVENTOS.csv'
ACC = RETO / 'resultados/salida/F4-T4.4-ACCIDENTES_atencion.csv'
ARCHIVO = RETO / 'resultados/salida/F4-T4.4-CRONOLOGIA_legible.log'


def detalles(cadena):
    d = {}
    for tramo in (cadena or '').split(';'):
        if '=' in tramo:
            k, v = tramo.strip().split('=', 1)
            d[k.strip()] = v.strip()
    return d


def formato(evento, d):
    aid = d.get('accidente', d.get('objetivo', '?'))
    unidad = d.get('unidad', '?')
    hospital = d.get('hospital', '?')
    if evento == 'CHOQUE_INTENTADO':
        return f"IMPRUDENTE {d.get('moto','?')} persigue a {d.get('bus','?')} | objetivo {aid}"
    if evento == 'ACCIDENTE_CONFIRMADO':
        return f"ACCIDENTE {aid} colisión {d.get('bus','?')} x {d.get('moto','?')} en {d.get('edge','?')}"
    if evento == 'ACCIDENTE_NO_CONFIRMADO':
        return f"INTENTO FALLIDO {aid}: colisión no confirmada"
    if evento == 'COLISION_SIN_POSICION':
        return f"INTENTO {aid} sin posición válida"
    if evento == 'AMBULANCIA_DESPACHADA':
        return f"DESPACHO {aid} <- {hospital} {unidad} | ETA {d.get('eta','?')} s"
    if evento == 'AMBULANCIA_EN_ESCENA':
        return f"LLEGADA {aid} {unidad} | respuesta {d.get('respuesta_s','?')} s | {d.get('modo','?')}"
    if evento == 'FIN_ATENCION_RETORNO':
        return f"RETORNO {aid} {unidad} -> {hospital} | atención concluida (120 s)"
    if evento == 'UNIDAD_DISPONIBLE':
        return f"DISPONIBLE {unidad} en {hospital} | {aid} | modo {d.get('modo','?')}"
    if evento == 'HOSPITAL_RECHAZA':
        return f"RECHAZO {aid} por {hospital} | solicitud no aceptada"
    if evento == 'SIN_AMBULANCIA_REINTENTO_30S':
        return f"ESPERA {aid}: sin ambulancia | próximo intento en 30 s"
    if evento == 'RETORNO_DIAGNOSTICO':
        return f"DIAGNÓSTICO {aid} {unidad} | arista {d.get('arista','?')} | {d.get('distancia_m','?')} m | {d.get('velocidad_ms','?')} m/s"
    if evento in ('RETORNO_BLOQUEADO', 'RETORNO_REACTIVADO', 'RETORNO_REACTIVACION_FALLIDA',
                  'RETORNO_REROUTE_ERROR', 'RETORNO_ERROR', 'RETORNO_SIN_RUTA',
                  'RETORNO_INTERRUMPIDO', 'RETORNO_NO_CONFIRMADO', 'DESPACHO_ERROR',
                  'AMBULANCIA_NO_INSERTADA', 'TIEMPO_LIMITE_IDA'):
        extras = ' | '.join(f'{k} {v}' for k, v in d.items() if k not in ('accidente', 'objetivo'))
        return f"{evento.replace('_',' ')} {aid}" + (f" | {extras}" if extras else '')
    # No perder eventos nuevos/desconocidos
    return evento.replace('_', ' ') + (f" | {', '.join(f'{k}={v}' for k,v in d.items())}" if d else '')


def construir(args):
    if not CSV.exists():
        raise SystemExit(f'ERROR: no existe {CSV}. Ejecuta primero F4.')
    with CSV.open(newline='', encoding='utf-8-sig') as f:
        eventos = list(csv.DictReader(f))
    accidentes = []
    if ACC.exists():
        with ACC.open(newline='', encoding='utf-8-sig') as f:
            accidentes = list(csv.DictReader(f))

    lineas = [
        '=' * 100,
        'FASE 4 | CRONOLOGÍA DE ACCIDENTES, DESPACHOS, ATENCIÓN Y RETORNOS'.center(100),
        '=' * 100,
    ]
    vistos = 0
    for fila in sorted(eventos, key=lambda x: float(x.get('tiempo_s') or 0)):
        t = float(fila.get('tiempo_s') or 0)
        if args.hasta is not None and t > args.hasta:
            continue
        e = fila.get('evento', '')
        d = detalles(fila.get('detalle', ''))
        if args.accidente and args.accidente not in (d.get('accidente'), d.get('objetivo')):
            continue
        if not args.diagnosticos and e in ('RETORNO_DIAGNOSTICO',):
            continue
        lineas.append(f'[ {t:6.0f} s] {formato(e, d)}')
        vistos += 1
    lineas.append('-' * 100)
    if args.accidente:
        subset = [a for a in accidentes if a.get('id') == args.accidente]
    elif args.hasta is None:
        subset = accidentes
    else:
        subset = []
    if subset:
        terminados = sum(a.get('state') == 'TERMINADO' for a in subset)
        lineas.append(f'RESUMEN CSV | accidentes: {len(subset)} | terminados: {terminados} | pendientes: {len(subset)-terminados}')
        for a in subset:
            if a.get('state') != 'TERMINADO':
                lineas.append(f"[PENDIENTE] {a.get('id','?')} estado={a.get('state','?')}")
    lineas.append(f'Eventos mostrados: {vistos}')
    return '\n'.join(lineas) + '\n'


def main():
    p = argparse.ArgumentParser(description='Cronología legible de la Fase 4 a partir del CSV real')
    p.add_argument('--hasta', type=float, help='mostrar solo eventos hasta el segundo indicado')
    p.add_argument('--accidente', help='filtrar por accidente, ejemplo A05')
    p.add_argument('--diagnosticos', action='store_true', help='incluir los diagnósticos periódicos de retorno')
    p.add_argument('--guardar', action='store_true', help='guardar reporte en resultados/salida')
    args = p.parse_args()
    texto = construir(args)
    print(texto, end='')
    if args.guardar:
        ARCHIVO.write_text(texto, encoding='utf-8')
        print(f'Reporte guardado: {ARCHIVO}')


if __name__ == '__main__':
    main()
