import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt

# 1. Definir los volúmenes de tráfico a evaluar (vehículos / hora)
volumenes = [500, 1000, 1500, 2000, 2200, 2400, 2600, 2800, 3000, 3200, 3400, 3600, 3800, 4000]

# Archivos base
net_file = "zona_final.net.xml"
sumocfg_file = "cuenca.sumocfg"

# Obtención del directorio de SUMO
sumo_home = os.environ.get("SUMO_HOME", "/usr/share/sumo")
if not os.path.exists(sumo_home):
    raise ValueError(f"No se encontró el directorio SUMO_HOME en {sumo_home}.")

xml2csv_script = os.path.join(sumo_home, "tools", "xml", "xml2csv.py")
random_trips_script = os.path.join(sumo_home, "tools", "randomTrips.py")

resultados = []

print("=== INICIANDO EXPERIMENTO DE SATURACIÓN DE RED (PORCENTAJE) ===")

for veh_h in volumenes:
    p_val = 3600.0 / veh_h
    rou_file = f"cuenca_{veh_h}.rou.xml"
    summary_xml = f"summary_{veh_h}.xml"
    summary_csv = f"summary_{veh_h}.csv"
    
    print(f"\n[+] Procesando volumen: {veh_h} veh/h (p = {p_val:.2f} s)...")
    
    # PASO 1: Generar archivo de rutas con randomTrips.py[cite: 5]
    cmd_trips = [
        "python3", random_trips_script,
        "-b", "0",
        "-e", "3600",
        "-p", str(p_val),
        "-n", net_file,
        "-r", rou_file,
        "--prefix", "veh"
    ]
    subprocess.run(cmd_trips, check=True)
    
    # PASO 2: Ejecutar simulación SUMO con tiempo de teleport a 60 segundos
    cmd_sumo = [
        "sumo",
        "-c", sumocfg_file,
        "--route-files", rou_file,
        "--summary-output", summary_xml,
        "--time-to-teleport", "60",
        "--no-warnings", "true"
    ]
    subprocess.run(cmd_sumo, check=True)
    
    # PASO 3: Convertir XML a CSV
    cmd_xml2csv = [
        "python3", xml2csv_script,
        summary_xml,
        "-o", summary_csv
    ]
    subprocess.run(cmd_xml2csv, check=True)
    
    # PASO 4: Leer CSV y calcular el porcentaje de teleportings
    try:
        df = pd.read_csv(summary_csv, sep=None, engine="python")
        
        # Buscar la columna de teleports
        col_teleports = [c for c in df.columns if "teleports" in c.lower()]
        # Buscar la columna de vehículos insertados o cargados
        col_inserted = [c for c in df.columns if "inserted" in c.lower() or "loaded" in c.lower()]
        
        if col_teleports and col_inserted:
            total_teleports = float(pd.to_numeric(df[col_teleports[0]].iloc[-1], errors="coerce"))
            total_inserted = float(pd.to_numeric(df[col_inserted[0]].iloc[-1], errors="coerce"))
            
            if total_inserted > 0:
                pct_teleports = (total_teleports / total_inserted) * 100.0
            else:
                pct_teleports = 0.0
        else:
            total_teleports = 0.0
            total_inserted = 0.0
            pct_teleports = 0.0
            print("    [!] Advertencia: No se encontraron las columnas necesarias en el CSV.")
            
    except Exception as e:
        print(f"    [!] Error al procesar {summary_csv}: {e}")
        total_teleports = 0.0
        total_inserted = 0.0
        pct_teleports = 0.0
        
    print(f"    -> Total Vehículos: {int(total_inserted)} | Teleportings: {int(total_teleports)} ({pct_teleports:.2f}%)")
    resultados.append({
        "Volumen_veh_h": veh_h, 
        "Vehiculos_Insertados": total_inserted,
        "Teleportings": total_teleports, 
        "Porcentaje_Teleportings": pct_teleports
    })

# Convertir a DataFrame y guardar
df_res = pd.DataFrame(resultados)
df_res.to_csv("resultados_teleports_porcentaje.csv", index=False)

# PASO 5: Generar y guardar la gráfica con umbral del 10%
plt.figure(figsize=(10, 6))

# Curva de porcentaje de Teleportings
plt.plot(
    df_res["Volumen_veh_h"], 
    df_res["Porcentaje_Teleportings"], 
    marker='o', 
    color='crimson', 
    linewidth=2.5, 
    label="% Teleportings"
)

# Línea horizontal del Umbral del 10%
plt.axhline(
    y=10, 
    color='darkblue', 
    linestyle='--', 
    linewidth=2, 
    label="Umbral de Saturación (10%)"
)

plt.title("Porcentaje de Teleportings vs. Volumen Generado en SUMO", fontsize=13, fontweight='bold')
plt.xlabel("Volumen Generado (veh/h)", fontsize=11)
plt.ylabel("Porcentaje de Teleportings (%)", fontsize=11)
plt.ylim(-1, max(df_res["Porcentaje_Teleportings"].max() + 5, 20))  # Ajuste dinámico del eje Y
plt.grid(True, linestyle="--", alpha=0.7)
plt.legend(fontsize=10)

# Guardar y mostrar
plt.savefig("umbral_teleportings_porcentaje.png", dpi=300)
print("\n=== EXPERIMENTO FINALIZADO ===")
print("Gráfica guardada exitosamente como 'umbral_teleportings_porcentaje.png'")
plt.show()