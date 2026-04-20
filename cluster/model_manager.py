"""
Model Manager - Handles model selection and routing
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class PrivacyLevel(str, Enum):
    """Privacy requirements for tasks"""
    LOW = "low"        # Can use external APIs
    MEDIUM = "medium"  # Prefer local, API if needed
    HIGH = "high"      # Must use local models only


class ModelType(str, Enum):
    """Type of model deployment"""
    LOCAL = "local"    # Ollama, LM Studio, etc
    API = "api"        # OpenRouter, OpenAI, etc


@dataclass
class ModelConfig:
    """Configuration for a model"""
    name: str
    type: ModelType
    context_length: int
    cost_per_1k_tokens: float
    privacy: PrivacyLevel
    speed: str  # fast, medium, slow
    api_key_env: Optional[str] = None


@dataclass
class TaskRequirements:
    """Requirements for task execution"""
    estimated_tokens: int
    privacy_level: PrivacyLevel
    complexity: str  # simple, medium, complex
    model_preference: Optional[str] = None  # User-specified model


class ModelManager:
    """
    Manages model selection based on task requirements and worker capabilities
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.models: Dict[str, ModelConfig] = {}
        self.default_model: str = config["models"]["default"]
        self._load_models()
        logger.info("model_manager_initialized", 
                   model_count=len(self.models),
                   default=self.default_model)
    
    def _load_models(self):
        """Load available models from config"""
        for model_cfg in self.config["models"]["available"]:
            model = ModelConfig(
                name=model_cfg["name"],
                type=ModelType(model_cfg["type"]),
                context_length=model_cfg["context_length"],
                cost_per_1k_tokens=model_cfg["cost_per_1k_tokens"],
                privacy=PrivacyLevel(model_cfg["privacy"]),
                speed=model_cfg["speed"],
                api_key_env=model_cfg.get("api_key_env")
            )
            self.models[model.name] = model
            logger.debug("model_loaded", name=model.name, type=model.type)
    
    def select_model(self, requirements: TaskRequirements) -> str:
        """
        Select best model for task requirements
        
        Priority:
        1. User-specified model (if available and compatible)
        2. Privacy requirements (force local if high)
        3. Task size routing rules
        4. Default model
        """
        # 1. User preference
        if requirements.model_preference:
            if requirements.model_preference in self.models:
                model = self.models[requirements.model_preference]
                # Check privacy compatibility
                if self._is_privacy_compatible(model, requirements.privacy_level):
                    logger.info("model_selected_user_preference",
                               model=requirements.model_preference,
                               reason="user_choice")
                    return requirements.model_preference
                else:
                    logger.warning("model_rejected_privacy",
                                  model=requirements.model_preference,
                                  required_privacy=requirements.privacy_level)
        
        # 2. Privacy requirements
        if requirements.privacy_level == PrivacyLevel.HIGH:
            local_models = [
                name for name, model in self.models.items()
                if model.type == ModelType.LOCAL
            ]
            if local_models:
                selected = local_models[0]  # TODO: Better selection heuristic
                logger.info("model_selected_privacy", 
                           model=selected,
                           reason="high_privacy_required")
                return selected
        
        # 3. Routing rules
        routing = self.config["models"].get("routing", {})
        
        # Small tasks
        if requirements.estimated_tokens <= routing.get("small_tasks", {}).get("max_tokens", 500):
            model = routing["small_tasks"]["model"]
            if model in self.models:
                logger.info("model_selected_routing",
                           model=model,
                           reason="small_task",
                           tokens=requirements.estimated_tokens)
                return model
        
        # Complex tasks
        if requirements.complexity == "complex":
            model = routing.get("complex", {}).get("model")
            if model and model in self.models:
                logger.info("model_selected_routing",
                           model=model,
                           reason="complex_task")
                return model
        
        # 4. Default
        logger.info("model_selected_default", model=self.default_model)
        return self.default_model
    
    def _is_privacy_compatible(self, model: ModelConfig, required_privacy: PrivacyLevel) -> bool:
        """Check if model meets privacy requirements"""
        privacy_order = {
            PrivacyLevel.HIGH: 3,
            PrivacyLevel.MEDIUM: 2,
            PrivacyLevel.LOW: 1
        }
        return privacy_order[model.privacy] >= privacy_order[required_privacy]
    
    def get_capabilities(self) -> List[str]:
        """Return list of available model names"""
        return list(self.models.keys())
    
    def estimate_cost(self, model_name: str, tokens: int) -> float:
        """Estimate cost for using a model"""
        if model_name not in self.models:
            return 0.0
        
        model = self.models[model_name]
        return (tokens / 1000) * model.cost_per_1k_tokens
    
    def get_model_info(self, model_name: str) -> Optional[ModelConfig]:
        """Get detailed info about a model"""
        return self.models.get(model_name)
