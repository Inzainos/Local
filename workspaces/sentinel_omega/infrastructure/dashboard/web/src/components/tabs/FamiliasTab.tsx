import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { TabIntro, Caption } from "@/components/TabIntro";
import { LineSpark, SimpleBars } from "@/components/charts/Sparkline";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs } from "@/lib/utils";

/**
 * Tab 1 — Familias (SNT): secciones apiladas Alfa → Beta → Delta.
 * Integra clima/Kp/Bz, Schumann vivo, capas, firmas, delta/psique, muro financiero, disclaimer SNT.
 */
export function FamiliasTab() {
  const layersF = useCallback(() => api.layers(), []);
  const climaF = useCallback(() => api.climaEspacial(80), []);
  const schF = useCallback(() => api.schumannVivo(120), []);
  const deltaF = useCallback(() => api.delta(80), []);
  const teleF = useCallback(() => api.telemetry(), []);
  const firmasF = useCallback(() => api.firmas(), []);
  const botsF = useCallback(() => api.bots(), []);
  const muroF = useCallback(() => api.muro(40), []);
  const precF = useCallback(() => api.precursores(40), []);
  const caF = useCallback(() => api.cimaticaAhora(), []);

  const layers = usePoll(layersF, 20000);
  const clima = usePoll(climaF, 30000);
  const sch = usePoll(schF, 20000);
  const delta = usePoll(deltaF, 30000);
  const tele = usePoll(teleF, 30000);
  const firmas = usePoll(firmasF, 60000);
  const bots = usePoll(botsF, 30000);
  const muro = usePoll(muroF, 30000);
  const prec = usePoll(precF, 20000);
  const ca = usePoll(caF, 30000);

  if (layers.error && clima.error) return <ErrorBanner message={layers.error || clima.error || ""} />;

  const agents = ((layers.data?.agents as Record<string, unknown>[]) || []);
  const byBot = (prefix: string) =>
    agents.filter((a) => String(a.label || a.bot_name || "").toLowerCase().startsWith(prefix));

  const alfaLayers = byBot("alfa");
  const betaLayers = byBot("beta");
  const deltaLayers = agents.filter((a) => {
    const n = String(a.label || a.bot_name || "").toLowerCase();
    return n.startsWith("delta");
  });

  const items = (bots.data?.items as Record<string, unknown>[]) || [];
  const familiaPesos = items.filter((r) => {
    const n = String(r.bot_name || "").toLowerCase();
    return n.startsWith("alfa") || n.startsWith("beta") || n.startsWith("delta");
  });

  const firmasByClase = (Array.isArray(firmas.data?.by_clase) ? firmas.data?.by_clase : []) as Record<
    string,
    unknown
  >[];
  const firmasAlfa = firmasByClase; // by_clase es global; se muestra en Alfa/Modelos

  const climaItems = clima.data?.items || [];
  const climaSpark = [...climaItems]
    .reverse()
    .map((r, i) => ({ i, bz: Number(r.bz_promedio ?? 0), kp: Number(r.kp_max ?? r.kp_promedio ?? 0) }));

  const schItems = sch.data?.items || [];
  const schSpark = [...schItems].reverse().map((r, i) => ({ i, hz: Number(r.schumann_hz ?? 0) }));

  const deltaItems = delta.data?.delta || [];
  const psiItems = delta.data?.psique || [];
  const deltaSpark = [...deltaItems]
    .reverse()
    .map((r, i) => ({ i, score: Number(r.composite_score ?? 0) }));
  const vixSpark = [...psiItems].reverse().map((r, i) => ({ i, vix: Number(r.vix ?? 0) }));

  const cob = useMemo(() => {
    const src = (tele.data?.sources || []).find((s) => String(s.id || s.label || "").toLowerCase().includes("cobert"));
    return src as Record<string, unknown> | undefined;
  }, [tele.data]);

  const volcanSrc = useMemo(() => {
    const src = (tele.data?.sources || []).find((s) => {
      const t = String(s.id || s.label || "").toLowerCase();
      return t.includes("volcan") || t.includes("desgas") || t.includes("so2");
    });
    return src as Record<string, unknown> | undefined;
  }, [tele.data]);

  const muroFin = (muro.data || []).filter((r) => {
    const wall = String(r.wall || r.pared || r.tipo || r.event_type || "").toLowerCase();
    const label = String(r.risk_label || r.detalle || "").toLowerCase();
    return wall.includes("financ") || label.includes("financ") || wall.includes("delta");
  });

  const latestClima = clima.data?.latest || {};
  const latestSch = sch.data?.latest || {};
  const latestDelta = delta.data?.latest_delta || {};
  const latestPsi = delta.data?.latest_psique || {};
  const latestPrec = (prec.data && prec.data[0]) || {};

  return (
    <div className="space-y-10">
      <TabIntro title="Familias (SNT) — Alfa → Beta → Delta">
        <p>
          Tres familias de bots apiladas. Alfa lee clima espacial y cobertura. Beta lee Schumann vivo, cimática y
          desgasificación. Delta lee cross-coupling y psique financiera. El marco SNT es andamiaje matemático, no el
          producto.
        </p>
      </TabIntro>

      {/* ——— ALFA ——— */}
      <section className="space-y-4 rounded-xl border border-border/80 bg-card/30 p-4">
        <h3 className="text-lg font-semibold tracking-tight text-accent">Alfa — clima espacial / cobertura</h3>
        <div className="grid gap-3 md:grid-cols-4">
          <Kpi label="Bz (nT)" value={fmtNum(latestClima.bz_promedio ?? latestPrec.bz_nT)} hint="IMF Bz" />
          <Kpi label="Kp máx" value={fmtNum(latestClima.kp_max ?? latestPrec.kp)} hint="índice geomagnético" />
          <Kpi
            label="Viento"
            value={fmtNum(latestClima.viento_solar_avg ?? latestPrec.viento_km_s)}
            hint="km/s"
          />
          <Kpi
            label="Cobertura"
            value={
              cob
                ? String(((cob.processed as Record<string, unknown>) || {}).value ?? "—").slice(0, 24)
                : "—"
            }
            hint="satelital / telemetría"
          />
        </div>
        {climaSpark.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="text-xs text-muted mb-1">Bz reciente</div>
              <LineSpark data={climaSpark} xKey="i" yKey="bz" height={110} />
            </div>
            <div>
              <div className="text-xs text-muted mb-1">Kp reciente</div>
              <LineSpark data={climaSpark} xKey="i" yKey="kp" height={110} />
            </div>
          </div>
        ) : (
          <EmptyState title="Sin tbl_clima_espacial_raw" detail={clima.data?.caption || clima.error || ""} />
        )}
        <h4 className="text-sm font-medium">Capas alfa1 / alfa2</h4>
        <DataTable
          rows={alfaLayers.length ? alfaLayers : agents.filter((a) => String(a.label || "").toLowerCase().includes("alfa"))}
          empty="Sin señales alfa en layers"
          columns={[
            { key: "label", label: "Agente" },
            { key: "prediccion", label: "Señal" },
            { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
          ]}
        />
        <Caption>
          Firmas alfa viven en TBL_FIRMAS (clase/bot). Clima: {clima.data?.source || "—"}. Precursores Kp/Bz también en
          TBL_PRECURSORES_COSMICOS.
        </Caption>
      </section>

      {/* ——— BETA ——— */}
      <section className="space-y-4 rounded-xl border border-border/80 bg-card/30 p-4">
        <h3 className="text-lg font-semibold tracking-tight text-accent">Beta — Schumann / cimática / volcanes</h3>
        <div className="grid gap-3 md:grid-cols-4">
          <Kpi
            label="Schumann Hz"
            value={fmtNum(latestSch.schumann_hz)}
            hint={`ref 7.83 · Δ ${fmtNum(Number(latestSch.schumann_hz ?? 7.83) - 7.83)}`}
          />
          <Kpi label="Actividad" value={fmtNum(latestSch.schumann_activity, 0)} hint="% WPC vivo" />
          <Kpi
            label="Cimática hits"
            value={String((ca.data?.library as Record<string, unknown> | undefined)?.n_hits ?? "—")}
            hint="biblioteca match"
          />
          <Kpi
            label="Volcán / SO₂"
            value={
              volcanSrc
                ? String(((volcanSrc.processed as Record<string, unknown>) || {}).value ?? "—").slice(0, 24)
                : "vía telemetría"
            }
            hint="desgasificación"
          />
        </div>
        {schSpark.length ? (
          <div>
            <div className="text-xs text-muted mb-1">Schumann vivo (tbl_schumann_vivo)</div>
            <LineSpark data={schSpark} xKey="i" yKey="hz" height={120} />
          </div>
        ) : (
          <EmptyState title="Sin schumann_vivo" detail={sch.data?.caption || sch.error || ""} />
        )}
        <DataTable
          rows={betaLayers}
          empty="Sin señales beta1/beta2 en layers"
          columns={[
            { key: "label", label: "Agente" },
            { key: "prediccion", label: "Señal" },
            { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
          ]}
        />
        <Caption>
          Biblioteca cimática: {String(ca.data?.biblioteca_n ?? "—")} figuras. Match live no entrena. Fuente Schumann:{" "}
          {sch.data?.source || "—"}.
        </Caption>
      </section>

      {/* ——— DELTA ——— */}
      <section className="space-y-4 rounded-xl border border-border/80 bg-card/30 p-4">
        <h3 className="text-lg font-semibold tracking-tight text-accent">Delta — cross + psique financiera</h3>
        <div className="grid gap-3 md:grid-cols-4">
          <Kpi label="Composite" value={fmtNum(latestDelta.composite_score)} hint={String(latestDelta.regime_label || "régimen")} />
          <Kpi label="Conf delta" value={fmtNum(latestDelta.confidence)} hint="cross-coupling" />
          <Kpi label="VIX" value={fmtNum(latestPsi.vix)} hint="volatilidad" />
          <Kpi label="Fear&amp;Greed" value={fmtNum(latestPsi.fear_greed, 0)} hint="sentimiento" />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {deltaSpark.length ? (
            <div>
              <div className="text-xs text-muted mb-1">Delta composite</div>
              <LineSpark data={deltaSpark} xKey="i" yKey="score" height={110} />
            </div>
          ) : (
            <EmptyState title="Sin tbl_delta_cross" detail={delta.data?.caption || ""} />
          )}
          {vixSpark.length ? (
            <div>
              <div className="text-xs text-muted mb-1">VIX (psique)</div>
              <LineSpark data={vixSpark} xKey="i" yKey="vix" height={110} />
            </div>
          ) : (
            <EmptyState title="Sin tbl_psique_financiera" detail="" />
          )}
        </div>
        <DataTable
          rows={deltaLayers}
          empty="Sin señales delta en layers"
          columns={[
            { key: "label", label: "Agente" },
            { key: "prediccion", label: "Señal" },
            { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
          ]}
        />
        <h4 className="text-sm font-medium">Muro financiero (si aparece en eventos)</h4>
        <DataTable
          rows={muroFin.length ? muroFin : (muro.data || []).slice(0, 8)}
          empty="Sin eventos de muro"
          columns={[
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
            { key: "walls_active", label: "Walls" },
            { key: "risk_label", label: "Risk" },
            { key: "wall", label: "Pared", render: (r) => String(r.wall || r.pared || r.tipo || "—") },
          ]}
        />
        <Caption>
          BTC {fmtNum(latestPsi.btc_precio_usd, 0)} USD · dominance {fmtNum(latestPsi.btc_dominance)}. Fuente:{" "}
          {delta.data?.source || "—"}. No es consejo de compra.
        </Caption>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Pesos / asertividad por familia</h4>
        <SimpleBars
          data={familiaPesos.map((r) => ({
            bot: r.bot_name,
            pct: Number(r.asertividad_viva_individual || 0) * 100,
          }))}
          xKey="bot"
          bars={[{ key: "pct", color: "#5e6ad2", name: "% viva" }]}
          height={160}
        />
        {firmasAlfa.length ? (
          <>
            <h4 className="text-sm font-medium">Firmas por clase (global)</h4>
            <SimpleBars
              data={firmasAlfa.map((r) => ({ name: r.clase, n: r.n }))}
              xKey="name"
              bars={[{ key: "n", color: "#5e6ad2" }]}
              height={160}
            />
          </>
        ) : null}
      </section>

      <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted">
        <strong className="text-foreground">Nota SNT (footnote):</strong> Shadow Node Theory describe R(t)=a·t^b
        (satelización). En Sentinel es andamiaje, no el producto. No hay serie SNT persistida en SQLite; Roche /
        equilibrium viven en config. No se interpolan curvas DEMO de Streamlit.
      </div>
    </div>
  );
}
