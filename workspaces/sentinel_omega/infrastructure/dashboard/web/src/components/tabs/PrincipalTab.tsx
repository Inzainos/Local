import { useCallback, useMemo } from "react";
import { api, type Overview } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { AskBox } from "@/components/AskBox";
import { TelemetryStrip } from "@/components/TelemetryStrip";
import { TabIntro, Caption } from "@/components/TabIntro";
import { DataTable } from "@/components/DataTable";
import { SimpleBars, LineSpark, SimplePie } from "@/components/charts/Sparkline";
import { Heatmap } from "@/components/charts/Heatmap";
import { Map2D } from "@/components/maps/Map2D";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs, riskColor } from "@/lib/utils";

/**
 * Tab 0 — Principal: estado, telemetría, AskBox, mini mapa, cimática ahora,
 * top alertas, mini heatmap, pie de riesgo, spark fantasma, reportes/telegram.
 */
export function PrincipalTab() {
  const ovF = useCallback(() => api.overview(), []);
  const alF = useCallback(() => api.alertas(20), []);
  const ciF = useCallback(() => api.cimatica(30), []);
  const caF = useCallback(() => api.cimaticaAhora(), []);
  const nF = useCallback(() => api.nodos(), []);
  const sF = useCallback(() => api.sismos(4.5, 40), []);
  const cycF = useCallback(() => api.ciclos(40), []);
  const corrF = useCallback(() => api.correlaciones(), []);
  const repF = useCallback(() => api.reportes(), []);
  const tgF = useCallback(() => api.telegramStatus(), []);
  const precF = useCallback(() => api.precursores(40), []);

  const ov = usePoll<Overview>(ovF, 20000);
  const al = usePoll(alF, 20000);
  const ci = usePoll(ciF, 30000);
  const ca = usePoll(caF, 30000);
  const n = usePoll(nF, 30000);
  const s = usePoll(sF, 30000);
  const cyc = usePoll(cycF, 20000);
  const corr = usePoll(corrF, 60000);
  const rep = usePoll(repF, 60000);
  const tg = usePoll(tgF, 60000);
  const prec = usePoll(precF, 20000);

  if (ov.error) return <ErrorBanner message={ov.error} />;
  if (ov.loading && !ov.data) return <EmptyState title="Cargando Principal…" />;

  const data = ov.data;
  const risk = Object.entries(data?.risk_distribution || {}).map(([name, value]) => ({
    name,
    value: Number(value),
  }));
  const nivel = data?.fantasma?.nivel_riesgo || "";
  const calm =
    !["HIGH", "CRITICAL"].includes(String(nivel).toUpperCase()) && !data?.muro?.muro_breach;

  const nodes = useMemo(
    () =>
      (n.data || [])
        .map((nd) => ({
          lat: Number(nd.lat),
          lon: Number(nd.lon),
          tipo: String(nd.tipo || ""),
          label: String(nd.nombre || ""),
          highlight:
            String(nd.nombre || "").toLowerCase().includes("tlaxcala") && String(nd.tipo) === "real",
        }))
        .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon)),
    [n.data],
  );
  const quakes = (s.data?.items || [])
    .map((q) => ({
      lat: Number(q.lat),
      lon: Number(q.lon),
      mag: Number(q.magnitude),
      label: String(q.region || ""),
    }))
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));

  const fantasmaSpark = [...(cyc.data || [])]
    .reverse()
    .map((r, i) => ({ i, y: Number(r.fantasma ?? 0) }));

  const pieAmbito = (ci.data?.by_ambito || []).map((r) => ({
    name: String(r.ambito || "—"),
    value: Number(r.n || 0),
  }));

  const geo = ((al.data?.geo_alerts as Record<string, unknown>[]) || []).slice(0, 5);
  const breaches = ((al.data?.muro_breaches as Record<string, unknown>[]) || []).slice(0, 5);
  const hot = ((al.data?.hot_fantasma as Record<string, unknown>[]) || []).slice(0, 5);
  const topAlertas = [
    ...geo.map((r) => ({ ...r, _kind: "geo" })),
    ...breaches.map((r) => ({ ...r, _kind: "muro" })),
    ...hot.map((r) => ({ ...r, _kind: "fantasma" })),
  ].slice(0, 8);

  const padre = corr.data?.padre;
  const corrMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of padre?.items || []) {
      m.set(`${r.patron}|${r.event_class}`, Number(r.fuerza || 0));
    }
    return m;
  }, [padre]);

  const caData = ca.data || {};
  const tgData = tg.data || {};
  const repFiles = rep.data?.files || [];

  return (
    <div className="space-y-6">
      <TabIntro title="Principal — pulso del sistema">
        <p>
          Vista unificada: Fantasma, Muro, telemetría, cimática en vivo, alertas top y un mini mapa. Los números
          salen de SQLite en modo lectura. No es un juguete de predicción ni un consejo de compra.
        </p>
        <p>
          {calm
            ? "Lectura actual: calma relativa. No hay que llamar a nadie solo por este tablero."
            : "Lectura actual: el sistema está inquieto (riesgo alto o Muro roto). Revise alertas abajo y avise a quien corresponda."}
        </p>
      </TabIntro>

      <div className="grid gap-3 md:grid-cols-5">
        <Kpi
          label="FANTASMA"
          value={
            data?.fantasma?.value != null
              ? `${fmtNum(data.fantasma.value)} ${data.fantasma.nivel_riesgo ?? ""}`
              : "—"
          }
          accent={riskColor(data?.fantasma?.nivel_riesgo)}
          hint="índice de riesgo cósmico (no es un sismo)"
        />
        <Kpi
          label="MURO"
          value={`${data?.muro?.walls_active ?? "—"} / 5`}
          hint={data?.muro?.muro_breach ? "BREACH: 3+ paredes activas" : "sin rotura"}
          accent={data?.muro?.muro_breach ? "#ff1744" : "#10b981"}
        />
        <Kpi label="NODOS" value={data?.counts?.nodos ?? "—"} hint="125 puntos de topología" />
        <Kpi label="SISMOS ≥4.5" value={data?.counts?.sismos_m45 ?? "—"} hint="umbral de alerta del Padre" />
        <Kpi
          label="ALERTAS EN CICLOS"
          value={
            data?.cycle_alert_rate?.alert_rate != null
              ? `${(Number(data.cycle_alert_rate.alert_rate) * 100).toFixed(1)}%`
              : "—"
          }
          hint="cuántos ciclos salieron en alerta"
        />
      </div>
      <Caption>
        LOW &lt;5 calma · MODERATE 5–15 atención · HIGH 15–30 avisar · CRITICAL ≥30 protocolo. El Muro se rompe con 3
        de 5 paredes.
      </Caption>

      <TelemetryStrip />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Fantasma (últimos ciclos)</h4>
          {fantasmaSpark.length ? (
            <LineSpark data={fantasmaSpark} xKey="i" yKey="y" height={120} />
          ) : (
            <Caption>Sin ciclos para sparkline.</Caption>
          )}
        </div>
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Distribución de riesgo</h4>
          {risk.length ? (
            <SimplePie data={risk} height={160} />
          ) : (
            <Caption>Sin distribución de riesgo en esta DB.</Caption>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Mini mapa — nodos + sismos ≥4.5</h4>
          <Map2D nodes={nodes} quakes={quakes} highlight={{ lat: 19.31, lon: -98.23, label: "Tlaxcala" }} />
        </div>
        <div className="space-y-3">
          <h4 className="text-sm font-medium">Cimática ahora</h4>
          <div className="grid gap-2 grid-cols-3">
            <Kpi label="BIBLIOTECA" value={String(caData.biblioteca_n ?? "—")} hint="figuras históricas" />
            <Kpi label="PATRONES" value={String(ci.data?.total ?? caData.patrones_n ?? "—")} hint="tbl_cimatica_patrones" />
            <Kpi
              label="HITS"
              value={String((caData.library as Record<string, unknown> | undefined)?.n_hits ?? "—")}
              hint="similitud live"
            />
          </div>
          {pieAmbito.length ? <SimplePie data={pieAmbito} height={140} /> : null}
          <Caption>
            Clave actual: {String(caData.current_clave || "—")}.{" "}
            {String(caData.caption || "Lookup live vs biblioteca; sin entrenamiento.")}
          </Caption>
        </div>
      </div>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Top alertas</h4>
        <DataTable
          rows={topAlertas}
          empty="Sin alertas activas — todo en verde según umbrales."
          columns={[
            { key: "_kind", label: "Tipo" },
            { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
            {
              key: "fantasma",
              label: "Fantasma",
              render: (r) => (r.fantasma != null ? fmtNum(r.fantasma) : "—"),
            },
            {
              key: "nivel_riesgo",
              label: "Riesgo",
              render: (r) => String(r.nivel_riesgo || r.risk_label || r.geo_signal || "—"),
            },
          ]}
        />
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-medium">Mini heatmap correlaciones (Padre)</h4>
        {padre?.present && (padre.patrones?.length || 0) > 0 ? (
          <Heatmap
            rows={(padre.patrones || []).slice(0, 8)}
            cols={(padre.event_classes || []).slice(0, 8)}
            get={(r, c) => corrMap.get(`${r}|${c}`) ?? null}
            caption="Recorte top patrones×eventos. Tablas vacías en DEV = sin train aún."
          />
        ) : (
          <EmptyState
            title="Sin correlaciones padre en esta DB"
            detail="tbl_correlaciones_padre vacía hasta re-entrenar. No se inventan celdas."
          />
        )}
      </section>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-card/40 px-3 py-3 text-xs">
          <div className="font-medium text-sm mb-1">Reportes (estado/)</div>
          {rep.data?.present ? (
            <ul className="space-y-0.5 text-muted">
              {repFiles.slice(0, 5).map((f) => (
                <li key={f.name} className="mono">
                  {f.name} · {(f.bytes / 1024).toFixed(1)} KB
                </li>
              ))}
              {!repFiles.length ? <li>Carpeta presente, sin archivos.</li> : null}
            </ul>
          ) : (
            <p className="text-muted">Sin carpeta estado/ en este árbol.</p>
          )}
        </div>
        <div className="rounded-lg border border-border bg-card/40 px-3 py-3 text-xs">
          <div className="font-medium text-sm mb-1">Telegram</div>
          <p className={tgData.configured ? "text-success" : "text-warning"}>
            {tgData.configured ? "Configurado" : "No configurado / dry-run"}
          </p>
          <p className="text-muted mt-1">
            token={String(tgData.has_token)} · chat={String(tgData.has_chat_id)} · dry_run=
            {String(tgData.dry_run)} · cooldown={String(tgData.cooldown_s ?? "—")}s
          </p>
          <Caption>No se muestran secretos. Solo banderas de configuración.</Caption>
        </div>
      </div>

      {prec.data?.length ? (
        <div>
          <h4 className="mb-1 text-sm font-medium">Precursores recientes (Kp / Bz)</h4>
          <SimpleBars
            data={[...prec.data]
              .slice(0, 20)
              .reverse()
              .map((r, i) => ({ i: String(i), kp: Number(r.kp || 0) }))}
            xKey="i"
            bars={[{ key: "kp", color: "#5e6ad2", name: "Kp" }]}
            height={140}
          />
        </div>
      ) : null}

      <AskBox />
    </div>
  );
}
