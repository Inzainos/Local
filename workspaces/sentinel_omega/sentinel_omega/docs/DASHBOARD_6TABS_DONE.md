# Dashboard 6 tabs DONE

Fecha 2026-09-10 PT (Mexico City).

## Promocion

- Test: copy previo en workspaces-test/sentinel_omega.
- Prod flat: promovido 2026-09-10 ~18:12 CST desde Dev → /home/deamon/workspaces/sentinel_omega
- Prod nested: sync adicional ~18:15 CST → workspaces/sentinel_omega/sentinel_omega/ (dual-layout)

Run tipico: API 8788 (uvicorn infrastructure.dashboard.api) + UI 5174 (Vite desde DEV web).

Changed: App.tsx, api.ts, 6 tabs, package.json port 5174, api.py (+schumann_vivo/delta/clima_espacial), README.

## Archivos promovidos

- infrastructure/dashboard/web/src/App.tsx
- infrastructure/dashboard/web/src/lib/api.ts
- infrastructure/dashboard/web/src/components/tabs/PrincipalTab.tsx
- infrastructure/dashboard/web/src/components/tabs/FamiliasTab.tsx
- infrastructure/dashboard/web/src/components/tabs/OmegaTab.tsx
- infrastructure/dashboard/web/src/components/tabs/LokiTab.tsx
- infrastructure/dashboard/web/src/components/tabs/PadreJuezTab.tsx
- infrastructure/dashboard/web/src/components/tabs/ModelosTab.tsx
- infrastructure/dashboard/web/package.json
- infrastructure/dashboard/api.py
- infrastructure/dashboard/README.md
- docs/DASHBOARD_6TABS_DONE.md
- docs/SYSTEM_HEALTH_2026-09-10.md
- docs/INGEST_FIX_2026-09-10.md (stub)

## API nuevas RO

- /api/schumann_vivo
- /api/delta
- /api/clima_espacial

## Verify Prod

- App.tsx: exactamente 6 TabsTrigger (Principal, Familias, Omega, Loki, Padre+Juez, Modelos)
- messaging loter = 0
- node_modules presente (no npm install largo)

## Blockers

- correlaciones vacias / datos flat → ver INGEST_FIX stub
- ONNX placeholder
- tsc shim
- prod gate firmas pendiente — NO enabled entrenar/firmas/remapeo

## Nota runtime

Vite 5174 suele correr desde Dev. Si se necesita UI desde arbol Prod: npm run dev alli o build estatico. Launcher Prod puede no servir React automaticamente.
