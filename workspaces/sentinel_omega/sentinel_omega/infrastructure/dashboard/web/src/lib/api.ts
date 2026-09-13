const BASE = import.meta.env.VITE_API_BASE ?? "";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export type Overview = {
  ts: number;
  fantasma: {
    value: number | null;
    nivel_riesgo: string | null;
    schumann_hz: number | null;
    kp: number | null;
    bz_nT: number | null;
    viento_km_s: number | null;
  };
  muro: {
    walls_active: number | null;
    muro_breach: boolean;
    correlation_score: number | null;
    risk_label: string | null;
  };
  ciclo: Record<string, unknown> | null;
  counts: {
    nodos: number;
    sismos_m45: number;
    detecciones_latest: boolean;
  };
  risk_distribution: Record<string, number>;
  cycle_alert_rate: Record<string, unknown>;
  health?: {
    last_cycle_ts: number | null;
    stale: boolean;
    stale_seconds: number;
  };
};

export type Health = {
  status: string;
  db_path: string;
  db_exists: boolean;
  db_readable?: boolean;
  stale: boolean;
  last_cycle_ts: number | null;
  fuente_sismos: number;
  remap_aplicado: boolean;
  lectura: string;
  tree: string;
  ciclos?: number;
  error?: string;
};

export const api = {
  health: () => getJson<Health>("/api/health"),
  overview: () => getJson<Overview>("/api/overview"),
  precursores: (limit = 50) =>
    getJson<Record<string, unknown>[]>(`/api/precursores?limit=${limit}`),
  muro: (limit = 50) => getJson<Record<string, unknown>[]>(`/api/muro?limit=${limit}`),
  nodos: () => getJson<Record<string, unknown>[]>("/api/nodos"),
  sismos: (min = 4.5, limit = 200) =>
    getJson<{
      min_magnitude: number;
      count: number;
      total_matching: number;
      items: Record<string, unknown>[];
    }>(`/api/sismos?min_magnitude=${min}&limit=${limit}`),
  ciclos: (limit = 50) => getJson<Record<string, unknown>[]>(`/api/ciclos?limit=${limit}`),
  detecciones: (limit = 100) =>
    getJson<Record<string, unknown>[]>(`/api/detecciones?limit=${limit}`),
  aciertos: (limit = 100) =>
    getJson<{
      pesos: Record<string, unknown>[];
      recent: Record<string, unknown>[];
      summary: Record<string, unknown>;
    }>(`/api/aciertos?limit=${limit}`),
  alertas: (limit = 50) => getJson<Record<string, unknown>>(`/api/alertas?limit=${limit}`),
  agente: () => getJson<Record<string, unknown>>("/api/agente"),
  ask: (question: string) =>
    postJson<{ answer: string; citations: string[] }>("/api/ask", { question }),
  cimatica: (limit = 50, ambito?: string) =>
    getJson<{
      total: number;
      limit: number;
      ambito: string | null;
      by_ambito: Record<string, unknown>[];
      items: Record<string, unknown>[];
    }>(`/api/cimatica?limit=${limit}${ambito ? `&ambito=${encodeURIComponent(ambito)}` : ""}`),
  correlaciones: () =>
    getJson<{
      padre: { present: boolean; items: Record<string, unknown>[]; patrones: string[]; event_classes: string[]; table: string };
      omega: { present: boolean; items: Record<string, unknown>[]; patrones: string[]; event_classes: string[]; table: string };
    }>("/api/correlaciones"),
  bots: () => getJson<Record<string, unknown>>("/api/bots"),
  sesgo: () => getJson<Record<string, unknown>>("/api/sesgo"),
  aprendizaje: () =>
    getJson<{
      present: boolean;
      source?: string;
      caption?: string;
      series: Record<string, { dia: string; asertividad_cum: number | null; n_cum: number }[]>;
    }>("/api/aprendizaje"),
  firmas: () => getJson<Record<string, unknown>>("/api/firmas"),
  lag: () =>
    getJson<{ factores: Record<string, unknown>[]; anticipacion: Record<string, unknown>[] }>("/api/lag"),
  juez: (limit = 100, fase = "viva") =>
    getJson<{ items: Record<string, unknown>[]; counts: Record<string, unknown>[]; source: string }>(
      `/api/juez?limit=${limit}&fase=${fase}`,
    ),
  layers: () => getJson<Record<string, unknown>>("/api/layers"),
  reportes: (name?: string) =>
    getJson<{ present: boolean; files: { name: string; bytes: number; mtime: number }[]; content: string | null; name: string | null; dir: string }>(
      name ? `/api/reportes?name=${encodeURIComponent(name)}` : "/api/reportes",
    ),
  unificado: () => getJson<Record<string, unknown>>("/api/unificado"),
  telemetry: () => getJson<{
    caption_in: string;
    caption_out: string;
    sources: Record<string, unknown>[];
    locf_cache_n: number;
    ciclo: Record<string, unknown> | null;
    precursor: Record<string, unknown> | null;
  }>("/api/telemetry"),
  /** Matrices Padre+Juez / telemetría / climática */
  heatmaps: () => getJson<Record<string, unknown>>("/api/heatmaps"),
  /** Consenso: ciclos + pesos bots */
  consenso: (limit = 50) => getJson<Record<string, unknown>>(`/api/consenso?limit=${limit}`),
  /** Figura cimática live vs biblioteca */
  cimaticaAhora: () => getJson<Record<string, unknown>>("/api/cimatica/ahora"),
  /** Estado de config Telegram (sin secretos) */
  telegramStatus: () => getJson<Record<string, unknown>>("/api/telegram/status"),
  /** Serie Schumann vivo (tbl_schumann_vivo) */
  schumannVivo: (limit = 120) =>
    getJson<{
      present: boolean;
      items: Record<string, unknown>[];
      latest: Record<string, unknown> | null;
      source: string;
      caption: string;
    }>(`/api/schumann_vivo?limit=${limit}`),
  /** Delta cross + psique financiera */
  delta: (limit = 80) =>
    getJson<{
      present: boolean;
      delta: Record<string, unknown>[];
      psique: Record<string, unknown>[];
      latest_delta: Record<string, unknown> | null;
      latest_psique: Record<string, unknown> | null;
      source: string;
      caption: string;
    }>(`/api/delta?limit=${limit}`),
  /** Muestras recientes clima espacial (Bz/Kp/viento) */
  climaEspacial: (limit = 80) =>
    getJson<{
      present: boolean;
      items: Record<string, unknown>[];
      latest: Record<string, unknown> | null;
      source: string;
      caption: string;
    }>(`/api/clima_espacial?limit=${limit}`),
};
