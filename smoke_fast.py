from engine.orchestrator import ConsensusOrchestrator
o=ConsensusOrchestrator(config_path="config.yaml")
r=o.fast_ask("Di solo: ok ligero")
print(r[:300] if r else "EMPTY")
