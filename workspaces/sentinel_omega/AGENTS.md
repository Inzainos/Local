# Sentinel Omega — Agents Registry (v2.5.4)

This document defines the roles, logic, and hierarchy of the agents within the Sentinel Omega system.

## 1. Hierarchy of Consensus (The Path to Alert)
The system follows a tiered validation process. A signal must climb this ladder to trigger a final alert:

**SNT Families** $\rightarrow$ **Omega** $\rightarrow$ **Loki**

1. **SNT Families (Alfa, Beta, Delta)**: The first line of detection. Consists of specialized bots looking for patterns in space weather, cymatics, and financial sentiment.
2. **Omega**: The global correlator. Validates if the SNT signals align with the "Cosmic Rhythm" (Schumann, Luna, Solar Envelopes).
3. **Loki (The Final Act)**: The Bayesian collapse. Uses the Unified Field Theory to determine the final probability of the event.

---

## 2. Agent Definitions

### 🟦 SNT Families (The Detectors)
- **Alfa-1 (Space Weather)**: Monitors Bz, solar wind, and seismic clusters.
- **Alfa-2 (Satellite)**: Analyzes ESA Sentinel data. Now trained on full satellite history.
- **Beta-1 (The Artist)**: Generates the **Cymatic Figure**. Captures the current vibration of the system as a vector.
- **Beta-2 (The Analyst)**: Interprets the Figure. Compares it against the historical library to find magnitude-specific replicas.
- **Delta (Financial Sentiment)**: Monitors VIX, Fear & Greed, and Crypto Topology. **Active Vote**: Now emits ALERT when financial stress is extreme.

### 🟪 Omega (The Correlator)
- **Role**: Validates the SNT consensus against global cosmic cycles.
- **Logic**: If $\ge 2$ families agree and the Schumann correlation is $> 0.3$, Omega elevates the signal.

### 🟥 Loki (The Bayesian Collapse)
- **Role**: Final probability arbiter based on the Unified Field Theory.
- **Process**: Gauss-Jordan Cleaning $\rightarrow$ Fourier Scanning $\rightarrow$ Bayesian Update.
- **Output**: Probability of event collapse based on the Golden Spiral ($\phi$).

### ⚖️ The Judge (The Auditor)
- **Role**: Cold auditor of truth.
- **Rule**: Compares predictions against the USGS catalog.
- **Penalty**: Applies asymmetric loss. If the **Father** fails to corroborate a signal that later becomes a hit, the Father and the informing bot receive a severe weight penalty.
EOF
