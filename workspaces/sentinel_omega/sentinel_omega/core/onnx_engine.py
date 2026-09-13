"""
Sentinel Omega — ONNX Runtime Engine
High-performance inference using ONNX Runtime for all 5 bots
"""

import numpy as np
from typing import Optional, Dict, Tuple, List
from pathlib import Path
import logging

try:
    import onnxruntime as rt
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("WARNING: onnxruntime not installed. Install with: pip install onnxruntime")

from sentinel_omega.config.onnx_config import ONNXModelConfig, ONNXRuntimeConfig


logger = logging.getLogger(__name__)


class ONNXModelLoader:
    """Load and manage ONNX models for all bots"""
    
    def __init__(self, runtime_config: ONNXRuntimeConfig, models_dir: str = "sentinel_omega/models"):
        self.runtime_config = runtime_config
        self.models_dir = Path(models_dir)
        self.sessions: Dict[str, rt.InferenceSession] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if not ONNX_AVAILABLE:
            self.logger.warning("ONNX Runtime not available")
    
    def load_model(self, model_config: ONNXModelConfig) -> Optional[rt.InferenceSession]:
        """Load a single ONNX model"""
        if not ONNX_AVAILABLE:
            self.logger.error(f"Cannot load {model_config.name}: onnxruntime not available")
            return None
        
        model_path = model_config.get_full_path(str(self.models_dir))
        
        if not model_path.exists():
            self.logger.warning(f"Model file not found: {model_path}")
            return None
        
        try:
            sess_options = rt.SessionOptions()
            level_name = self.runtime_config.graph_optimization_level.upper()
            # Compat: "ALL" -> "ORT_ENABLE_ALL" (onnxruntime 1.27+)
            if level_name == "ALL":
                level_name = "ORT_ENABLE_ALL"
            sess_options.graph_optimization_level = getattr(
                rt.GraphOptimizationLevel, level_name
            )
            sess_options.intra_op_num_threads = self.runtime_config.intra_op_num_threads
            sess_options.inter_op_num_threads = self.runtime_config.inter_op_num_threads
            
            session = rt.InferenceSession(
                str(model_path),
                sess_options=sess_options,
                providers=self.runtime_config.providers
            )
            
            self.sessions[model_config.name] = session
            self.logger.info(f"Loaded ONNX model: {model_config.name} ({model_path})")
            return session
        except Exception as e:
            self.logger.error(f"Failed to load {model_config.name}: {e}")
            return None
    
    def run_inference(self, session: rt.InferenceSession, input_data: np.ndarray) -> Optional[np.ndarray]:
        """Run inference on a single model"""
        if session is None:
            return None
        
        try:
            input_name = session.get_inputs()[0].name
            output_name = session.get_outputs()[0].name
            
            # Ensure input is float32
            if input_data.dtype != np.float32:
                input_data = input_data.astype(np.float32)
            
            # Add batch dimension if needed
            if len(input_data.shape) == 1:
                input_data = np.expand_dims(input_data, axis=0)
            
            result = session.run([output_name], {input_name: input_data})
            return result[0]
        except Exception as e:
            self.logger.error(f"Inference failed: {e}")
            return None


class ONNXBotInference:
    """Wrapper for running bot inference via ONNX"""
    
    def __init__(self, bot_name: str, model_config: ONNXModelConfig, session: Optional[rt.InferenceSession] = None):
        self.bot_name = bot_name
        self.model_config = model_config
        self.session = session
        self.logger = logging.getLogger(f"ONNXBot.{bot_name}")
    
    def predict(self, features: np.ndarray) -> Tuple[float, str]:
        """
        Run prediction on bot model.
        Returns: (confidence: float, signal_type: str)
        """
        if self.session is None:
            return 0.0, "NO_SIGNAL"
        
        try:
            loader = ONNXModelLoader(runtime_config=ONNXRuntimeConfig())
            output = loader.run_inference(self.session, features)
            
            if output is None:
                return 0.0, "NO_SIGNAL"
            
            # Extract confidence (first output)
            confidence = float(output[0, 0]) if output.shape[0] > 0 else 0.0
            confidence = np.clip(confidence, 0.0, 1.0)
            
            # Extract signal type (second output if available)
            signal_idx = int(output[0, 1]) if output.shape[1] > 1 else 0
            signal_map = {
                0: "NO_SIGNAL",
                1: "NEUTRAL",
                2: "WATCH",
                3: "ALERT",
                4: "BULLISH",
                5: "BEARISH",
            }
            signal_type = signal_map.get(signal_idx, "UNKNOWN")
            
            return confidence, signal_type
        except Exception as e:
            self.logger.error(f"Prediction failed: {e}")
            return 0.0, "NO_SIGNAL"


def create_mock_onnx_session(
    input_features: int = 10, output_features: int = 2
) -> Optional["rt.InferenceSession"]:
    """
    Create a mock ONNX session for testing (when models not yet exported).

    Builds a valid MatMul model that maps [N, input_features] ->
    [N, output_features] with a zero weight, so inference returns a
    well-formed all-zero output (confidence 0.0 -> NO_SIGNAL). Shapes are
    parametrizable so the mock can stand in for any bot's model_config.

    Requires the `onnx` builder package (see requirements_jupyter.txt).
    """
    if not ONNX_AVAILABLE:
        return None

    try:
        import numpy as np
        from onnx import helper, numpy_helper, TensorProto

        X = helper.make_tensor_value_info(
            'X', TensorProto.FLOAT, [None, input_features]
        )
        Y = helper.make_tensor_value_info(
            'Y', TensorProto.FLOAT, [None, output_features]
        )

        # Constant weight [input_features, output_features] of zeros — a valid
        # linear layer whose output is the declared graph output Y.
        weight = numpy_helper.from_array(
            np.zeros((input_features, output_features), dtype=np.float32), name='W'
        )
        node = helper.make_node('MatMul', inputs=['X', 'W'], outputs=['Y'])

        graph = helper.make_graph(
            [node], 'mock_graph', [X], [Y], initializer=[weight]
        )
        # Opset 17 — soportado por onnxruntime>=1.14 (el default de onnx es
        # más nuevo de lo que garantiza el runtime instalado).
        model = helper.make_model(
            graph,
            producer_name='sentinel_omega',
            opset_imports=[helper.make_opsetid("", 17)],
        )

        session = rt.InferenceSession(model.SerializeToString())
        logger.info(
            "Created mock ONNX session (%d -> %d)", input_features, output_features
        )
        return session
    except ImportError:
        logger.warning(
            "Mock ONNX model needs the `onnx` package "
            "(pip install onnx); mock unavailable."
        )
        return None
    except Exception as e:
        logger.error(f"Failed to create mock session: {e}")
        return None
