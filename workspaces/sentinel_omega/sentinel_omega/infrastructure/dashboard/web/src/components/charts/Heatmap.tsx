export function Heatmap({
  rows,
  cols,
  get,
  caption,
}: {
  rows: string[];
  cols: string[];
  get: (row: string, col: string) => number | null;
  caption?: string;
}) {
  if (!rows.length || !cols.length) {
    return <div className="text-sm text-muted">Sin correlaciones en esta base.</div>;
  }
  const vals = rows.flatMap((r) => cols.map((c) => get(r, c)).filter((v): v is number => v != null));
  const max = Math.max(0.0001, ...vals);
  return (
    <div className="space-y-2">
      <div className="overflow-auto rounded-lg border border-border">
        <table className="min-w-[640px] text-left text-[11px]">
          <thead className="bg-panel text-muted">
            <tr>
              <th className="px-2 py-1">Patrón \\ evento</th>
              {cols.map((c) => (
                <th key={c} className="px-2 py-1 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r} className="border-t border-border/60">
                <td className="px-2 py-1 mono">{r}</td>
                {cols.map((c) => {
                  const v = get(r, c);
                  const t = v == null ? 0 : v / max;
                  const bg = v == null ? "transparent" : `rgba(94,106,210,${0.15 + t * 0.85})`;
                  const hot = t > 0.55;
                  return (
                    <td key={c} className="px-2 py-1 text-center mono" style={{ background: bg, color: hot ? "#fff" : "#c5c7c9" }}>
                      {v == null ? "—" : v.toFixed(3)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        {caption ||
          "Color: más azul intenso = mayor 'fuerza' (el patrón se vio más veces junto a esa clase de evento). Claro = raro. No es causalidad ni una predicción."}
      </p>
    </div>
  );
}
