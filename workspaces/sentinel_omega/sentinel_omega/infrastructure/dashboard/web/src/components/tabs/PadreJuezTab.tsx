import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { TabIntro, Caption } from "@/components/TabIntro";
import { Heatmap } from "@/components/charts/Heatmap";
import { SimpleBars } from "@/components/charts/Sparkline";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs } from "@/lib/utils";

/**
 * Tab 4 — Padre + Juez: /api/heatmaps + juez + lags + aciertos + last padre prediction + correlaciones.
 */
export function PadreJuezTab() {
  const hmF = useCallback(() => api.heatmaps(), []);
  const juezF = useCallback(() => api.juez(80, "viva"), []);
  const lagF = useCallback(() => api.lag(), []);
  const acF = useCallback(() => api.aciertos(50), []);
  const layersF = useCallback(() => api.layers(), []);
  const corrF = useCallback(() => api.correlaciones(), []);

  const hm = usePoll(hmF, 60000);
  const juez = usePoll(juezF, 20000);
  const lag = usePoll(lagF, 60000);
  const ac = usePoll(acF, 30000);
  const layers = usePoll(layersF, 20000);
  const corr = usePoll(corrF, 60000);

  if (hm.error && juez.error) return <ErrorBanner message={hm.error || juez.error || ""} />;
  if (juez.loading && !juez.data && hm.loading && !hm.data) {
    return <EmptyState title="Cargando Padre + Juez…" />;
  }

  const models = (hm.data?.models_x_models || {}) as Record<string, unknown>;
  const telem = (hm.data?.telemetry_x_events || {}) as Record<string, unknown>;
  const climatic = (hm.data?.climatic || {}) as Record<string, unknown>;
  const padreCorrHm = (hm.data?.padre_corr || {}) as Record<string, unknown>;
  const omegaCorrHm = (hm.data?.omega_corr || {}) as Record<string, unknown>;

  const bots = (models.bots as string[]) || [];
  const matrix = (models.matrix as (number | null)[][]) || [];
  const modelGet = (r: string, c: string) => {
    const i = bots.indexOf(r);
    const j = bots.indexOf(c);
    if (i < 0 || j < 0) return null;
    const v = matrix[i]?.[j];
    return v == null ? null : Number(v);
  };

  const features = (telem.features as string[]) || [];
  const events = (telem.events as string[]) || [];
  const tMatrix = (telem.matrix as (number | null)[][]) || [];
  const telemGet = (r: string, c: string) => {
    const i = features.indexOf(r);
    const j = events.indexOf(c);
    if (i < 0 || j < 0) return null;
    const v = tMatrix[i]?.[j];
    return v == null ? null : Number(v);
  };

  const padre = layers.data?.padre as Record<string, unknown> | null;
  const summary = ac.data?.summary || {};
  const ant = lag.data?.anticipacion || [];
  const fac = lag.data?.factores || [];

  const corrPadre = corr.data?.padre;
  const corrMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of corrPadre?.items || []) {
      m.set(`${r.patron}|${r.event_class}`, Number(r.fuerza || 0));
    }
    return m;
  }, [corrPadre]);

  return (
    <div className="space-y-6">
      <TabIntro title="Padre + Juez — auditoría y memoria">
        <p>
          El Padre valida en cruz y puede avisar. El Juez compara predicción vs realidad (ACIERTO / FALLO / FP) en fase
          viva. Los heatmaps salen de agregados SQL — nunca se vuelcan los ~2.6M de filas crudas.
        </p>
        <p>
          Calma: muchos ACIERTO y Padre en NO_SIGNAL. Acción: racha de FALLO o Padre con señal alta — revisar Alertas /
          Muro, no entrenar desde aquí.
        </p>
      </TabIntro>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi label="ACIERTOS" value={String(summary.aciertos ?? "—")} accent="#10b981" />
        <Kpi label="FALLOS" value={String(summary.fallos ?? "—")} accent="#ff1744" />
        <Kpi label="FP" value={String(summary.falsos_positivos ?? "—")} accent="#ff9100" />
        <Kpi
          label="ASERTIVIDAD"
          value={
            summary.asertividad != null ? `${(Number(summary.asertividad) * 100).toFixed(1)}%` : "—"
          }
          hint={`${summary.total_resueltos ?? 0} resueltos`}
        />
      </div>

      <div className="rounded-lg border border-border px-4 py-3">
        <div className="text-xs text-muted">Última predicción del Padre (layers)</div>
        <div className="text-lg font-semibold">{String(padre?.prediccion || "SIN_DATOS")}</div>
        <div className="text-xs text-muted">
          conf {fmtNum(padre?.confianza)} · {fmtTs(padre?.timestamp)}
        </div>
      </div>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Heatmap modelos × modelos (asertividad diaria, 30d)</h4>
        {models.present && bots.length ? (
          <Heatmap
            rows={bots}
            cols={bots}
            get={modelGet}
            caption={String(models.caption || "")}
          />
        ) : (
          <EmptyState title="Sin matriz models×models" detail="Juez viva sin días suficientes en común." />
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Heatmap telemetría × eventos (patrones_correlacion)</h4>
        {telem.present && features.length ? (
          <Heatmap
            rows={features.slice(0, 12)}
            cols={events.slice(0, 12)}
            get={telemGet}
            caption={String(telem.caption || "")}
          />
        ) : (
          <EmptyState title="Sin tbl_patrones_correlacion" detail="" />
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Factores climáticos / lags</h4>
        <Caption>{String(climatic.caption || "")}</Caption>
        <DataTable
          rows={((climatic.lag_climatic as Record<string, unknown>[]) || []).slice(0, 20)}
          empty="Sin features climáticas en tbl_factores_lag"
          columns={[
            { key: "feature", label: "Feature" },
            { key: "media_rapidas", label: "Rápidas", render: (r) => fmtNum(r.media_rapidas) },
            { key: "media_lentas", label: "Lentas", render: (r) => fmtNum(r.media_lentas) },
            { key: "diferencia_norm", label: "Δ norm", render: (r) => fmtNum(r.diferencia_norm) },
          ]}
        />
        {ant.length ? (
          <SimpleBars
            data={ant.map((r) => ({ name: r.event_class, h: Number(r.lag_promedio_h || 0) }))}
            xKey="name"
            bars={[{ key: "h", color: "#5e6ad2", name: "horas promedio" }]}
          />
        ) : null}
        <DataTable
          rows={ant}
          empty="Sin tbl_lag_anticipacion"
          columns={[
            { key: "event_class", label: "Evento" },
            { key: "lag_promedio_h", label: "Promedio h", render: (r) => fmtNum(r.lag_promedio_h, 1) },
            { key: "lag_min_h", label: "Mín", render: (r) => fmtNum(r.lag_min_h, 1) },
            { key: "lag_max_h", label: "Máx", render: (r) => fmtNum(r.lag_max_h, 1) },
            { key: "n_eventos", label: "n" },
          ]}
        />
        <DataTable
          rows={fac.slice(0, 25)}
          empty="Sin tbl_factores_lag"
          columns={[
            { key: "feature", label: "Feature" },
            { key: "media_rapidas", label: "Rápidas", render: (r) => fmtNum(r.media_rapidas) },
            { key: "media_lentas", label: "Lentas", render: (r) => fmtNum(r.media_lentas) },
            { key: "diferencia_norm", label: "Δ norm", render: (r) => fmtNum(r.diferencia_norm) },
          ]}
        />
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Juez viva — conteos y recientes</h4>
        <DataTable
          rows={(juez.data?.counts as Record<string, unknown>[]) || []}
          empty="Sin conteos"
          columns={[
            { key: "fase", label: "Fase" },
            { key: "resultado", label: "Resultado" },
            { key: "n", label: "n" },
          ]}
        />
        <DataTable
          rows={juez.data?.items || []}
          columns={[
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
            { key: "bot_name", label: "Bot" },
            { key: "resultado", label: "Resultado" },
            { key: "prediccion", label: "Predicción" },
            { key: "verdad", label: "Verdad" },
            { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            { key: "fase", label: "Fase" },
          ]}
        />
        <Caption>Fuente: {String(juez.data?.source || "TBL_JUEZ_AUDITORIA")}. Límite 80 filas vivas.</Caption>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Correlaciones padre / omega (si hay filas)</h4>
        {corrPadre?.present && (corrPadre.patrones?.length || 0) > 0 ? (
          <Heatmap
            rows={corrPadre.patrones}
            cols={corrPadre.event_classes}
            get={(r, c) => corrMap.get(`${r}|${c}`) ?? null}
          />
        ) : (
          <EmptyState
            title="tbl_correlaciones_padre vacía en DEV"
            detail={`heatmap padre_corr present=${String(padreCorrHm.present)} · omega_corr present=${String(omegaCorrHm.present)}. Sin re-entrenar no hay celdas.`}
          />
        )}
        {(corrPadre?.items || []).length ? (
          <DataTable
            rows={(corrPadre?.items || []).slice(0, 30)}
            columns={[
              { key: "patron", label: "Patrón" },
              { key: "event_class", label: "Evento" },
              { key: "n", label: "n" },
              { key: "fuerza", label: "Fuerza", render: (r) => fmtNum(r.fuerza, 4) },
            ]}
          />
        ) : null}
      </section>
    </div>
  );
}
