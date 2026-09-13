import { useCallback } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { TabIntro, Caption } from "@/components/TabIntro";
import { LineSpark, SimpleBars } from "@/components/charts/Sparkline";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs, riskColor } from "@/lib/utils";

/**
 * Tab 2 — Omega: Schumann vivo vs confianza/layers Omega; dual series; fantasma/Kp; veredictos.
 */
export function OmegaTab() {
  const schF = useCallback(() => api.schumannVivo(120), []);
  const precF = useCallback(() => api.precursores(80), []);
  const layersF = useCallback(() => api.layers(), []);
  const juezF = useCallback(() => api.juez(80, "viva"), []);
  const ovF = useCallback(() => api.overview(), []);
  const botsF = useCallback(() => api.bots(), []);

  const sch = usePoll(schF, 20000);
  const prec = usePoll(precF, 20000);
  const layers = usePoll(layersF, 20000);
  const juez = usePoll(juezF, 20000);
  const ov = usePoll(ovF, 20000);
  const bots = usePoll(botsF, 30000);

  if (sch.error && prec.error) return <ErrorBanner message={sch.error || prec.error || ""} />;
  if (sch.loading && prec.loading && !sch.data && !prec.data) {
    return <EmptyState title="Cargando Omega…" />;
  }

  const agents = ((layers.data?.agents as Record<string, unknown>[]) || []);
  const omegaLayer = agents.find((a) => String(a.label || a.bot_name || "").toLowerCase().includes("omega"));
  const omegaItems = ((bots.data?.items as Record<string, unknown>[]) || []).filter((r) =>
    String(r.bot_name || "").toLowerCase().includes("omega"),
  );
  const veredictos = (juez.data?.items || []).filter((r) =>
    String(r.bot_name || "").toLowerCase().includes("omega"),
  );

  const schSeries = [...(sch.data?.items || [])]
    .reverse()
    .map((r, i) => ({ i, hz: Number(r.schumann_hz ?? 0), act: Number(r.schumann_activity ?? 0) }));
  const precSeries = [...(prec.data || [])]
    .reverse()
    .map((r, i) => ({
      i,
      hz: Number(r.schumann_hz ?? 0),
      fantasma: Number(r.fantasma ?? 0),
      kp: Number(r.kp ?? 0),
    }));

  const latestSch = sch.data?.latest || (sch.data?.items || [])[0] || {};
  const fant = ov.data?.fantasma;

  return (
    <div className="space-y-6">
      <TabIntro title="Omega — Schumann vivo vs confianza">
        <p>
          Omega cruza el latido Schumann (tbl_schumann_vivo) con su propia capa de predicción y el índice Fantasma.
          Una desviación de Hz sola no es alarma; si se mueve con Kp/Bz y el Muro, el sistema marca precursor.
        </p>
        <p>Calma: Hz cerca de 7.83 y Omega en NO_SIGNAL. Acción: Hz fuera de banda + Fantasma MODERATE+ — abrir Muro.</p>
      </TabIntro>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi
          label="Schumann vivo"
          value={latestSch.schumann_hz != null ? `${fmtNum(latestSch.schumann_hz)} Hz` : "—"}
          hint={`Δ vs 7.83 = ${fmtNum(Number(latestSch.schumann_hz ?? 7.83) - 7.83)}`}
        />
        <Kpi
          label="Omega señal"
          value={String(omegaLayer?.prediccion || "SIN_DATOS")}
          hint={`conf ${fmtNum(omegaLayer?.confianza)}`}
        />
        <Kpi
          label="Fantasma"
          value={fmtNum(fant?.value)}
          accent={riskColor(fant?.nivel_riesgo)}
          hint={String(fant?.nivel_riesgo || "")}
        />
        <Kpi label="Kp" value={fmtNum(fant?.kp)} hint="contexto geomagnético" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="mb-1 text-sm font-medium">Serie A — Schumann vivo (Hz)</h4>
          {schSeries.length ? (
            <LineSpark data={schSeries} xKey="i" yKey="hz" height={140} />
          ) : (
            <EmptyState title="Sin tbl_schumann_vivo" detail={sch.data?.caption || ""} />
          )}
          <Caption>Fuente: {sch.data?.source || "tbl_schumann_vivo"}.</Caption>
        </div>
        <div>
          <h4 className="mb-1 text-sm font-medium">Serie B — Fantasma (precursores)</h4>
          {precSeries.length ? (
            <LineSpark data={precSeries} xKey="i" yKey="fantasma" height={140} />
          ) : (
            <EmptyState title="Sin precursores" detail="" />
          )}
          <Caption>Dual contextual: Hz vivo vs Fantasma/Kp de precursores. No es eje causal forzado.</Caption>
        </div>
      </div>

      {precSeries.length ? (
        <div>
          <h4 className="mb-1 text-sm font-medium">Kp reciente (contexto)</h4>
          <SimpleBars
            data={precSeries.slice(-30).map((r) => ({ i: String(r.i), kp: r.kp }))}
            xKey="i"
            bars={[{ key: "kp", color: "#ffc107", name: "Kp" }]}
            height={140}
          />
        </div>
      ) : null}

      <div className="rounded-lg border border-border px-4 py-3">
        <div className="text-xs text-muted">Última capa Omega</div>
        <div className="text-lg font-semibold">{String(omegaLayer?.prediccion || "SIN_DATOS")}</div>
        <div className="text-xs text-muted">
          conf {fmtNum(omegaLayer?.confianza)} · {fmtTs(omegaLayer?.timestamp)} · peso{" "}
          {fmtNum(omegaItems[0]?.peso)}
        </div>
      </div>

      <h4 className="text-sm font-medium">Veredictos Omega (Juez viva)</h4>
      <DataTable
        rows={veredictos.slice(0, 40)}
        empty="Sin filas omega en Juez viva (límite reciente)"
        columns={[
          { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
          { key: "resultado", label: "Resultado" },
          { key: "prediccion", label: "Predicción" },
          { key: "verdad", label: "Verdad" },
          { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
        ]}
      />
      <Caption>
        Fuentes Schumann: tbl_schumann_vivo + snapshot en precursores. NOAA/Kp vía clima y Fantasma. Lectura sola — no
        entrena.
      </Caption>
    </div>
  );
}
