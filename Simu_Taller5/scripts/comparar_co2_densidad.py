#!/usr/bin/env python3
"""Compara CO2 y densidad de una MISMA salida de emisiones SUMO.
Dependencias: pip install numpy pandas matplotlib
Uso: python comparar_co2_densidad.py --csv co2.csv --net zona_final.net.xml
Intervalo: --inicio 600 --fin 1200 (segundos, fin excluido).
Sin red: representa celdas espaciales; NO inventa geometría de calles.
CO2 de SUMO 1.12: mg/s; --paso es el intervalo de muestreo del CSV.
Densidad = tiempo vehicular / duración / longitud (veh/km), o por área
(veh/km²) en modo celdas. No mezcla edgedata de otra ejecución.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize


def leer_red(path):
    edges, lanes = {}, {}
    for _, e in ET.iterparse(path, events=('end',)):
        if e.tag != 'edge':
            continue
        if e.get('function') == 'internal' or e.get('id', '').startswith(':'):
            e.clear()
            continue
        ll = e.findall('lane')
        if ll:
            shape = ll[0].get('shape', '')
            if shape:
                xy = np.array([[float(v) for v in p.split(',')[:2]] for p in shape.split()])
                length = float(ll[0].get('length', 0))
                if length > 0:
                    edges[e.get('id')] = (xy, length)
                    for lane in ll:
                        lanes[lane.get('id')] = e.get('id')
        e.clear()
    return edges, lanes


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--csv', default='co2.csv')
    p.add_argument('--net', default=None, help='Red SUMO; busca zona_final.net.xml junto al CSV por defecto')
    p.add_argument('--inicio', type=float, default=None)
    p.add_argument('--fin', type=float, default=None)
    p.add_argument('--paso', type=float, default=1, help='Intervalo de muestreo en segundos; no el paso gráfico')
    p.add_argument('--celda', type=float, default=100, help='Lado de celda en metros, sin red')
    p.add_argument('--salida', default='comparacion_co2_densidad')
    p.add_argument('--sin-ventana', action='store_true')
    a = p.parse_args()
    if a.paso <= 0 or a.celda <= 0:
        p.error('--paso y --celda deben ser positivos')
    data = pd.read_csv(a.csv, sep=None, engine='python')
    required = ['timestep_time', 'vehicle_CO2', 'vehicle_lane', 'vehicle_x', 'vehicle_y']
    missing = set(required) - set(data.columns)
    if missing:
        p.error('Faltan columnas: ' + ', '.join(sorted(missing)))
    for col in ['timestep_time', 'vehicle_CO2', 'vehicle_x', 'vehicle_y']:
        data[col] = pd.to_numeric(data[col], errors='coerce')
    if data[required].isna().any().any():
        p.error('Hay filas con datos vacíos o no numéricos en las columnas necesarias')
    if data.empty:
        p.error('CSV vacío')
    if (data.vehicle_CO2 < 0).any():
        p.error('Hay emisiones negativas; revise el CSV')
    start = float(data.timestep_time.min()) if a.inicio is None else a.inicio
    end = float(data.timestep_time.max() + a.paso) if a.fin is None else a.fin
    if start < data.timestep_time.min() or end > data.timestep_time.max() + a.paso:
        p.error('El intervalo solicitado excede la cobertura del CSV')
    if end <= start:
        p.error('--fin debe ser mayor que --inicio')
    # Cada registro representa [t, t+paso); pondera los extremos parcialmente incluidos.
    data['dt'] = np.maximum(0, np.minimum(data.timestep_time + a.paso, end) - np.maximum(data.timestep_time, start))
    d = data.loc[data.dt > 0].copy()
    if d.empty:
        p.error('No hay datos en este intervalo')
    d['co2_g'] = d.vehicle_CO2 * d.dt / 1000
    duration = end - start
    net = Path(a.net) if a.net else Path(a.csv).resolve().parent / 'zona_final.net.xml'
    if a.net and not net.exists():
        p.error('No existe la red indicada: ' + str(net))
    edges, lanes = leer_red(net) if net.exists() else ({}, {})
    use_net = bool(edges)
    if use_net:
        d['zona'] = d.vehicle_lane.map(lanes)
        unmatched = d.zona.isna()
        print(f'Registros fuera de calles externas de la red: {unmatched.sum()} / {len(d)} (incluye enlaces internos).')
        d = d.loc[~unmatched].copy()
        if d.empty:
            p.error('Ninguna calle del CSV coincide con la red; compruebe que sean de la misma simulación')
        density_unit = 'veh/km'
        method = 'Calles SUMO · enlaces internos excluidos'
    else:
        d['ix'] = np.floor(d.vehicle_x / a.celda).astype(int)
        d['iy'] = np.floor(d.vehicle_y / a.celda).astype(int)
        d['zona'] = d.ix.astype(str) + ':' + d.iy.astype(str)
        density_unit = 'veh/km²'
        method = f'Zonas de {a.celda:g} × {a.celda:g} m · sin geometría de red'
        print('Sin red: mapa por coordenadas y celdas, no por calles.')
    stats = d.groupby('zona').agg(tiempo_vehicular_s=('dt', 'sum'), co2_g=('co2_g', 'sum'))
    stats['vehiculos_medios'] = stats.tiempo_vehicular_s / duration
    stats['co2_g_s'] = stats.co2_g / duration
    if use_net:
        stats['longitud_m'] = [edges[k][1] for k in stats.index]
        stats['densidad'] = stats.vehiculos_medios / (stats.longitud_m / 1000)
    else:
        stats['densidad'] = stats.vehiculos_medios / (a.celda / 1000)**2
        stats['x_m'] = [(int(k.split(':')[0]) + .5) * a.celda for k in stats.index]
        stats['y_m'] = [(int(k.split(':')[1]) + .5) * a.celda for k in stats.index]
    # Normalización por longitud/área permite comparar zonas de diferente tamaño.
    if use_net:
        stats['intensidad_co2'] = stats.co2_g_s / (stats.longitud_m / 1000)
        co2unit = 'g/s/km'
    else:
        stats['intensidad_co2'] = stats.co2_g_s / (a.celda / 1000)**2
        co2unit = 'g/s/km²'
    out = Path(a.salida)
    out.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(str(out) + '.csv', index_label='zona')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)
    for ax, field, cmap, title, unit in [
        (axes[0, 0], 'densidad', 'YlOrRd', 'Densidad vehicular media', density_unit),
        (axes[0, 1], 'intensidad_co2', 'magma', 'Intensidad media de CO₂', co2unit)]:
        if use_net:
            ax.add_collection(LineCollection([v[0] for v in edges.values()], colors='#d7dce2', linewidths=1))
            art = LineCollection([edges[k][0] for k in stats.index], cmap=cmap,
                                 norm=Normalize(0, max(stats[field].max(), 1e-12)), linewidths=3)
            art.set_array(stats[field].to_numpy())
            ax.add_collection(art)
            ax.autoscale()
        else:
            # Coordenadas compartidas: ambas capas muestran exactamente las mismas zonas.
            xs = np.arange(np.floor(data.vehicle_x.min()/a.celda), np.floor(data.vehicle_x.max()/a.celda)+2)*a.celda
            ys = np.arange(np.floor(data.vehicle_y.min()/a.celda), np.floor(data.vehicle_y.max()/a.celda)+2)*a.celda
            grid = np.full((len(ys)-1, len(xs)-1), np.nan)
            for k, row in stats.iterrows():
                ix, iy = map(int, k.split(':'))
                grid[iy-int(round(ys[0]/a.celda)), ix-int(round(xs[0]/a.celda))] = row[field]
            art = ax.pcolormesh(xs, ys, np.ma.masked_invalid(grid), cmap=cmap, vmin=0, shading='flat')
            ax.set_facecolor('#eef1f5')
        ax.set_aspect('equal')
        ax.set_title(title, fontweight='bold')
        ax.set_xlabel('X SUMO (m)'); ax.set_ylabel('Y SUMO (m)')
        fig.colorbar(art, ax=ax, label=unit, shrink=.8)
    ax = axes[1, 0]
    ax.scatter(stats.densidad, stats.intensidad_co2, c=stats.co2_g, cmap='viridis', s=35, alpha=.75)
    r = stats.densidad.corr(stats.intensidad_co2) if len(stats)>2 and stats.densidad.std()>0 and stats.intensidad_co2.std()>0 else np.nan
    ax.set_title(f'Densidad frente a CO₂ · Pearson r = {r:.3f}' if np.isfinite(r) else 'Densidad frente a CO₂ · correlación no definida')
    ax.set_xlabel(f'Densidad ({density_unit})'); ax.set_ylabel(f'Intensidad de CO₂ ({co2unit})')
    ax.grid(alpha=.2)
    for k in stats.nlargest(4, 'intensidad_co2').index:
        ax.annotate(str(k), (stats.loc[k,'densidad'], stats.loc[k,'intensidad_co2']), fontsize=7, xytext=(4,4), textcoords='offset points')
    ax = axes[1, 1]
    top = stats.nlargest(10, 'co2_g').sort_values('co2_g')
    ax.barh(top.index, top.co2_g/1000, color='#ba3c52')
    ax.set_xlabel('CO₂ emitido en el intervalo (kg)')
    ax.set_title('Zonas con mayor emisión total')
    ax.tick_params(axis='y', labelsize=8)
    ax.grid(axis='x', alpha=.2)
    fig.suptitle(f'CO₂ y densidad vehicular | {start:g}–{end:g} s\n{method}', fontsize=18, fontweight='bold')
    fig.savefig(str(out)+'.png', dpi=180)
    print(f'Intervalo: {start:g}–{end:g} s; CO₂ de zonas analizadas: {stats.co2_g.sum()/1000:.3f} kg')
    print(f'Guardados: {out}.png y {out}.csv')
    print('La correlación describe asociación, no causalidad. Gris: sin muestras; no implica densidad cero.')
    if not a.sin_ventana:
        plt.show()
    plt.close(fig)


if __name__ == '__main__':
    main()
