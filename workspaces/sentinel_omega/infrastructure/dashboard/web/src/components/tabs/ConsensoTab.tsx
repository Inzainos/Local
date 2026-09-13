import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { SimpleBars, LineSpark, SimplePie } from "@/components/charts/Sparkline";

export function ConsensoTab() {
  const fetchConsenso = useCallback(async () => {
    const [familias, omega, loki, padre, historial] = await Promise.all([
      api.system.familias(),
      api.system.omega(),
      api.system.loki(),
      api.system.padre(),
      api.consenso.historial(100),
    ]);
    return { familias, omega, loki, padre, historial };
  }, []);

  const { data, loading, error } = usePoll(fetchConsenso, 30000);

  const familias = data?.familias;
  const omega = data?.omega;
  const loki = data?.loki;
  const padre = data?.padre;
  const historial = data?.historial?.historial ?? [];

  const kpis = useMemo(() => [
    { label: "Alfa Score", value: familias?.alfa?.score ? `${(familias.alfa.score * 100).toFixed(1)}%` : "—", color: familias?.alfa?.score && familias.alfa.score > 0.7 ? "green" : "yellow" },
    { label: "Beta Score", value: familias?.beta?.score ? `${(familias.beta.score * 100).toFixed(1)}%` : "—", color: familias?.beta?.score && familias.beta.score > 0.7 ? "green" : "yellow" },
    { label: "Delta Score", value: familias?.delta?.score ? `${(familias.delta.score * 100).toFixed(1)}%` : "—", color: familias?.delta?.score && familias.delta.score > 0.7 ? "green" : "yellow" },
    { label: "Omega Score", value: omega?.score ? `${(omega.score * 100).toFixed(1)}%` : "—", color: omega?.score && omega.score > 0.7 ? "green" : "yellow" },
    { label: "Omega Phi (Φ)", value: omega?.phi ? `${omega.phi.toFixed(3)}` : "—" },
    { label: "Loki Score", value: loki?.score ? `${(loki.score * 100).toFixed(1)}%` : "—", color: loki?.score && loki.score > 0.7 ? "green" : "yellow" },
    { label: "Padre Decisión", value: padre?.decision ?? "—", color: padre?.decision === "ALERTA" ? "red" : padre?.decision === "OBSERVAR" ? "yellow" : "green" },
  ], [familias, omega, loki, padre]);

  if (loading) return <div className="p-4 text-center text-gray-400">Cargando consenso...</div>;
  if (error) return <div className="p-4 text-center text-red-400">Error: {String(error)}</div>;

  const renderPct = (row: Record<string, unknown>, key: string) => `${(Number(row[key]) * 100).toFixed(1)}%`;
  const renderFixed = (row: Record<string, unknown>, key: string, digits = 3) => Number(row[key]).toFixed(digits);
  const renderDecision = (row: Record<string, unknown>, key: string) => String(row[key] ?? "—");

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Familia ALFA (SNT)</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono">{familias?.alfa?.score ? `${(familias.alfa.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Confianza</span><span className="font-mono">{familias?.alfa?.confianza ? `${(familias.alfa.confianza * 100).toFixed(1)}%` : "—"}</span></div>
            <SimpleBars data={Object.entries(familias?.alfa?.componentes ?? {}).map(([k, v]) => ({ key: k, value: Number(v) }))} xKey="key" yKey="value" color="#3b82f6" height={150} />
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Familia BETA (SNT)</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono">{familias?.beta?.score ? `${(familias.beta.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Confianza</span><span className="font-mono">{familias?.beta?.confianza ? `${(familias.beta.confianza * 100).toFixed(1)}%` : "—"}</span></div>
            <SimpleBars data={Object.entries(familias?.beta?.componentes ?? {}).map(([k, v]) => ({ key: k, value: Number(v) }))} xKey="key" yKey="value" color="#10b981" height={150} />
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Familia DELTA (SNT)</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono">{familias?.delta?.score ? `${(familias.delta.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Confianza</span><span className="font-mono">{familias?.delta?.confianza ? `${(familias.delta.confianza * 100).toFixed(1)}%` : "—"}</span></div>
            <SimpleBars data={Object.entries(familias?.delta?.componentes ?? {}).map(([k, v]) => ({ key: k, value: Number(v) }))} xKey="key" yKey="value" color="#f59e0b" height={150} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">OMEGA — Integrador de Consenso</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono text-xl">{omega?.score ? `${(omega.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Phi (Φ)</span><span className="font-mono">{omega?.phi ? `${omega.phi.toFixed(3)}` : "—"}</span></div>
            <div className="flex justify-between"><span>Decisión</span><span className="font-bold">{omega?.decision ?? "—"}</span></div>
            <SimplePie data={Object.entries(omega?.componentes ?? {}).map(([k, v]) => ({ name: k, value: Number(v), color: `hsl(${Math.random() * 360}, 70%, 50%)` }))} height={180} />
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">LOKI — Campo Unificado Fractal-Bayesiano</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Score</span><span className="font-mono text-xl">{loki?.score ? `${(loki.score * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Dim. Fractal</span><span className="font-mono">{loki?.dimension_fractal ? `${loki.dimension_fractal.toFixed(3)}` : "—"}</span></div>
            <div className="flex justify-between"><span>Prior Bayes</span><span className="font-mono">{loki?.bayesian_prior ? `${(loki.bayesian_prior * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Posterior Bayes</span><span className="font-mono">{loki?.bayesian_posterior ? `${(loki.bayesian_posterior * 100).toFixed(1)}%` : "—"}</span></div>
            <SimpleBars data={Object.entries(loki?.componentes ?? {}).map(([k, v]) => ({ key: k, value: Number(v) }))} xKey="key" yKey="value" color="#8b5cf6" height={150} />
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">PADRE — Juez Final</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span>Decisión</span><span className="font-bold text-xl">{padre?.decision ?? "—"}</span></div>
            <div className="flex justify-between"><span>Probabilidad</span><span className="font-mono">{padre?.probabilidad ? `${(padre.probabilidad * 100).toFixed(1)}%` : "—"}</span></div>
            <div className="flex justify-between"><span>Regla</span><span className="font-mono text-xs">{padre?.regla_aplicada ?? "—"}</span></div>
            <SimplePie data={Object.entries(padre?.detalles ?? {}).map(([k, v]) => ({ name: k, value: Number(v), color: `hsl(${Math.random() * 360}, 70%, 50%)` }))} height={180} />
          </div>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Historial de Consenso — Últimas 100 Decisiones</h3>
        <DataTable
          rows={historial as Record<string, unknown>[]}
          columns={[
            { key: "timestamp", label: "Timestamp" },
            { key: "evento_id", label: "Evento ID" },
            { key: "alfa_score", label: "Alfa", render: (row) => renderPct(row, "alfa_score") },
            { key: "beta_score", label: "Beta", render: (row) => renderPct(row, "beta_score") },
            { key: "delta_score", label: "Delta", render: (row) => renderPct(row, "delta_score") },
            { key: "omega_score", label: "Omega", render: (row) => renderPct(row, "omega_score") },
            { key: "omega_phi", label: "Phi (Φ)", render: (row) => renderFixed(row, "omega_phi", 3) },
            { key: "loki_score", label: "Loki", render: (row) => renderPct(row, "loki_score") },
            { key: "loki_dim", label: "Dim.F", render: (row) => renderFixed(row, "loki_dim", 3) },
            { key: "padre_decision", label: "Padre", render: (row) => renderDecision(row, "padre_decision") },
            { key: "padre_prob", label: "Prob. Padre", render: (row) => renderPct(row, "padre_prob") },
          ]}
          pageSize={20}
        />
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Evolución de Phi (Ω) — Integración de Información</h3>
        <LineSpark
          data={historial.map(d => ({ key: d.timestamp, value: d.omega_phi }))}
          xKey="key"
          yKey="value"
          color="#ec4899"
          height={200}
        />
      </div>
    </div>
  );
}