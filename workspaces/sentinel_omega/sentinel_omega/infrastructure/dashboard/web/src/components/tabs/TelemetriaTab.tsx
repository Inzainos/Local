import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";
import { Kpi } from "@/components/Kpi";
import { DataTable } from "@/components/DataTable";
import { SimpleBars, LineSpark } from "@/components/charts/Sparkline";

export function TelemetriaTab() {
  const fetchData = useCallback(async () => {
    const [latest, history] = await Promise.all([
      api.telemetry.latest(),
      api.telemetry.history(48),
    ]);
    return { latest, history };
  }, []);

  const { data, loading, error } = usePoll(fetchData, 30000);

  const telemetry = data?.latest;
  const history = data?.history?.history ?? [];

  const kpis = useMemo(() => [
    { label: "Kp", value: telemetry?.latest?.kp?.toFixed(2) ?? "—", color: (telemetry?.latest?.kp ?? 0) > 5 ? "red" : "green" },
    { label: "Schumann (Hz)", value: telemetry?.latest?.schumann?.toFixed(2) ?? "—" },
    { label: "Fase Lunar", value: telemetry?.latest?.lunar_phase?.toFixed(2) ?? "—" },
    { label: "Rotación (ms/día)", value: telemetry?.latest?.rotation?.toFixed(4) ?? "—" },
  ], [telemetry]);

  if (loading) return <div className="p-4 text-center text-gray-400">Cargando telemetría...</div>;
  if (error) return <div className="p-4 text-center text-red-400">Error: {String(error)}</div>;

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Kp — Últimas 48h</h3>
          <LineSpark
            data={history.map(d => ({ key: d.ts, value: d.kp }))}
            xKey="key"
            yKey="value"
            color="#3b82f6"
            height={250}
          />
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Schumann — Últimas 48h</h3>
          <LineSpark
            data={history.map(d => ({ key: d.ts, value: d.schumann }))}
            xKey="key"
            yKey="value"
            color="#10b981"
            height={250}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Fase Lunar — Últimas 48h</h3>
          <LineSpark
            data={history.map(d => ({ key: d.ts, value: d.lunar_phase }))}
            xKey="key"
            yKey="value"
            color="#f59e0b"
            height={250}
          />
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-white font-semibold mb-3">Rotación — Últimas 48h</h3>
          <LineSpark
            data={history.map(d => ({ key: d.ts, value: d.rotation }))}
            xKey="key"
            yKey="value"
            color="#8b5cf6"
            height={250}
          />
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-white font-semibold mb-3">Datos Brutos — Últimas 48h</h3>
        <DataTable
          rows={history as Record<string, unknown>[]}
          columns={[
            { key: "ts", label: "Timestamp" },
            { key: "kp", label: "Kp", render: (_, v: unknown) => Number(v).toFixed(2) },
            { key: "schumann", label: "Schumann", render: (_, v: unknown) => Number(v).toFixed(2) },
            { key: "lunar_phase", label: "Fase Lunar", render: (_, v: unknown) => Number(v).toFixed(2) },
            { key: "rotation", label: "Rotación", render: (_, v: unknown) => Number(v).toFixed(4) },
          ]}
          pageSize={20}
        />
      </div>
    </div>
  );
}