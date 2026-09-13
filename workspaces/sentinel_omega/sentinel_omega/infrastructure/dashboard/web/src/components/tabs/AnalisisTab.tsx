import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { SimpleBars, LineSpark } from "@/components/charts/Sparkline";

export function AnalisisTab() {
  const fetchData = useCallback(async () => {
    const [patrones, replicas] = await Promise.all([
      api.analysis.patrones(),
      api.analysis.replicas(),
    ]);
    return { patrones, replicas };
  }, []);

  const { data, loading, error } = usePoll(fetchData, 60000);

  const patrones = data?.patrones?.patrones ?? [];
  const replicas = data?.replicas?.replicas ?? [];

  const kpis = useMemo(() => [
    { label: "Patrones Detectados", value: patrones.length.toString() },
    { label: "Réplicas Encontradas", value: replicas.length.toString() },
    { label: "Confianza Promedio", value: patrones.length ? `${(patrones.reduce((a, p) => a + p.confianza, 0) / patrones.length * 100).toFixed(1)}%` : "—" },
    { label: "Similitud Máxima", value: replicas.length ? `${Math.max(...replicas.map(r => r.similitud)).toFixed(1)}%` : "—" },
  ], [patrones, replicas]);

  if (loading) return <div className="p-4 text-center text-gray-400">Cargando análisis...</div>;
  if (error) return <div className="p-4 text-center text-red-400">Error: {String(error)}</div>;

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Patrones Detectados</h3>
          <DataTable
            rows={patrones as Record<string, unknown>[]}
            columns={[
              { key: "id", label: "ID" },
              { key: "patron", label: "Patrón" },
              { key: "confianza", label: "Confianza", render: (_, v: unknown) => `${(Number(v) * 100).toFixed(1)}%` },
              { key: "ocurrencias", label: "Ocurrencias" },
              { key: "ultima_vez", label: "Última Vez" },
              { key: "similares", label: "Similares" },
            ]}
            pageSize={15}
          />
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Réplicas Históricas</h3>
          <DataTable
            rows={replicas as Record<string, unknown>[]}
            columns={[
              { key: "id", label: "ID" },
              { key: "evento_actual", label: "Evento Actual" },
              { key: "evento_historico", label: "Evento Histórico" },
              { key: "similitud", label: "Similitud", render: (_, v: unknown) => `${Number(v).toFixed(1)}%` },
              { key: "ventana_dias", label: "Ventana (días)" },
              { key: "magnitud_diff", label: "Diff Mag.", render: (_, v: unknown) => Number(v).toFixed(2) },
            ]}
            pageSize={15}
          />
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Distribución de Confianza — Patrones</h3>
        <SimpleBars
          data={patrones.map((p, i) => ({ key: p.id.slice(-6), value: p.confianza }))}
          xKey="key"
          yKey="value"
          color="#10b981"
          height={200}
        />
      </div>
    </div>
  );
}