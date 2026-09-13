import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { SimpleBars, LineSpark, SimplePie } from "@/components/charts/Sparkline";

export function SistemaTab() {
  const fetchSistema = useCallback(async () => {
    const [overview, familias, omega, loki, padre] = await Promise.all([
      api.system.overview(),
      api.system.familias(),
      api.system.omega(),
      api.system.loki(),
      api.system.padre(),
    ]);
    return { overview, familias, omega, loki, padre };
  }, []);

  const { data, loading, error } = usePoll(fetchSistema, 30000);

  const overview = data?.overview;
  const familias = data?.familias;
  const omega = data?.omega;
  const loki = data?.loki;
  const padre = data?.padre;

  const kpis = useMemo(() => [
    { label: "DB Size (MB)", value: overview?.db_size_mb?.toString() ?? "—" },
    { label: "Total Sismos", value: overview?.quakes_total?.toLocaleString() ?? "—" },
    { label: "Ciclos 24h", value: overview?.cycles_24h?.toString() ?? "—" },
    { label: "Latencia Promedio (ms)", value: overview?.avg_latency_ms?.toFixed(1) ?? "—" },
    { label: "Alfa Score", value: familias?.alfa?.score ? `${(familias.alfa.score * 100).toFixed(1)}%` : "—", color: familias?.alfa?.score && familias.alfa.score > 0.7 ? "green" : "yellow" },
    { label: "Beta Score", value: familias?.beta?.score ? `${(familias.beta.score * 100).toFixed(1)}%` : "—", color: familias?.beta?.score && familias.beta.score > 0.7 ? "green" : "yellow" },
    { label: "Delta Score", value: familias?.delta?.score ? `${(familias.delta.score * 100).toFixed(1)}%` : "—", color: familias?.delta?.score && familias.delta.score > 0.7 ? "green" : "yellow" },
    { label: "Omega Score", value: omega?.score ? `${(omega.score * 100).toFixed(1)}%` : "—", color: omega?.score && omega.score > 0.7 ? "green" : "yellow" },
    { label: "Loki Score", value: loki?.score ? `${(loki.score * 100).toFixed(1)}%` : "—", color: loki?.score && loki.score > 0.7 ? "green" : "yellow" },
    { label: "Padre Decisión", value: padre?.decision ?? "—", color: padre?.decision === "ALERTA" ? "red" : padre?.decision === "OBSERVAR" ? "yellow" : "green" },
  ], [overview, familias, omega, loki, padre]);

  if (loading) return <div className="p-4 text-center text-gray-400">Cargando sistema...</div>;
  if (error) return <div className="p-4 text-center text-red-400">Error: {String(error)}</div>;

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-10 gap-3">
        {kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Familias SNT — Detalle</h3>
          <DataTable
            rows={familias ? [
              { familia: "ALFA", score: familias.alfa.score, confianza: familias.alfa.confianza, componentes: JSON.stringify(familias.alfa.componentes) },
              { familia: "BETA", score: familias.beta.score, confianza: familias.beta.confianza, componentes: JSON.stringify(familias.beta.componentes) },
              { familia: "DELTA", score: familias.delta.score, confianza: familias.delta.confianza, componentes: JSON.stringify(familias.delta.componentes) },
            ] : []}
            columns={[
              { key: "familia", label: "Familia" },
              { key: "score", label: "Score", render: (_, v: unknown) => `${(Number(v) * 100).toFixed(1)}%` },
              { key: "confianza", label: "Confianza", render: (_, v: unknown) => `${(Number(v) * 100).toFixed(1)}%` },
              { key: "componentes", label: "Componentes" },
            ]}
            pageSize={10}
          />
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">OMEGA — Integrador</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono text-xl">{omega?.score ? `${(omega.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Phi (Φ)</span><span className="font-mono">{omega?.phi ? `${omega.phi.toFixed(3)}` : "—"}</span></div>
            <div className="flex justify-between"><span>Decisión</span><span className="font-bold">{omega?.decision ?? "—"}</span></div>
            <SimplePie data={Object.entries(omega?.componentes ?? {}).map(([k, v]) => ({ name: k, value: Number(v), color: `hsl(${Math.random() * 360}, 70%, 50%)` }))} height={180} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">LOKI — Campo Unificado</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono text-xl">{loki?.score ? `${(loki.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Dim. Fractal</span><span className="font-mono">{loki?.dimension_fractal ? `${loki.dimension_fractal.toFixed(3)}` : "—"}</span></div>
            <div className="flex justify-between"><span>Prior Bayes</span><span className="font-mono">{loki?.bayesian_prior ? `${(loki.bayesian_prior * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Posterior Bayes</span><span className="font-mono">{loki?.bayesian_posterior ? `${(loki.bayesian_posterior * 100).toFixed(1)}%` : "—"}</span></div>
            <SimpleBars data={Object.entries(loki?.componentes ?? {}).map(([k, v]) => ({ key: k, value: Number(v) }))} xKey="key" yKey="value" color="#8b5cf6" height={200} />
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">PADRE — Juez Final</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Decisión</span><span className="font-bold text-xl">{padre?.decision ?? "—"}</span></div>
            <div className="flex justify-between"><span>Probabilidad</span><span className="font-mono">{padre?.probabilidad ? `${(padre.probabilidad * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Regla Aplicada</span><span className="font-mono text-xs">{padre?.regla_aplicada ?? "—"}</span></div>
            <SimplePie data={Object.entries(padre?.detalles ?? {}).map(([k, v]) => ({ name: k, value: Number(v), color: `hsl(${Math.random() * 360}, 70%, 50%)` }))} height={180} />
          </div>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Resumen del Sistema</h3>
        <DataTable
          rows={overview ? [{
            metrica: "Tamaño DB (MB)",
            valor: overview.db_size_mb.toString(),
          }, {
            metrica: "Total Sismos",
            valor: overview.quakes_total.toLocaleString(),
          }, {
            metrica: "Ciclos 24h",
            valor: overview.cycles_24h.toString(),
          }, {
            metrica: "Latencia Promedio (ms)",
            valor: overview.avg_latency_ms.toFixed(1),
          }] : []}
          columns={[
            { key: "metrica", label: "Métrica" },
            { key: "valor", label: "Valor" },
          ]}
          pageSize={10}
        />
      </div>
    </div>
  );
}