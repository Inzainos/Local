import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { HealthStrip } from "@/components/HealthStrip";
import { PrincipalTab } from "@/components/tabs/PrincipalTab";
import { FamiliasTab } from "@/components/tabs/FamiliasTab";
import { OmegaTab } from "@/components/tabs/OmegaTab";
import { LokiTab } from "@/components/tabs/LokiTab";
import { PadreJuezTab } from "@/components/tabs/PadreJuezTab";
import { ModelosTab } from "@/components/tabs/ModelosTab";

/**
 * Sentinel Omega — rediseño a exactamente 6 pestañas.
 * Integra todos los streams de la auditoría DASHBOARD_6TABS_AUDIT.md.
 * Los tabs antiguos (19) quedan como módulos reutilizables; la UI solo expone estas 6.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-white/5 bg-[#08090a]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs font-bold">◈</div>
            <div>
              <div className="text-sm font-semibold">Sentinel Omega</div>
              <div className="mono text-[11px] text-muted">
                Tablero de lectura · 6 vistas · datos reales SQLite · no predice
              </div>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Estado del sistema</h1>
          <p className="mt-1 text-sm text-muted">
            Sentinel observa precursores de eventos naturales. Estas cifras salen de la base en vivo. No es un
            pronóstico ni un consejo de compra. Empiece por Principal; si algo está en rojo, revise alertas ahí
            mismo o abra Padre + Juez.
          </p>
        </div>
        <HealthStrip />
        <Tabs defaultValue="principal">
          <TabsList>
            <TabsTrigger value="principal">Principal</TabsTrigger>
            <TabsTrigger value="familias">Familias (SNT)</TabsTrigger>
            <TabsTrigger value="omega">Omega</TabsTrigger>
            <TabsTrigger value="loki">Loki</TabsTrigger>
            <TabsTrigger value="padre">Padre + Juez</TabsTrigger>
            <TabsTrigger value="modelos">Modelos</TabsTrigger>
          </TabsList>
          <TabsContent value="principal">
            <PrincipalTab />
          </TabsContent>
          <TabsContent value="familias">
            <FamiliasTab />
          </TabsContent>
          <TabsContent value="omega">
            <OmegaTab />
          </TabsContent>
          <TabsContent value="loki">
            <LokiTab />
          </TabsContent>
          <TabsContent value="padre">
            <PadreJuezTab />
          </TabsContent>
          <TabsContent value="modelos">
            <ModelosTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
