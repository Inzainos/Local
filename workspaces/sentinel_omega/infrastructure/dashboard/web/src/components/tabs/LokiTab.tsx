import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { TabIntro, Caption } from "@/components/TabIntro";
import { Map2D } from "@/components/maps/Map2D";
import { Globe3D } from "@/components/maps/Globe3D";
import { LineSpark } from "@/components/charts/Sparkline";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs, riskColor } from "@/lib/utils";

/**
 * Tab 3 — Loki: Campo Unificado (Map2D+Globe3D) + /api/consenso + layers loki + Tlaxcala.
 */
export function LokiTab() {
  const uF = useCallback(() => api.unificado(), []);
  const nF = useCallback(() => api.nodos(), []);
  const sF = useCallback(() => api.sismos(4.5, 80), []);
  const cF = useCallback(() => api.consenso(40), []);
  const lF = useCallback(() => api.layers(), []);

  const u = usePoll(uF, 20000);
  const n = usePoll(nF, 30000);
  const s = usePoll(sF, 30000);
  const c = usePoll(cF, 20000);
  const layers = usePoll(lF, 20000);

  if (u.error) return <ErrorBanner message={u.error} />;
  if (u.loading && !u.data) return <EmptyState title="Cargando Loki / Campo Unificado…" />;

  const d = u.data || {};
  const fant = (d.fantasma || {}) as Record<string, unknown>;
  const muro = (d.muro || {}) as Record<string, unknown>;
  const tlax = (d.tlaxcala || {}) as Record<string, unknown>;
  const row = (tlax.row || {}) as Record<string, unknown>;
  const lat = Number(row.lat ?? tlax.spec_lat ?? 19.31);
  const lon = Number(row.lon ?? tlax.spec_lon ?? -98.23);

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

  const agents = ((layers.data?.agents as Record<string, unknown>[]) || []);
  const lokiLayer = agents.find((a) => String(a.label || a.bot_name || "").toLowerCase().includes("loki"));

  const cycles = ((c.data?.cycles as Record<string, unknown>[]) || []);
  const fantasmaSeries = [...cycles]
    .reverse()
    .map((r, i) => ({ i, y: Number(r.fantasma ?? 0) }));
  const botsConsenso = ((c.data?.bots as Record<string, unknown>[]) || []);

  const nivel = String(fant.nivel_riesgo || "—");
  const vector = muro.muro_breach
    ? `El Muro está roto (${muro.walls_active}/5). Fantasma ${fmtNum(fant.value)} (${nivel}). Esto pide revisión humana.`
    : `Consenso: Fantasma ${fmtNum(fant.value)} (${nivel}), Muro ${muro.walls_active ?? "—"}/5. Motor unificado aún teórico + sensores vivos.`;

  return (
    <div className="space-y-4">
      <TabIntro title="Loki — Campo Unificado Fractal-Bayesiano">
        <p>
          Loki observa el campo unificado: geometría (φ), Schumann, nodos y consenso jerárquico. Nodo de observación:
          Tlaxcala 19.31 N, 98.23 W (node_id=11 en topología).
        </p>
        <p>Calma: sin breach y Loki en silencio. Acción: breach + consenso geo_signal — avisar, no apostar.</p>
      </TabIntro>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi label="φ" value={fmtNum(d.phi, 3)} hint="constante, no dato vivo" />
        <Kpi
          label="SCHUMANN"
          value={fant.schumann_hz != null ? `${fmtNum(fant.schumann_hz)} Hz` : "—"}
          hint={`vs 7.83 · Δ ${fmtNum(d.schumann_delta)}`}
        />
        <Kpi
          label="FANTASMA"
          value={fmtNum(fant.value)}
          accent={riskColor(String(fant.nivel_riesgo))}
          hint={nivel}
        />
        <Kpi label="TLAXCALA" value={`${fmtNum(lat, 2)} N, ${fmtNum(Math.abs(lon), 2)} W`} hint={String(row.nombre || "spec")} />
      </div>

      <div className="rounded-lg border border-accent/40 bg-accent/10 px-4 py-3 text-sm">{vector}</div>

      <div className="rounded-lg border border-border px-4 py-3">
        <div className="text-xs text-muted">Capa Loki (última predicción viva)</div>
        <div className="text-lg font-semibold">{String(lokiLayer?.prediccion || "SIN_DATOS")}</div>
        <div className="text-xs text-muted">
          conf {fmtNum(lokiLayer?.confianza)} · {fmtTs(lokiLayer?.timestamp)}
        </div>
        <Caption>Nota: Loki suele tener pocos aciertos en Juez; no se inventa historial.</Caption>
      </div>

      <h4 className="text-sm font-medium">Consenso — timeline de ciclos</h4>
      {fantasmaSeries.length ? (
        <LineSpark data={fantasmaSeries} xKey="i" yKey="y" height={120} />
      ) : (
        <EmptyState title="Sin ciclos en /api/consenso" detail={String(c.error || "")} />
      )}
      <DataTable
        rows={cycles.slice(0, 20)}
        empty="Sin ciclos"
        columns={[
          { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
          { key: "fantasma", label: "Fantasma", render: (r) => fmtNum(r.fantasma) },
          { key: "nivel_riesgo", label: "Riesgo" },
          { key: "muro_walls_active", label: "Muro" },
          { key: "geo_signal", label: "Geo" },
          { key: "geo_consensus", label: "Consenso" },
        ]}
      />
      <DataTable
        rows={botsConsenso}
        empty="Sin pesos en consenso"
        columns={[
          { key: "bot_name", label: "Bot" },
          { key: "peso", label: "Peso", render: (r) => fmtNum(r.peso) },
          {
            key: "asertividad_viva",
            label: "Viva %",
            render: (r) =>
              r.asertividad_viva != null ? `${(Number(r.asertividad_viva) * 100).toFixed(1)}%` : "—",
          },
          { key: "n", label: "n" },
        ]}
      />
      <Caption>{String(c.data?.caption || d.caption || "")}</Caption>

      <Map2D nodes={nodes} quakes={quakes} highlight={{ lat, lon, label: "Tlaxcala" }} />
      <Globe3D nodes={nodes} quakes={quakes} />
    </div>
  );
}
