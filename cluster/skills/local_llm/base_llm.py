"""
Base Local LLM Agent - Abstract base for local language models
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import structlog
from dataclasses import dataclass
from enum import Enum

logger = structlog.get_logger()


class ModelSize(Enum):
    """Model size categories"""
    TINY = "tiny"      # < 500M parameters
    SMALL = "small"    # 500M - 1B
    MEDIUM = "medium"  # 1B - 3B
    LARGE = "large"    # 3B - 7B
    XLARGE = "xlarge"  # 7B+


@dataclass
class ModelInfo:
    """Model information"""
    name: str
    size: ModelSize
    parameters: str
    context_length: int
    quantization: Optional[str] = None
    capabilities: List[str] = None


class BaseLocalLLM(ABC):
    """
    Abstract base class for local LLM agents

    All local LLM agents must implement:
    - load_model() - Load model into memory
    - unload_model() - Unload model from memory
    - generate() - Generate text completion
    - chat() - Chat completion
    - embed() - Generate embeddings (optional)
    - get_info() - Get model information
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.model = None
        self.is_loaded = False
        self.model_name = self.config.get('model_name', 'unknown')
        self.model_info = None

        logger.info(
            f"Initialized {self.__class__.__name__}",
            model=self.model_name
        )

    @abstractmethod
    async def load_model(self) -> bool:
        """
        Load model into memory

        Returns:
            bool: True if loaded successfully
        """
        pass

    @abstractmethod
    async def unload_model(self):
        """Unload model from memory"""
        pass

    @abstractmethod
    async def generate(self,
                      prompt: str,
                      max_tokens: int = 512,
                      temperature: float = 0.7,
                      top_p: float = 0.9,
                      stop: Optional[List[str]] = None,
                      stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """
        Generate text completion

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 - 2.0)
            top_p: Nucleus sampling threshold
            stop: Stop sequences
            stream: Stream response

        Returns:
            Generated text or async generator if streaming
        """
        pass

    @abstractmethod
    async def chat(self,
                  messages: List[Dict[str, str]],
                  max_tokens: int = 512,
                  temperature: float = 0.7,
                  stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """
        Chat completion

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Stream response

        Returns:
            Generated response or async generator if streaming
        """
        pass

    async def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """
        Generate embeddings (optional, not all models support)

        Args:
            text: Text or list of texts to embed

        Returns:
            Embedding vector(s)
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support embeddings")

    @abstractmethod
    async def get_info(self) -> ModelInfo:
        """
        Get model information

        Returns:
            ModelInfo with model details
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Check model health

        Returns:
            Health status information
        """
        try:
            if not self.is_loaded:
                return {
                    'healthy': False,
                    'loaded': False,
                    'error': 'Model not loaded'
                }

            # Try a simple generation
            test_prompt = "Hello"
            result = await self.generate(test_prompt, max_tokens=5)

            return {
                'healthy': True,
                'loaded': self.is_loaded,
                'model': self.model_name,
                'test_passed': len(result) > 0
            }

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                'healthy': False,
                'loaded': self.is_loaded,
                'error': str(e)
            }

    def supports_embedding(self) -> bool:
        """Check if model supports embeddings"""
        try:
            # Try to call embed to see if implemented
            self.embed.__func__(self, "test")
            return False
        except NotImplementedError:
            return False
        except Exception:
            return True

    def get_capabilities(self) -> List[str]:
        """Get model capabilities"""
        capabilities = ['generate', 'chat']

        if self.supports_embedding():
            capabilities.append('embed')

        if self.model_info and self.model_info.capabilities:
            capabilities.extend(self.model_info.capabilities)

        return list(set(capabilities))

    async def count_tokens(self, text: str) -> int:
        """
        Estimate token count (approximate)

        Args:
            text: Text to count

        Returns:
            Approximate token count
        """
        # Simple approximation: ~4 chars per token
        return len(text) // 4

    def get_model_size(self) -> ModelSize:
        """Get model size category"""
        if self.model_info:
            return self.model_info.size

        # Estimate from name
        name_lower = self.model_name.lower()

        if any(x in name_lower for x in ['0.5b', '500m', '0_5b']):
            return ModelSize.TINY
        elif any(x in name_lower for x in ['1b', '1.0b', '1_0b']):
            return ModelSize.SMALL
        elif any(x in name_lower for x in ['2b', '3b']):
            return ModelSize.MEDIUM
        elif any(x in name_lower for x in ['7b', '8b']):
            return ModelSize.LARGE
        else:
            return ModelSize.XLARGE

    async def optimize_for_task(self, task_type: str) -> Dict[str, Any]:
        """
        Get optimized parameters for task type

        Args:
            task_type: Type of task (coding, creative, analytical, etc)

        Returns:
            Optimized generation parameters
        """
        # Default parameters by task type
        task_params = {
            'coding': {
                'temperature': 0.2,
                'top_p': 0.95,
                'max_tokens': 1024
            },
            'creative': {
                'temperature': 0.9,
                'top_p': 0.95,
                'max_tokens': 512
            },
            'analytical': {
                'temperature': 0.3,
                'top_p': 0.9,
                'max_tokens': 512
            },
            'factual': {
                'temperature': 0.1,
                'top_p': 0.9,
                'max_tokens': 256
            },
            'summarization': {
                'temperature': 0.3,
                'top_p': 0.9,
                'max_tokens': 256
            },
            'chat': {
                'temperature': 0.7,
                'top_p': 0.9,
                'max_tokens': 512
            }
        }

        return task_params.get(task_type, task_params['chat'])
