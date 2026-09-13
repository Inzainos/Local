"""
Sentinel Omega — ONNX Models Configuration
Central management for all bot ONNX models (Alfa-1, Alfa-2, Beta-1, Beta-2, Delta, Omega)
All models are ONNX runtime optimized — no TF/Torch dependencies at runtime
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class ONNXModelConfig:
    """Configuration for a single bot's ONNX model"""
    name: str
    model_path: str
    input_features: int
    output_shape: tuple
    confidence_threshold: float = 0.5
    enabled: bool = True

    def get_full_path(self, base_dir: str = "sentinel_omega/models") -> Path:
        """Get absolute path to model file (cwd-independent)."""
        base = Path(base_dir)
        if base.is_absolute() and base.exists():
            return base / self.model_path
        cand = base / self.model_path
        if cand.exists():
            return cand
        pkg = Path(__file__).resolve().parent.parent
        cand2 = pkg / "models" / self.model_path
        if cand2.exists():
            return cand2
        cand3 = pkg.parent / "sentinel_omega" / "models" / self.model_path
        return cand3 if cand3.exists() else cand2


@dataclass
class ONNXRuntimeConfig:
    """Global ONNX Runtime settings"""
    providers: list = field(default_factory=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    graph_optimization_level: str = "ORT_ENABLE_ALL"
    intra_op_num_threads: int = 4
    inter_op_num_threads: int = 1
    session_options_kwargs: Dict = field(default_factory=dict)


@dataclass
class AllONNXModelsConfig:
    """All bots' ONNX models configuration"""

    models_dir: str = "sentinel_omega/models"

    alfa1: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="alfa1",
        model_path="alfa1_spaceweather_rf.onnx",
        input_features=10,
        output_shape=(1, 2),
        confidence_threshold=0.6,
        enabled=True
    ))

    alfa2: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="alfa2",
        model_path="alfa2_satellite_cnn.onnx",
        input_features=8,
        output_shape=(1, 2),
        confidence_threshold=0.65,
        enabled=True
    ))

    beta1: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="beta1",
        model_path="beta1_schumann_fft.onnx",
        input_features=16,
        output_shape=(1, 2),
        confidence_threshold=0.55,
        enabled=True
    ))

    beta2: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="beta2",
        model_path="beta2_atmospheric_cnn.onnx",
        input_features=16,
        output_shape=(1, 2),
        confidence_threshold=0.60,
        enabled=True
    ))

    delta: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="delta",
        model_path="delta_financial_lstm.onnx",
        input_features=16,
        output_shape=(1, 2),
        confidence_threshold=0.50,
        enabled=True
    ))

    omega: ONNXModelConfig = field(default_factory=lambda: ONNXModelConfig(
        name="omega",
        model_path="omega_espacial_rf.onnx",
        input_features=12,
        output_shape=(1, 2),
        confidence_threshold=0.55,
        enabled=True
    ))

    runtime: ONNXRuntimeConfig = field(default_factory=ONNXRuntimeConfig)

    def get_enabled_models(self) -> Dict[str, ONNXModelConfig]:
        models = {
            "alfa1": self.alfa1,
            "alfa2": self.alfa2,
            "beta1": self.beta1,
            "beta2": self.beta2,
            "delta": self.delta,
            "omega": self.omega,
        }
        return {k: v for k, v in models.items() if v.enabled}

    def verify_models_exist(self) -> bool:
        for name, model_cfg in self.get_enabled_models().items():
            model_file = model_cfg.get_full_path(self.models_dir)
            if not model_file.exists():
                print(f"WARNING: Model not found: {model_file}")
                return False
        return True


onnx_config = AllONNXModelsConfig()
