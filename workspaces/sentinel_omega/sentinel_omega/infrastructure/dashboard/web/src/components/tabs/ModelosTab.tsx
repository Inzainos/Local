import { useCallback } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { TabIntro, Caption } from "@/components/TabIntro";
import { LineSpark, SimpleBars } from "@/components/charts/Sparkline";
import { EmptyState, ErrorBanner } from "@/components/EmptyState";
import { fmtNum, fmtTs } from "@/lib/utils";

function pct(v: unknown) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

/**
 * Tab 5 — Modelos: curvas aprendizaje, pesos/sesgo, firmas, top-5 ACIERTO/FALLO, placeholder ONNX.
 */
export function ModelosTab() {
  const botsF = useCallback(() => api.bots(), []);
  const sesgoF = useCallback(() => api.sesgo(), []);
  const learnF = useCallback(() => api.aprendizaje(), []);
  const firmasF = useCallback(() => api.firmas(), []);
  const acF = useCallback(() => api.aciertos(200), []);
  const juezF = useCallback(() => api.juez(200, "viva"), []);

  const bots = usePoll(botsF, 30000);
  const sesgo = usePoll(sesgoF, 60000);
  const learn = usePoll(learnF, 60000);
  const firmas = usePoll(firmasF, 60000);
  const ac = usePoll(acF, 30000);
  const juez = usePoll(juezF, 20000);

  if (bots.error) return <ErrorBanner message={bots.error} />;
  if (bots.loading && !bots.data) return <EmptyState title="Cargando Modelos…" />;

  const items = (bots.data?.items as Record<string, unknown>[]) || [];
  const sesgoItems = (sesgo.data?.items as Record<string, unknown>[]) || [];
  const series = learn.data?.series || {};
  const botsNames = Object.keys(series);
  const merged: Record<string, unknown>[] = [];
  if (botsNames.length) {
    const days = Array.from(new Set(botsNames.flatMap((b) => series[b].map((p) => p.dia)))).sort();
    for (const d of days) {
      const row: Record<string, unknown> = { dia: d };
      for (const bname of botsNames) {
        const pt = series[bname].find((p) => p.dia === d);
        row[bname] = pt?.asertividad_cum != null ? Number(pt.asertividad_cum) * 100 : null;
      }
      merged.push(row);
    }
  }

  const recent = (ac.data?.recent as Record<string, unknown>[]) || (juez.data?.items || []);
  const topAcierto = recent.filter((r) => String(r.resultado || "").toUpperCase() === "ACIERTO").slice(0, 5);
  const topFallo = recent.filter((r) => String(r.resultado || "").toUpperCase() === "FALLO").slice(0, 5);
  const summary = ac.data?.summary || {};
  const byClase = (Array.isArray(firmas.data?.by_clase) ? firmas.data?.by_clase : []) as Record<
    string,
    unknown
  >[];

  return (
    <div className="space-y-6">
      <TabIntro title="Modelos — aprendizaje, pesos y veredictos">
        <p>
          Curvas honestas del Juez (fase viva), pesos snapshot, sesgo insample vs causal, firmas por clase y top-5
          recientes de ACIERTO / FALLO. ONNX existe en el código del core pero no hay tabla de métricas en el dashboard:
          se muestra un placeholder honesto.
        </p>
      </TabIntro>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi label="VIVA GLOBAL" value={pct(bots.data?.asertividad_viva_global)} hint="aciertos/(aciertos+fallos)" />
        <Kpi
          label="VIVA PADRE"
          value={pct((bots.data?.padre as Record<string, unknown> | undefined)?.asertividad_viva_individual)}
          hint="quien puede avisar"
        />
        <Kpi label="ACIERTOS Σ" value={String(summary.aciertos ?? bots.data?.aciertos_total ?? "—")} accent="#10b981" />
        <Kpi label="FALLOS Σ" value={String(summary.fallos ?? bots.data?.fallos_total ?? "—")} accent="#ff1744" />
      </div>

      <SimpleBars
        data={items.map((r) => ({ bot: r.bot_name, aciertos: Number(r.aciertos || 0), fallos: Number(r.fallos || 0) }))}
        xKey="bot"
        bars={[
          { key: "aciertos", color: "#10b981", name: "aciertos" },
          { key: "fallos", color: "#ff1744", name: "fallos" },
        ]}
      />
      <DataTable
        rows={items}
        columns={[
          { key: "bot_name", label: "Bot" },
          { key: "peso", label: "Peso", render: (r) => fmtNum(r.peso) },
          { key: "aciertos", label: "Aciertos" },
          { key: "fallos", label: "Fallos" },
          { key: "asertividad_viva_individual", label: "Viva %", render: (r) => pct(r.asertividad_viva_individual) },
          { key: "updated_at", label: "Snapshot" },
        ]}
      />

      <h4 className="text-sm font-medium">Sesgo insample vs causal</h4>
      {sesgoItems.length ? (
        <SimpleBars
          data={sesgoItems.map((r) => ({
            bot: r.bot,
            insample: Number(r.recon_insample || 0) * 100,
            causal: Number(r.recon_causal || 0) * 100,
          }))}
          xKey="bot"
          bars={[
            { key: "insample", color: "#5e6ad2", name: "insample" },
            { key: "causal", color: "#ffc107", name: "causal" },
          ]}
        />
      ) : (
        <EmptyState title="Sin tbl_sesgo_aprendizaje" detail="En DEV a menudo no está la tabla de train." />
      )}
      <DataTable
        rows={sesgoItems}
        empty="Sin sesgo"
        columns={[
          { key: "bot", label: "Bot" },
          { key: "n", label: "n" },
          { key: "recon_insample", label: "Insample", render: (r) => fmtNum(r.recon_insample) },
          { key: "recon_causal", label: "Causal", render: (r) => fmtNum(r.recon_causal) },
          { key: "sesgo", label: "Sesgo", render: (r) => fmtNum(r.sesgo) },
        ]}
      />

      <h4 className="text-sm font-medium">Curvas de aprendizaje (Juez viva, diaria)</h4>
      <Caption>
        {learn.data?.caption || "Sin interpolar."} Fuente: {String(learn.data?.source || "—")}.
      </Caption>
      {learn.data?.present && merged.length ? (
        <div className="space-y-2">
          {botsNames.map((name) => (
            <div key={name}>
              <div className="text-xs text-muted">{name}</div>
              <LineSpark data={merged.map((r) => ({ dia: r.dia, y: r[name] }))} xKey="dia" yKey="y" height={110} />
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="no hay historial por ciclo aún" detail="Cuando el Juez viva tenga días, aparecen aquí." />
      )}

      {byClase.length ? (
        <>
          <h4 className="text-sm font-medium">Firmas por clase</h4>
          <SimpleBars
            data={byClase.map((r) => ({ name: r.clase, n: r.n }))}
            xKey="name"
            bars={[{ key: "n", color: "#5e6ad2" }]}
          />
        </>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-success">Top-5 ACIERTO recientes</h4>
          <DataTable
            rows={topAcierto}
            empty="Sin ACIERTO en la ventana reciente"
            columns={[
              { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
              { key: "bot_name", label: "Bot" },
              { key: "prediccion", label: "Pred" },
              { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            ]}
          />
        </div>
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-danger">Top-5 FALLO recientes</h4>
          <DataTable
            rows={topFallo}
            empty="Sin FALLO en la ventana reciente"
            columns={[
              { key: "timestamp", label: "Tiempo", render: (r) => fmtTs(r.timestamp) },
              { key: "bot_name", label: "Bot" },
              { key: "prediccion", label: "Pred" },
              { key: "confianza", label: "Conf", render: (r) => fmtNum(r.confianza) },
            ]}
          />
        </div>
      </div>

      <div className="rounded-lg border border-dashed border-border bg-card/20 px-4 py-4">
        <div className="text-sm font-medium">ONNX — placeholder</div>
        <p className="mt-2 text-xs text-muted">
          Existe código en <span className="mono">core/onnx_engine.py</span> y{" "}
          <span className="mono">models/train_onnx_from_db.py</span>, pero <strong>no hay tabla SQLite de métricas
          ONNX</strong> expuesta al dashboard. Cuando se persistan métricas reales (loss, AUC, path del .onnx),
          aparecerán aquí citando la tabla. No se inventan curvas.
        </p>
      </div>
    </div>
  );
}
