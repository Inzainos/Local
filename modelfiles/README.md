# Thin Modelfiles (Concilio)

Optional Ollama aliases without Sentinel architecture corpus.

```bash
cd /home/deamon/consensus-expert-agent
ollama create concilio-lightest -f modelfiles/Modelfile.lightest
ollama create concilio-medium   -f modelfiles/Modelfile.medium
ollama create concilio-heavy    -f modelfiles/Modelfile.heavy
```

Then set in `config.yaml`:

```yaml
roles:
  researcher:
    model: concilio-lightest
  coder:
    model: concilio-medium
  optimizer:
    model: concilio-heavy
```

Default config uses base tags `qwen2.5:1.5b` / `gemma4:26b` with thin system prompts in YAML (same effect without `ollama create`).

Default Concilio uses thin Modelfile.lightest|medium|heavy or base tags.
Do not use Modelfile.sentinel-concilio-* while inject_sentinel_architecture: false.
