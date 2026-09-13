# 🌍 Sentinel Omega — Estado del Sistema

**Generado:** 2026-07-02 20:28 UTC (14:28 UTC-6)

## Último ciclo

| Métrica | Valor |
|---|---|
| Fantasma | 🔴 **30.2** (CRITICAL) |
| Señal / consenso | NO_SIGNAL (0%) |
| Muro de los 5 | 🚨 BREACH — 3/5 muros |
| Precursores activos | 4: ["SILENT_TRIGGER", "SEISMIC_CLUSTER", "SCHUMANN", "TSUNAMI"] |
| Hora del ciclo | 2026-07-02 20:24 UTC |

## Detecciones recientes

| Precursor | Confianza | Zona |
|---|---|---|
| Tsunami / Maremoto | 70% | regional |
| Resonancia Schumann | 70% | global |
| Enjambre Sísmico Local | 95% | regional |
| Patrón Silent Trigger (Calma) | 90% | global |
| Tsunami / Maremoto | 70% | regional |
| Resonancia Schumann | 70% | global |
| Enjambre Sísmico Local | 95% | regional |
| Patrón Silent Trigger (Calma) | 90% | global |

## 🎯 Firma Match — la memoria reconoce el estado actual

| Similitud | Precedió a | Nodo | Veces vista |
|---|---|---|---|
| **84%** | SISMO_M5 | 81 | 413 |
| **83%** | SISMO_M6 | 71 | 18 |
| **83%** | SISMO_M5 | 14 | 177 |
| **82%** | SISMO_M5 | 14 | 295 |
| **82%** | SISMO_M5 | 81 | 399 |

## ⏱ Anticipación — con cuánto tiempo avisa la firma

| Evento | Lag promedio | Máximo | Mínimo | Eventos medidos |
|---|---|---|---|---|
| SISMO_M5 | **7.2 días** | 14.0 d | 1.0 d | 125 |
| SISMO_M6 | **9.0 días** | 14.0 d | 1.0 d | 144 |
| SISMO_M7 | **11.0 días** | 14.0 d | 1.0 d | 86 |

*Lag = desde cuándo (antes del evento) la firma ya era reconocible en el histórico (in-sample).*

## 🔍 Factores del lag — qué comparten las que avisan antes

| Variable | Firmas rápidas | Firmas lentas | Sesgo |
|---|---|---|---|
| kp_max_72h | 2.39 | 0.15 | ⬆ más en RÁPIDAS (-1.77) |
| kp_max | 4.28 | 0.67 | ⬆ más en RÁPIDAS (-1.46) |
| kp_mean | 0.43 | 0.09 | ⬆ más en RÁPIDAS (-1.32) |
| sismo_count_72h | 13.36 | 5.72 | ⬆ más en RÁPIDAS (-0.80) |
| viento_avg | 1994.95 | 1312.22 | ⬆ más en RÁPIDAS (-0.41) |
| sismo_count_win | 31.63 | 22.39 | ⬆ más en RÁPIDAS (-0.34) |

*Rápidas = tercil con menor anticipación; lentas = tercil con mayor. El sesgo revela qué condiciones alargan o acortan la preparación del evento.*

## Memoria entrenada (30 años)

| Bot | Firmas | Recurrencias | Peso |
|---|---|---|---|
| alfa1 | 114 | 49,001 | 1.50 |
| beta1 | 494 | 49,001 | 1.50 |
| beta2 | 467 | 21,720 | 1.00 |
| delta | 380 | 15,727 | 1.00 |
| padre | 561 | 49,001 | 1.00 |

## 🎯 Asertividad

| Métrica | Valor |
|---|---|
| **Global histórica** (backtest 30 años) | 99.9% |
| **Global viva** (operación resuelta) | — |
| **Últimos 7 días** (viva) | — |

### Individual por bot

| Bot | Histórica (30a) | Viva | Viva 7d | Peso |
|---|---|---|---|---|
| alfa1 | 100.0% | — | — | 1.50 |
| beta1 | 99.9% | — | — | 1.50 |
| beta2 | 99.6% | — | — | 1.00 |
| delta | 100.0% | — | — | 1.00 |
| padre | 99.7% | — | — | 1.00 |

*Histórica = reconocimiento de firmas consolidadas en el backtest. Viva = predicciones en operación calificadas por el Juez al cerrar su ventana de 72h.*

## Juez (auditoría)

- FALLO: 260
- PENDIENTES (ventana abierta): 99

---
*Ciclos totales: 100 · Sentinel Omega · Fractal Core Research*
