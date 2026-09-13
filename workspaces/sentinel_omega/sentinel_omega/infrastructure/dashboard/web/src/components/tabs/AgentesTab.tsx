import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { SimpleBars } from "@/components/charts/Sparkline";

export function AgentesTab() {
  const fetchAgentes = useCallback(async () => {
    const status = await api.agents.status();
    return { status };
  }, []);

  const { data, loading, error } = usePoll(fetchAgentes, 30000);

  const agents = data?.status?.status ?? [];

  const kpis = useMemo(() => [
    { label: "Total Agentes", value: agents.length.toString() },
    { label: "OK", value: agents.filter((a: any) => a.status === "ok").length.toString(), color: "green" },
    { label: "WARN", value: agents.filter((a: any) => a.status === "warn").length.toString(), color: "yellow" },
    { label: "ERROR", value: agents.filter((a: any) => a.status === "error").length.toString(), color: "red" },
    { label: "Ejecuciones 24h", value: agents.reduce((a: number, b: any) => a + b.runs_24h, 0).toString() },
    { label: "Errores 24h", value: agents.reduce((a: number, b: any) => a + b.errors_24h, 0).toString(), color: agents.reduce((a: number, b: any) => a + b.errors_24h, 0) > 0 ? "red" : "green" },
  ], [agents]);

  if (loading) return <div className="p-4 text-center text-gray-400">Cargando agentes...</div>;
  if (error) return <div className="p-4 text-center text-red-400">Error: {String(error)}</div>;

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Estado de Agentes</h3>
        <DataTable
          rows={agents as Record<string, unknown>[]}
          columns={[
            { key: "name", label: "Agente" },
            { key: "status", label: "Estado", render: (_, v: unknown) => {
              const status = String(v);
              return (
                <span className={`px-2 py-1 rounded text-xs font-bold ${
                  status === "ok" ? "bg-green-900/50 text-green-400" :
                  status === "warn" ? "bg-yellow-900/50 text-yellow-400" :
                  status === "error" ? "bg-red-900/50 text-red-400" :
                  "bg-gray-700 text-gray-400"
                }`}>{status.toUpperCase()}</span>
              );
            }},
            { key: "last_run", label: "Última Ejecución" },
            { key: "runs_24h", label: "Ejec. 24h" },
            { key: "errors_24h", label: "Errores 24h" },
            { key: "version", label: "Versión" },
          ]}
          pageSize={20}
        />
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Ejecuciones 24h por Agente</h3>
        <SimpleBars
          data={agents.map((a: any) => ({ key: a.name, value: a.runs_24h }))}
          xKey="key"
          yKey="value"
          color="#3b82f6"
          height={200}
        />
      </div>
    </div>
  );
}