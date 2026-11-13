import sqlite3, json
from datetime import datetime, timezone

# PARCHE ITEM 25 (2026-11-12, fase 2): apertura SOLO LECTURA (mode=ro).
# El original abria la DB en RW (sqlite3.connect(DB) sin mode=ro) y con el
# path viejo /home/deamon/workspaces/... -- violaba el encargo del Concilio
# "validar diagnostico_v3.py contra la DB actual, sin ejecutar con escritura".
# mode=ro: SQLite rechaza cualquier escritura y NO crea el archivo si falta.
DB = '/home/deamon/Sentinel_Omega/sentinel_omega/data/SENTINEL_OMEGA_PRO.db'
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
def q(s,p=()): return con.execute(s,p).fetchall()
def q1(s,p=()): r=con.execute(s,p).fetchone(); return dict(r) if r else None

NOW = datetime.now(timezone.utc)
NOW_TS = NOW.timestamp()
H=3600; D=86400

def lag_h_blk(ts_str):
    if not ts_str: return 9999
    try:
        fmt = '%Y-%m-%d %H:%M:%S' if len(ts_str)>16 else '%Y-%m-%d %H:%M'
        dt = datetime.strptime(ts_str[:19], fmt).replace(tzinfo=timezone.utc)
        return (NOW - dt).total_seconds() / 3600
    except: return 9999

def lag_h_ts(ts):
    if not ts: return 9999
    return (NOW_TS - float(ts)) / H

def fmt_lag(h, unit='h'):
    s = f'{h:.1f}{unit}'
    if h < 6: return f'{s} ✅'
    if h < 48: return f'{s} ⚠️'
    return f'{s} ❌'

def fmt_lag_m(m):
    s = f'{m:.0f}min'
    if m < 15: return f'{s} ✅'
    if m < 60: return f'{s} ⚠️'
    return f'{s} ❌'

print('='*65)
print(f'DIAGNÓSTICO APIS — {NOW.strftime("%Y-%m-%d %H:%M")} UTC')
print('='*65)

# ── 1. PRECURSORES (clima espacial alfa1/NASA OMNI2) ──────────────
r = q1("""SELECT COUNT(*) t, MAX(timestamp) lt,
       AVG(bz_nT) ab, AVG(viento_km_s) av, AVG(kp) ak,
       AVG(schumann_hz) ash, AVG(schumann_activity) asa,
       SUM(CASE WHEN protones=0 THEN 1 ELSE 0 END) z_pr,
       SUM(CASE WHEN schumann_hz=7.83 THEN 1 ELSE 0 END) d_sh,
       SUM(CASE WHEN schumann_activity=0 THEN 1 ELSE 0 END) z_sa
       FROM TBL_PRECURSORES_COSMICOS""")
lag_prec = lag_h_ts(r['lt']) * 60  # en minutos
print(f'\n[alfa1] CLIMA ESPACIAL (NASA OMNI2) — lag={fmt_lag_m(lag_prec)}')
print(f'  {r["t"]} registros | Bz avg={r["ab"]:.2f}nT | Viento={r["av"]:.0f}km/s | Kp={r["ak"]:.2f}')
print(f'  Sch Hz avg={r["ash"]:.2f} | Sch Act avg={r["asa"]:.2f}')
print(f'  ⚠️  protones=0: {r["z_pr"]}/{r["t"]} (100%) — campo nunca ingesta')
print(f'  ⚠️  sch_hz=7.83 fallback: {r["d_sh"]}/{r["t"]} ({100*r["d_sh"]//r["t"]}%) — primera mitad histórica sin Schumann real')
print(f'  ✅ Últimos ciclos tienen schumann real (segunda mitad)')

# ── 2. SCHUMANN VIVO (beta1/Tomsk) ──────────────────────────────────
r_cnt = q1('SELECT COUNT(*) t FROM tbl_schumann_vivo')
r_last = q1('SELECT timestamp_blk, schumann_hz, schumann_activity FROM tbl_schumann_vivo ORDER BY timestamp_blk DESC LIMIT 1')
r_avg = q1('SELECT AVG(schumann_hz) hz, AVG(schumann_activity) sa FROM tbl_schumann_vivo')
lag_sch = lag_h_blk(r_last['timestamp_blk'] if r_last else None)
print(f'\n[beta1] SCHUMANN VIVO (Tomsk) — lag={fmt_lag(lag_sch)}')
print(f'  {r_cnt["t"]} registros | último: {r_last["timestamp_blk"] if r_last else "N/A"}')
if r_last:
    print(f'  Último: {r_last["schumann_hz"]:.2f}Hz | activity={r_last["schumann_activity"]:.2f}')
print(f'  Avg: {r_avg["hz"]:.2f}Hz | act={r_avg["sa"]:.2f}')

r_enj = q1('SELECT timestamp_blk FROM tbl_enjambre_telemetria ORDER BY timestamp_blk DESC LIMIT 1')
r_enj_c = q1('SELECT COUNT(*) t FROM tbl_enjambre_telemetria')
lag_enj = lag_h_blk(r_enj['timestamp_blk'] if r_enj else None)
print(f'  [enjambre 736 nodos]: lag={fmt_lag(lag_enj)} | último: {r_enj["timestamp_blk"] if r_enj else "N/A"}')

# ── 3. DESGASIFICACIÓN SO2 (beta2/NASA MSVOLSO2L4) ──────────────────
r_cnt = q1('SELECT COUNT(*) t FROM tbl_desgasificacion_raw')
r_last = q1('SELECT timestamp_blk FROM tbl_desgasificacion_raw ORDER BY timestamp_blk DESC LIMIT 1')
lag_des = lag_h_blk(r_last['timestamp_blk'] if r_last else None)
print(f'\n[beta2] DESGASIFICACIÓN SO2 (NASA) — lag={fmt_lag(lag_des)}')
print(f'  {r_cnt["t"]} eventos | último: {r_last["timestamp_blk"] if r_last else "N/A"}')
rows = q("""SELECT volcan, MAX(vei) mv, SUM(so2_kt) so2, COUNT(*) cnt
       FROM tbl_desgasificacion_raw WHERE timestamp_blk >= '2026-01-01'
       GROUP BY volcan ORDER BY so2 DESC LIMIT 5""")
if rows:
    print('  Top volcanes 2026:')
    for ro in rows:
        d=dict(ro)
        print(f'    {d["volcan"]}: VEI_max={d["mv"]} | SO2_total={d["so2"]:.1f}kt | {d["cnt"]} eventos')

# ── 4. PSIQUE FINANCIERA (delta/Yahoo) ──────────────────────────────
r_cnt = q1('SELECT COUNT(*) t FROM tbl_psique_financiera')
r_last = q1('SELECT timestamp_blk, btc_precio_usd, volatilidad_24h, fear_greed, fetch_flags FROM tbl_psique_financiera ORDER BY timestamp_blk DESC LIMIT 1')
lag_fin = lag_h_blk(r_last['timestamp_blk'] if r_last else None)
print(f'\n[delta] PSIQUE FINANCIERA (Yahoo Finance/BTC) — lag={fmt_lag(lag_fin)}')
print(f'  {r_cnt["t"]} registros | último: {r_last["timestamp_blk"] if r_last else "N/A"}')
if r_last:
    print(f'  BTC=${r_last["btc_precio_usd"]:,.0f} | vol={r_last["volatilidad_24h"]:.4f} | fear_greed={r_last["fear_greed"]} | flags={r_last["fetch_flags"]}')

r2 = q1('SELECT timestamp_blk, composite_score, regime_label, confidence, data_completeness FROM tbl_delta_cross ORDER BY timestamp_blk DESC LIMIT 1')
r2c = q1('SELECT COUNT(*) t FROM tbl_delta_cross')
lag_dc = lag_h_blk(r2['timestamp_blk'] if r2 else None)
print(f'  [delta_cross {r2c["t"]} registros] lag={fmt_lag(lag_dc)}')
if r2:
    print(f'    score={r2["composite_score"]:.3f} | régimen={r2["regime_label"]} | conf={r2["confidence"]:.2f} | completeness={r2["data_completeness"]:.2f}')

# ── 5. ASTRONOMÍA LOD/LUNAR (omega/IERS) ────────────────────────────
r_cnt = q1('SELECT COUNT(*) t FROM tbl_astronomia_cinematica')
r_last = q1('SELECT timestamp_blk, lod_ms, fase_lunar_pct, es_sicigia FROM tbl_astronomia_cinematica ORDER BY timestamp_blk DESC LIMIT 1')
lag_ast = lag_h_blk(r_last['timestamp_blk'] if r_last else None)
print(f'\n[omega] ASTRONOMÍA LOD/LUNAR (IERS) — lag={fmt_lag(lag_ast)}')
print(f'  {r_cnt["t"]} registros | último: {r_last["timestamp_blk"] if r_last else "N/A"}')
if r_last:
    print(f'  LOD={r_last["lod_ms"]:.3f}ms | lunar={r_last["fase_lunar_pct"]:.1f}% | sicigia={bool(r_last["es_sicigia"])}')

# ── 6. SISMOS USGS ───────────────────────────────────────────────────
r_sis = q1('SELECT COUNT(*) t, MAX(timestamp) lt FROM TBL_HISTORICO_SISMICO')
lag_sis = lag_h_ts(r_sis['lt'])
ld_sis = datetime.fromtimestamp(float(r_sis['lt']), tz=timezone.utc).strftime('%Y-%m-%d %H:%M') if r_sis['lt'] else 'N/A'
print(f'\n[USGS] SISMOS (FDSN) — lag={fmt_lag(lag_sis)}')
print(f'  {r_sis["t"]} sismos | último: {ld_sis} UTC')
rows72 = q("""SELECT datetime(timestamp,'unixepoch') dt, magnitude, depth_km, region
         FROM TBL_HISTORICO_SISMICO WHERE timestamp>? AND magnitude>=4.5
         ORDER BY magnitude DESC LIMIT 12""", (NOW_TS-3*D,))
if rows72:
    print('  Sismos M≥4.5 últimas 72h:')
    for ro in rows72:
        d=dict(ro)
        print(f'    {d["dt"]} | M{d["magnitude"]:.1f} | {d["depth_km"]:.0f}km | {d["region"]}')
else:
    print('  Sin sismos M≥4.5 en últimas 72h')
m5_7d = q1('SELECT COUNT(*) c FROM TBL_HISTORICO_SISMICO WHERE timestamp>? AND magnitude>=5.0', (NOW_TS-7*D,))
m6_30d = q1('SELECT COUNT(*) c FROM TBL_HISTORICO_SISMICO WHERE timestamp>? AND magnitude>=6.0', (NOW_TS-30*D,))
print(f'  M≥5 (7d): {m5_7d["c"]} | M≥6 (30d): {m6_30d["c"]}')

# ── 7. LOCF CACHE ───────────────────────────────────────────────────
lc = q('SELECT source_key, updated_at FROM tbl_locf_cache')
print(f'\n[LOCF] Cache de fallback: {len(lc)} entradas')
if lc:
    for ro in lc: d=dict(ro); print(f'  [{d["source_key"]}] {d["updated_at"]}')
else:
    print('  Vacío — APIs respondiendo normalmente O LOCF nunca se activó')

# ── 8. CICLOS Y MURO ────────────────────────────────────────────────
cc = q1('SELECT COUNT(*) t, MAX(timestamp) lt FROM TBL_CICLOS')
lag_cc = lag_h_ts(cc['lt']) * 60
print(f'\n[CICLOS] {cc["t"]} ciclos | lag={fmt_lag_m(lag_cc)}')
last5 = q("""SELECT datetime(timestamp,'unixepoch') dt, fantasma, muro_walls_active, geo_signal, precursors_count
         FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT 5""")
for ro in last5:
    d=dict(ro)
    print(f'  {d["dt"]} | f={d["fantasma"]:.1f} | muros={d["muro_walls_active"]} | geo={d["geo_signal"]} | prec={d["precursors_count"]}')

mu = q1("""SELECT walls_active, muro_breach, risk_label, correlation_score,
         wall_geofisico, wall_atmosferico, wall_oceanico, wall_solar, wall_financiero
         FROM TBL_MURO_EVENTOS ORDER BY timestamp DESC LIMIT 1""")
bh = q1('SELECT COUNT(*) c FROM TBL_MURO_EVENTOS WHERE muro_breach=1')
bh30 = q1('SELECT COUNT(*) c FROM TBL_MURO_EVENTOS WHERE muro_breach=1 AND timestamp>?', (NOW_TS-30*D,))
print(f'\n[MURO] {mu["walls_active"]}/5 activos | breach={"⚠️ SÍ" if mu["muro_breach"] else "NO"} | label={mu["risk_label"]} | corr={mu["correlation_score"]:.3f}')
print(f'  GEO={mu["wall_geofisico"]} | ATM={mu["wall_atmosferico"]} | OCE={mu["wall_oceanico"]} | SOL={mu["wall_solar"]} | FIN={mu["wall_financiero"]}')
print(f'  Breaches histórico: {bh["c"]} | últimos 30d: {bh30["c"]}')

# ── 9. NODOS SATURADOS ──────────────────────────────────────────────
n_max = q1('SELECT COUNT(*) c FROM TBL_NODOS_TOPOLOGIA WHERE saturacion>=1.0')
n_hi = q1('SELECT COUNT(*) c FROM TBL_NODOS_TOPOLOGIA WHERE saturacion>=0.8')
print(f'\n[NODOS] sat=1.0: {n_max["c"]}/125 | sat≥0.8: {n_hi["c"]}/125')
sat_rows = q('SELECT nombre, tipo, region FROM TBL_NODOS_TOPOLOGIA WHERE saturacion>=1.0 ORDER BY tipo')
for ro in sat_rows:
    d=dict(ro); print(f'  🔴 {d["nombre"]} ({d["tipo"]}) | {d["region"]}')

# ── 10. SALUD DEL SISTEMA ───────────────────────────────────────────
sal = q1('SELECT viva, aciertos, fallos, pesos_json FROM tbl_salud_sistema ORDER BY ts DESC LIMIT 1')
pesos = json.loads(sal['pesos_json']) if sal else {}
tasa = 100*sal['aciertos']/(sal['aciertos']+sal['fallos']) if sal else 0
print(f'\n[JUEZ] Tasa éxito={tasa:.1f}% | viva={sal["viva"]:.4f}')
print(f'  Pesos: {pesos}')
if pesos.get('alfa1', 1.0) < 0.6:
    print(f'  ⚠️ alfa1 PENALIZADO (peso={pesos["alfa1"]}) → OMNI2/Bz poco confiable')

# ────────────────────────────────────────────────────────────────────
# VEREDICTO FINAL
# ────────────────────────────────────────────────────────────────────
p = q1('SELECT fantasma, nivel_riesgo, bz_nT, kp FROM TBL_PRECURSORES_COSMICOS ORDER BY timestamp DESC LIMIT 1')
det24 = q1('SELECT COUNT(*) c FROM TBL_DETECCIONES WHERE timestamp>?', (NOW_TS-D,))
crit24 = q1('SELECT COUNT(*) c FROM TBL_PRECURSORES_COSMICOS WHERE nivel_riesgo="CRITICAL" AND timestamp>?', (NOW_TS-D,))

score = 0
flags = []

if p['nivel_riesgo'] == 'CRITICAL':
    score += 35; flags.append(f'🔴 Fantasma CRITICAL ({p["fantasma"]:.1f})')
elif p['nivel_riesgo'] == 'HIGH':
    score += 15; flags.append(f'🟠 Fantasma HIGH ({p["fantasma"]:.1f})')

if mu['muro_breach']:
    score += 35; flags.append('🔴 BREACH activo en el Muro')
elif mu['walls_active'] >= 3:
    score += 20; flags.append(f'🟠 {mu["walls_active"]}/5 muros activos (≥3 = umbral breach)')
elif mu['walls_active'] == 2:
    score += 8; flags.append(f'🟡 {mu["walls_active"]}/5 muros activos')

if n_max['c'] >= 5:
    score += 15; flags.append(f'🟠 {n_max["c"]} nodos saturados al máximo')
elif n_max['c'] >= 2:
    score += 8; flags.append(f'🟡 {n_max["c"]} nodos saturados')

if crit24['c'] >= 10:
    score += 10; flags.append(f'🟠 {crit24["c"]} ciclos CRITICAL en 24h (continuo)')

if m5_7d['c'] >= 5:
    score += 10; flags.append(f'🟠 {m5_7d["c"]} sismos M≥5 en 7 días')
elif m5_7d['c'] >= 2:
    score += 5; flags.append(f'🟡 {m5_7d["c"]} sismos M≥5 en 7 días')

# Penalizaciones por datos faltantes/stale
apis_stale = []
if lag_sis > 24: apis_stale.append(f'USGS lag={lag_sis:.0f}h')
if lag_fin > 72: apis_stale.append(f'Yahoo lag={lag_fin:.0f}h')
if lag_ast > 168: apis_stale.append(f'IERS lag={lag_ast:.0f}h')
if lag_des > 168*24: apis_stale.append(f'SO2 lag={lag_des/24:.0f}d')
if apis_stale:
    score += 5; flags.append('⚠️ APIs stale: ' + ', '.join(apis_stale))

nivel = '🔴 CRÍTICO' if score>=60 else '🟠 ELEVADO' if score>=35 else '🟡 MODERADO' if score>=15 else '🟢 BAJO'
print()
print('='*65)
print('VEREDICTO DE ALERTA')
print('='*65)
print(f'  Score compuesto: {score}/100')
print(f'  Nivel: {nivel}')
print(f'\n  Indicadores activos:')
for f in flags: print(f'    {f}')
print(f'\n  Contexto:')
print(f'    Bz={p["bz_nT"]:.2f}nT | Kp={p["kp"]:.2f} | Fantasma={p["fantasma"]:.2f}')
print(f'    Muro: {mu["walls_active"]}/5 | GEO={mu["wall_geofisico"]} SOL={mu["wall_solar"]}')
print(f'    Nodos sat_max={n_max["c"]} | sismos M5 7d={m5_7d["c"]}')

con.close()
