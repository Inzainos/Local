type Pt = { lat: number; lon: number; label?: string; tipo?: string; mag?: number };

function mercator(lat: number, lon: number, w: number, h: number): [number, number] {
  const x = ((lon + 180) / 360) * w;
  const rad = (lat * Math.PI) / 180;
  const merc = Math.log(Math.tan(Math.PI / 4 + rad / 2));
  const y = h / 2 - (merc * w) / (2 * Math.PI);
  return [x, y];
}

const TIPO: Record<string, string> = {
  real: "#5e6ad2",
  ghost: "#8a8f98",
  geobattery: "#ffc107",
};

export function Map2D({
  nodes,
  quakes,
  highlight,
}: {
  nodes: Pt[];
  quakes?: Pt[];
  highlight?: { lat: number; lon: number; label?: string };
}) {
  const w = 900;
  const h = 420;
  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-lg border border-border bg-[#0b0c0d]">
        <rect width={w} height={h} fill="#0b0c0d" />
        {[-120, -60, 0, 60, 120].map((lon) => {
          const [x] = mercator(0, lon, w, h);
          return <line key={lon} x1={x} x2={x} y1={0} y2={h} stroke="rgba(255,255,255,0.04)" />;
        })}
        {nodes.map((n, i) => {
          const [x, y] = mercator(n.lat, n.lon, w, h);
          return (
            <circle key={`n${i}`} cx={x} cy={y} r={2.4} fill={TIPO[n.tipo || "real"] || "#5e6ad2"} opacity={0.9}>
              <title>{`${n.label || ""} ${n.tipo || ""}`}</title>
            </circle>
          );
        })}
        {(quakes || []).map((q, i) => {
          const [x, y] = mercator(q.lat, q.lon, w, h);
          const r = 2 + Math.max(0, (q.mag || 4.5) - 4) * 1.6;
          return (
            <circle key={`q${i}`} cx={x} cy={y} r={r} fill="none" stroke="#ff1744" strokeWidth={1} opacity={0.8}>
              <title>{`M${q.mag} ${q.label || ""}`}</title>
            </circle>
          );
        })}
        {highlight ? (
          (() => {
            const [x, y] = mercator(highlight.lat, highlight.lon, w, h);
            return (
              <g>
                <circle cx={x} cy={y} r={7} fill="none" stroke="#5e6ad2" strokeWidth={1.5} />
                <circle cx={x} cy={y} r={3} fill="#f7f8f8" />
                <text x={x + 10} y={y - 8} fill="#f7f8f8" fontSize="11">
                  {highlight.label || "Tlaxcala"}
                </text>
              </g>
            );
          })()
        ) : null}
      </svg>
      <div className="flex flex-wrap gap-3 text-xs text-muted">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: "#5e6ad2" }} /> real</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: "#8a8f98" }} /> ghost</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: "#ffc107" }} /> geobatería</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full border border-danger" /> sismo ≥4.5</span>
      </div>
      <p className="text-xs text-muted">
        Mapa 2D Mercator de los 125 nodos de topología y sismos recientes con coordenadas. No es un mapa de alertas
        oficiales. Si la tabla fuente USGS está vacía, la asignación nodo↔sismo de esta DB no fue remapeada.
      </p>
    </div>
  );
}
