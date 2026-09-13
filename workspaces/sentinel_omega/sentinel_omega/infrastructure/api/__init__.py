"""
Real API connectors for Sentinel Omega.
All public APIs (no keys required) are fetched directly.
Authenticated APIs use environment variables.

Modules:
  - noaa: NOAA SWPC (Kp, GOES X-ray, solar wind, magnetometer)
  - noaa_hazards: Active hurricanes, historical tsunamis, tsunamigenic quake detection
  - usgs: USGS earthquake catalog
  - schumann: Tomsk Observatory Schumann resonance (WPC vision)
  - geophysical: IERS LOD, lunar ephemeris
  - esa_sentinel: ESA Copernicus Sentinel satellite data (EODAG)
  - openweathermap: Atmospheric pressure, temperature, humidity, air quality
  - telegram: Alert dispatch via Telegram Bot API
  - crypto: Binance, CoinGecko, Fear & Greed (used by Delta agent)
  - bolsa: Yahoo Finance, VIX, sector ETFs, yield spread (used by Delta agent)
"""
