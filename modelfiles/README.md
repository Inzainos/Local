# Modelfiles thin (Concilio)

Alias de Ollama con un system prompt delgado, sin corpus de arquitectura Sentinel.

## Qué usa la v1 (2026-09-25)

| rol | modelo en `config.yaml` | Modelfile |
|---|---|---|
| investigador | `concilio-investigador` | `Modelfile.concilio-investigador` (`FROM llama3.2:3b`) |
| árbitro | `concilio-arbitro` | `Modelfile.concilio-arbitro` (`FROM gemma3:4b`) |
| coder | `codegemma:7b` | ninguno: tag base |
| extractor de formato | `qwen2.5-coder:7b` | ninguno: tag base |

El coder y el extractor van **sin Modelfile propio** a propósito: se midieron como tags base
(ver `CHANGELOG.md`), y un system prompt embebido cambiaría lo que se midió. Estos modelos
son sensibles al texto que reciben —añadir reglas correctas y redundantes bajó a codegemma de
72/73 a 68/73 casos—, así que cualquier Modelfile nuevo se mide antes de usarse.

```bash
cd /home/deamon/consensus-expert-agent
bash scripts/create_concilio_models.sh      # crea los alias concilio-*
```

## Modelfiles que quedan de versiones anteriores

`Modelfile.lightest|medium|heavy|worker|arbitro` y `concilio-worker`: el esquema anterior
(nemotron-mini de investigador, deepseek-r1:8b de coder). `Modelfile.medium` sigue siendo el
respaldo lejano del coder vía `concilio-medium`. No usar `Modelfile.sentinel-concilio-*`
mientras `inject_sentinel_architecture: false`.
