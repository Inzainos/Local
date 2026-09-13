import { useEffect, useRef, useState } from "react";

type Pt = { lat: number; lon: number; tipo?: string; mag?: number; highlight?: boolean };
const TIPO: Record<string, string> = { real: "#5e6ad2", ghost: "#8a8f98", geobattery: "#ffc107" };

export function Globe3D({ nodes, quakes }: { nodes: Pt[]; quakes?: Pt[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [noCv, setNoCv] = useState(false);
  const rot = useRef({ lon: 20, lat: 10 });
  useEffect(() => {
    const c = ref.current;
    if (!c) { setNoCv(true); return; }
    const ctx = c.getContext("2d");
    if (!ctx) { setNoCv(true); return; }
    const w = c.width, h = c.height, R = Math.min(w, h) * 0.42;
    let dragging = false, last = { x: 0, y: 0 };
    const project = (lat: number, lon: number) => {
      const lon2 = ((lon + rot.current.lon + 540) % 360) - 180;
      const lat2 = lat + rot.current.lat;
      const phi = (lat2 * Math.PI) / 180;
      const lam = (lon2 * Math.PI) / 180;
      const x = R * Math.cos(phi) * Math.sin(lam);
      const y = -R * Math.sin(phi);
      const z = Math.cos(phi) * Math.cos(lam);
      return { x: w / 2 + x, y: h / 2 + y, z };
    };
    const draw = () => {
      ctx.fillStyle = "#08090a"; ctx.fillRect(0, 0, w, h);
      ctx.beginPath(); ctx.arc(w / 2, h / 2, R, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(94,106,210,0.4)"; ctx.stroke();
      for (const p of nodes) {
        const q = project(p.lat, p.lon); if (q.z < 0) continue;
        ctx.fillStyle = p.highlight ? "#ffffff" : (TIPO[p.tipo || "real"] || "#5e6ad2");
        ctx.beginPath(); ctx.arc(q.x, q.y, p.highlight ? 3.2 : 1.6, 0, Math.PI * 2); ctx.fill();
      }
      for (const p of quakes || []) {
        const q = project(p.lat, p.lon); if (q.z < 0) continue;
        ctx.strokeStyle = "#ff1744";
        ctx.beginPath(); ctx.arc(q.x, q.y, 2 + Math.max(0, (p.mag || 4.5) - 4), 0, Math.PI * 2); ctx.stroke();
      }
    };
    draw();
    const onDown = (e: PointerEvent) => { dragging = true; last = { x: e.clientX, y: e.clientY }; };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      rot.current.lon += (e.clientX - last.x) * 0.4;
      rot.current.lat = Math.max(-60, Math.min(60, rot.current.lat + (e.clientY - last.y) * 0.2));
      last = { x: e.clientX, y: e.clientY }; draw();
    };
    const onUp = () => { dragging = false; };
    c.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      c.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [nodes, quakes]);
  if (noCv) return <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted">Canvas no disponible. Use el mapa 2D.</div>;
  return (
    <div className="space-y-2">
      <canvas ref={ref} width={720} height={380} className="w-full rounded-lg border border-border bg-[#08090a]" />
      <p className="text-xs text-muted">Globo canvas (arrastrar). three.js no instalado en este host. Blanco = Tlaxcala.</p>
    </div>
  );
}
