#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis de Comportamiento Electoral
Módulo para análisis estadístico y de patrones del padrón de afiliados
"""

import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional
import json
from scipy import stats
from scipy.stats import chi2_contingency
import warnings
warnings.filterwarnings('ignore')


BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "database" / "padron.db"


def get_db_connection():
    """Obtiene conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load_afiliados(filters: Dict = None) -> pd.DataFrame:
    """Carga afiliados desde la BD con filtros opcionales."""
    conn = get_db_connection()
    
    query = "SELECT * FROM afiliados WHERE 1=1"
    params = []
    
    if filters:
        if filters.get('estado'):
            query += " AND estado = ?"
            params.append(filters['estado'])
        if filters.get('provincia'):
            query += " AND provincia LIKE ?"
            params.append(f"%{filters['provincia']}%")
        if filters.get('localidad'):
            query += " AND localidad LIKE ?"
            params.append(f"%{filters['localidad']}%")
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    date_cols = ['fecha_nacimiento', 'fecha_afiliacion', 'created_at', 'updated_at']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    return df

def load_participacion(evento_id: int = None) -> pd.DataFrame:
    """Carga datos de participación electoral."""
    conn = get_db_connection()
    
    query = """
        SELECT p.*, a.dni, a.nombre, a.apellido, a.provincia, a.localidad, 
               a.fecha_nacimiento, a.genero, e.nombre as evento_nombre, e.fecha as evento_fecha
        FROM participacion_electoral p
        JOIN afiliados a ON p.afiliado_id = a.id
        JOIN eventos_electorales e ON p.evento_id = e.id
        WHERE 1=1
    """
    params = []
    
    if evento_id:
        query += " AND p.evento_id = ?"
        params.append(evento_id)
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    return df

# =============================================================================
# ANÁLISIS DEMOGRÁFICO
# =============================================================================

def analisis_edad(df: pd.DataFrame) -> Dict:
    """Análisis de distribución por edad."""
    if 'fecha_nacimiento' not in df.columns:
        return {}
    
    hoy = pd.Timestamp.now()
    df['edad'] = (hoy - df['fecha_nacimiento']).dt.days / 365.25
    df_edad = df.dropna(subset=['edad'])
    
    if len(df_edad) == 0:
        return {}

    return {
        'total': len(df_edad),
        'edad_promedio': round(df_edad['edad'].mean(), 1),
        'edad_mediana': round(df_edad['edad'].median(), 1),
        'desviacion_std': round(df_edad['edad'].std(), 1),
        'min': int(df_edad['edad'].min()),
        'max': int(df_edad['edad'].max()),
        'percentiles': {
            '25': round(df_edad['edad'].quantile(0.25), 1),
            '50': round(df_edad['edad'].quantile(0.50), 1),
            '75': round(df_edad['edad'].quantile(0.75), 1),
            '90': round(df_edad['edad'].quantile(0.90), 1),
            '95': round(df_edad['edad'].quantile(0.95), 1),
        },
        'rangos_etarios': df_edad.groupby(pd.cut(df_edad['edad'], 
            bins=[0, 18, 25, 35, 45, 55, 65, 75, 100],
            labels=['0-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65-74', '75+']
        )).size().to_dict()
    }


def analisis_genero(df: pd.DataFrame) -> Dict:
    """Análisis por género."""
    if 'genero' not in df.columns:
        return {}
    
    dist = df['genero'].value_counts().to_dict()
    total = len(df)
    
    return {
        'distribucion': dist,
        'porcentajes': {k: round(v/total*100, 1) for k, v in dist.items()},
        'total': total
    }


def analisis_geografico(df: pd.DataFrame) -> Dict:
    """Análisis geográfico por provincia y localidad."""
    resultado = {}
    
    if 'provincia' in df.columns:
        prov = df['provincia'].value_counts()
        resultado['provincias'] = {
            'distribucion': prov.to_dict(),
            'top_10': prov.head(10).to_dict(),
            'total_provincias': len(prov)
        }
    
    if 'localidad' in df.columns:
        loc = df['localidad'].value_counts()
        resultado['localidades'] = {
            'distribucion': loc.to_dict(),
            'top_20': loc.head(20).to_dict(),
            'total_localidades': len(loc)
        }
    
    return resultado


def analisis_mesas(df: pd.DataFrame) -> Dict:
    """Análisis de distribución por mesa de votación."""
    if 'mesa_votacion' not in df.columns:
        return {}
    
    mesas = df.dropna(subset=['mesa_votacion'])
    if len(mesas) == 0:
        return {}
    
    dist = mesas['mesa_votacion'].value_counts().sort_index()
    
    return {
        'total_mesas': len(dist),
        'afiliados_por_mesa': dist.to_dict(),
        'promedio_por_mesa': round(len(mesas) / len(dist), 1),
        'mesa_max': int(dist.max()),
        'mesa_min': int(dist.min()),
        'mesas_vacias': int((dist == 0).sum()) if len(dist) > 0 else 0
    }

# =============================================================================
# ANÁLISIS DE PARTICIPACIÓN ELECTORAL
# =============================================================================

def analisis_participacion_general(evento_id: int = None) -> Dict:
    """Análisis general de participación electoral."""
    df_part = load_participacion(evento_id)
    
    if len(df_part) == 0:
        return {'mensaje': 'No hay datos de participación'}
    
    total = len(df_part)
    votaron = df_part['voto_emitido'].sum()
    tasa = (votaron / total * 100) if total > 0 else 0
    
    if 'genero' in df_part.columns:
        part_genero = df_part.groupby('genero')['voto_emitido'].agg(['sum', 'count'])
        part_genero['tasa'] = (part_genero['sum'] / part_genero['count'] * 100).round(1)
    
    if 'fecha_nacimiento' in df_part.columns:
        hoy = pd.Timestamp.now()
        df_part['edad'] = (hoy - pd.to_datetime(df_part['fecha_nacimiento'])).dt.days / 365.25
        df_part['rango_edad'] = pd.cut(df_part['edad'], 
            bins=[0, 18, 25, 35, 45, 55, 65, 75, 100],
            labels=['0-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65-74', '75+']
        )
        part_edad = df_part.groupby('rango_edad')['voto_emitido'].agg(['sum', 'count'])
        part_edad['tasa'] = (part_edad['sum'] / part_edad['count'] * 100).round(1)
    
    if 'provincia' in df_part.columns:
        part_prov = df_part.groupby('provincia')['voto_emitido'].agg(['sum', 'count'])
        part_prov['tasa'] = (part_prov['sum'] / part_prov['count'] * 100).round(1)
        part_prov = part_prov.sort_values('tasa', ascending=False)
    
    return {
        'evento_id': evento_id,
        'total_registros': total,
        'votaron': int(votaron),
        'no_votaron': int(total - votaron),
        'tasa_participacion': round(tasa, 2),
        'por_genero': part_genero.to_dict('index') if 'genero' in df_part.columns else {},
        'por_edad': part_edad.to_dict('index') if 'fecha_nacimiento' in df_part.columns else {},
        'por_provincia': part_prov.to_dict('index') if 'provincia' in df_part.columns else {}
    }


def test_chi_cuadrado_participacion(evento_id: int = None) -> Dict:
    """Test Chi-cuadrado para independencia entre variables y participación."""
    df_part = load_participacion(evento_id)
    
    if len(df_part) == 0:
        return {}
    
    resultados = {}
    
    if 'genero' in df_part.columns:
        tabla = pd.crosstab(df_part['genero'], df_part['voto_emitido'])
        if tabla.shape == (2, 2) or (tabla.shape[0] >= 2 and tabla.shape[1] >= 2):
            chi2, p, dof, expected = chi2_contingency(tabla)
            resultados['genero_vs_voto'] = {
                'chi2': round(chi2, 4),
                'p_value': round(p, 6),
                'grados_libertad': dof,
                'significativo': p < 0.05,
                'tabla_contingencia': tabla.to_dict()
            }
    
    if 'provincia' in df_part.columns:
        top_prov = df_part['provincia'].value_counts().head(10).index
        df_top = df_part[df_part['provincia'].isin(top_prov)]
        tabla = pd.crosstab(df_top['provincia'], df_top['voto_emitido'])
        if tabla.shape[0] >= 2 and tabla.shape[1] >= 2:
            chi2, p, dof, expected = chi2_contingency(tabla)
            resultados['provincia_vs_voto'] = {
                'chi2': round(chi2, 4),
                'p_value': round(p, 6),
                'grados_libertad': dof,
                'significativo': p < 0.05
            }
    
    return resultados


def analisis_cohorte_afiliacion(df: pd.DataFrame) -> Dict:
    """Análisis de cohortes por año de afiliación."""
    if 'fecha_afiliacion' not in df.columns:
        return {}
    
    df = df.copy()
    df['anio_afiliacion'] = pd.to_datetime(df['fecha_afiliacion']).dt.year
    
    cohorte = df.groupby('anio_afiliacion').agg(
        total=('id', 'count'),
        activos=('estado', lambda x: (x == 'activo').sum()),
        inactivos=('estado', lambda x: (x == 'inactivo').sum())
    ).reset_index()
    
    cohorte['tasa_retencion'] = (cohorte['activos'] / cohorte['total'] * 100).round(1)
    
    return {
        'cohortes': cohorte.to_dict('records'),
        'total_anios': len(cohorte),
        'anio_mas_afiliaciones': int(cohorte.loc[cohorte['total'].idxmax(), 'anio_afiliacion']) if len(cohorte) > 0 else None
    }

# =============================================================================
# ANÁLISIS AVANZADO / CIMÁTICA
# =============================================================================

def analisis_cimatica(df: pd.DataFrame) -> Dict:
    """
    Análisis cimático: patrones vibracionales en datos electorales.
    Análisis de frecuencia y resonancia en series temporales de afiliación.
    """
    if 'fecha_afiliacion' not in df.columns:
        return {}
    
    df = df.copy()
    df['fecha_afiliacion'] = pd.to_datetime(df['fecha_afiliacion'])
    df = df.dropna(subset=['fecha_afiliacion'])
    
    if len(df) < 10:
        return {'mensaje': 'Datos insuficientes para análisis cimático'}
    
    serie_diaria = df.groupby(df['fecha_afiliacion'].dt.date).size()
    serie_diaria = serie_diaria.sort_index()
    
    from scipy.fft import fft, fftfreq
    
    valores = serie_diaria.values.astype(float)
    n = len(valores)
    
    if n < 4:
        return {'mensaje': 'Serie temporal muy corta'}
    
    yf = fft(valores - np.mean(valores))
    xf = fftfreq(n, 1)[:n//2]
    magnitudes = 2.0/n * np.abs(yf[:n//2])
    
    idx_top = np.argsort(magnitudes)[-5:][::-1]
    frecuencias_dominantes = []
    for idx in idx_top:
        if xf[idx] > 0:
            periodo_dias = 1 / xf[idx]
            frecuencias_dominantes.append({
                'frecuencia': round(xf[idx], 6),
                'periodo_dias': round(periodo_dias, 1),
                'magnitud': round(magnitudes[idx], 2)
            })
    
    from scipy.signal import correlate
    autocorr = correlate(valores - np.mean(valores), valores - np.mean(valores), mode='full')
    autocorr = autocorr[n-1:] / autocorr[n-1]
    
    picos = []
    for i in range(1, min(len(autocorr)-1, 60)):
        if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1] and autocorr[i] > 0.3:
            picos.append({'lag_dias': i, 'correlacion': round(autocorr[i], 3)})
    
    x = np.arange(len(valores))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, valores)
    
    return {
        'total_dias': len(serie_diaria),
        'promedio_diario': round(np.mean(valores), 2),
        'std_diario': round(np.std(valores), 2),
        'frecuencias_dominantes': frecuencias_dominantes,
        'autocorrelacion_picos': picos[:5],
        'tendencia': {
            'pendiente': round(slope, 4),
            'r_squared': round(r_value**2, 4),
            'p_value': round(p_value, 6),
            'direccion': 'creciente' if slope > 0 else 'decreciente' if slope < 0 else 'estable'
        },
        'estacionalidad_detectada': len(picos) > 0,
        'periodicidad_principal_dias': picos[0]['lag_dias'] if picos else None
    }


def analisis_red_afiliados(df: pd.DataFrame) -> Dict:
    """Análisis de redes: conexiones por mesa, localidad, familia (apellido)."""
    if len(df) == 0:
        return {}
    
    resultado = {}
    
    if 'mesa_votacion' in df.columns:
        mesas = df.dropna(subset=['mesa_votacion'])
        if len(mesas) > 0:
            mesa_groups = mesas.groupby('mesa_votacion').size()
            resultado['por_mesa'] = {
                'total_mesas': len(mesa_groups),
                'tamano_promedio': round(mesa_groups.mean(), 1),
                'tamano_mediano': round(mesa_groups.median(), 1),
                'max_afiliados_mesa': int(mesa_groups.max()),
                'distribucion_tamanos': mesa_groups.value_counts().sort_index().to_dict()
            }
    
    if 'apellido' in df.columns:
        apellidos = df['apellido'].value_counts()
        apellidos_comunes = apellidos[apellidos >= 3]
        resultado['por_apellido'] = {
            'apellidos_unicos': len(apellidos),
            'apellidos_comunes_3plus': len(apellidos_comunes),
            'top_apellidos': apellidos.head(20).to_dict(),
            'posibles_familias': apellidos_comunes.head(30).to_dict()
        }
    
    if 'localidad' in df.columns and 'apellido' in df.columns:
        loc_ap = df.groupby(['localidad', 'apellido']).size().reset_index(name='count')
        loc_ap = loc_ap[loc_ap['count'] >= 3].sort_values('count', ascending=False)
        resultado['localidad_apellido'] = {
            'grupos_3plus': len(loc_ap),
            'top_grupos': loc_ap.head(20).to_dict('records')
        }
    
    return resultado


def analisis_outliers(df: pd.DataFrame) -> Dict:
    """Detección de valores atípicos en datos del padrón."""
    outliers = {}
    
    if 'fecha_nacimiento' in df.columns:
        hoy = pd.Timestamp.now()
        df['edad'] = (hoy - pd.to_datetime(df['fecha_nacimiento'])).dt.days / 365.25
        edades = df.dropna(subset=['edad'])
        
        Q1 = edades['edad'].quantile(0.25)
        Q3 = edades['edad'].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        
        outliers_edad = edades[(edades['edad'] < lower) | (edades['edad'] > upper)]
        outliers['edad'] = {
            'limite_inferior': round(lower, 1),
            'limite_superior': round(upper, 1),
            'count': len(outliers_edad),
            'ejemplos': outliers_edad[['dni', 'nombre', 'apellido', 'edad']].head(10).to_dict('records')
        }
    
    if 'mesa_votacion' in df.columns:
        mesa_counts = df.dropna(subset=['mesa_votacion']).groupby('mesa_votacion').size()
        Q1 = mesa_counts.quantile(0.25)
        Q3 = mesa_counts.quantile(0.75)
        IQR = Q3 - Q1
        upper = Q3 + 1.5 * IQR
        
        mesas_grandes = mesa_counts[mesa_counts > upper]
        outliers['mesas_grandes'] = {
            'limite_superior': round(upper, 1),
            'count': len(mesas_grandes),
            'mesas': mesas_grandes.head(10).to_dict()
        }
    
    return outliers

# =============================================================================
# REPORTES COMPLETOS
# =============================================================================

def generar_reporte_completo(filters: Dict = None) -> Dict:
    """Genera reporte completo de análisis."""
    df = load_afiliados(filters)
    
    if len(df) == 0:
        return {'error': 'No hay datos para analizar'}
    
    reporte = {
        'fecha_generacion': datetime.now().isoformat(),
        'filtros_aplicados': filters or {},
        'total_afiliados_analizados': len(df),
        'demografico': {
            'edad': analisis_edad(df),
            'genero': analisis_genero(df),
            'geografico': analisis_geografico(df),
            'mesas': analisis_mesas(df)
        },
        'temporal': {
            'cohortes_afiliacion': analisis_cohorte_afiliacion(df),
            'cimatica': analisis_cimatica(df)
        },
        'redes': analisis_red_afiliados(df),
        'outliers': analisis_outliers(df)
    }
    
    conn = get_db_connection()
    eventos = conn.execute("SELECT id, nombre FROM eventos_electorales WHERE activo = 1").fetchall()
    conn.close()
    
    if eventos:
        reporte['participacion'] = {}
        for ev in eventos:
            reporte['participacion'][ev['nombre']] = {
                'general': analisis_participacion_general(ev['id']),
                'chi_cuadrado': test_chi_cuadrado_participacion(ev['id'])
            }
    
    return reporte


def exportar_reporte_json(reporte: Dict, filepath: str):
    """Exporta reporte a JSON."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# FUNCIONES DE UTILIDAD PARA STREAMLIT
# =============================================================================

def get_resumen_ejecutivo(filters: Dict = None) -> Dict:
    """Resumen ejecutivo para dashboard."""
    df = load_afiliados(filters)
    
    if len(df) == 0:
        return {}
    
    return {
        'total': len(df),
        'activos': int((df['estado'] == 'activo').sum()) if 'estado' in df.columns else 0,
        'con_email': int(df['email'].notna().sum()) if 'email' in df.columns else 0,
        'con_telefono': int(df['telefono'].notna().sum()) if 'telefono' in df.columns else 0,
        'provincias_unicas': df['provincia'].nunique() if 'provincia' in df.columns else 0,
        'localidades_unicas': df['localidad'].nunique() if 'localidad' in df.columns else 0,
        'mesas_unicas': df['mesa_votacion'].nunique() if 'mesa_votacion' in df.columns else 0,
        'edad_promedio': round(
            (pd.Timestamp.now() - pd.to_datetime(df['fecha_nacimiento'])).dt.days.mean() / 365.25, 1
        ) if 'fecha_nacimiento' in df.columns and df['fecha_nacimiento'].notna().any() else None
    }


if __name__ == "__main__":
    print("=== Test Análisis Comportamiento ===")
    reporte = generar_reporte_completo()
    print(json.dumps(reporte, indent=2, default=str, ensure_ascii=False)[:2000])
