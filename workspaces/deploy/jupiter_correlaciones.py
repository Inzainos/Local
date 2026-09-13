"""
jupiter_correlaciones.py — run Júpiter on live data
===================================================
Fetches the three real sources and prints/saves the solar-storm correlations:

  NOAA SWPC (Kp geomagnetic + GOES X-ray flares)  ×  Google Trends  ×  Schumann

    python deploy/jupiter_correlaciones.py

Writes estado/jupiter_correlaciones.json (correlations only — no raw series).
Descriptive analysis; scope: solar storms only.
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from sentinel_omega.infrastructure.api.noaa import fetch_goes_xray  # noqa: E402
from sentinel_omega.infrastructure.api.gfz_kp import fetch_kp_history  # noqa: E402
from sentinel_omega.infrastructure.api.google_trends import fetch_solar_storm_trends  # noqa: E402
from sentinel_omega.core.precursor import jupiter  # noqa: E402


def main() -> None:
    print("=== Júpiter — solar-storm correlations (live) ===\n")

    kp = fetch_kp_history(days=90)          # GFZ Potsdam long history
    xray = fetch_goes_xray()
    trends = fetch_solar_storm_trends(timeframe="today 3-m")

    # Schumann accumulates live in the DB; load whatever history exists (best-effort).
    schumann = None
    try:
        from sentinel_omega.infrastructure.database.repository import SentinelRepository
        rows = SentinelRepository().schumann_trend(limit=500)
        schumann = jupiter.schumann_series_from_trend(rows)
    except Exception as exc:  # noqa: BLE001 — no DB / empty table is fine
        logging.getLogger("jupiter").info(f"Schumann history unavailable: {exc}")

    print("Sources:")
    print(f"  GFZ Kp (90d)   : {0 if kp is None else len(kp)} records")
    print(f"  NOAA GOES X-ray: {0 if xray is None else len(xray)} records")
    print(f"  Google Trends  : {0 if trends is None else len(trends)} daily points")
    print(f"  Schumann (DB)  : {0 if schumann is None else len(schumann)} daily points")

    result = jupiter.analyze(kp_df=kp, xray_df=xray, trends_df=trends, schumann_series=schumann)

    print(f"\nCommon window: {result.window_days} days")
    print(f"Series available: {', '.join(result.series_available)}")
    if not result.correlations:
        print("No correlations computed.")
    for c in result.correlations:
        rho = "n/a" if c.spearman_rho is None else f"{c.spearman_rho:+.3f}"
        p = "n/a" if c.p_value is None else f"{c.p_value:.4f}"
        lag = "n/a" if c.best_lag_corr is None else f"{c.best_lag_corr:+.3f} @ lag {c.best_lag_days:+d}d"
        print(f"  {c.pair:16s} n={c.n:3d}  Spearman ρ={rho} (p={p})  best-lag={lag}")
    for note in result.notes:
        print(f"  note: {note}")

    out = Path(__file__).resolve().parents[1] / "estado" / "jupiter_correlaciones.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
