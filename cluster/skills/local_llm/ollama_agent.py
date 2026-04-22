"""
Ollama Agent - Integration with Ollama for local LLMs
"""

import aiohttp
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import structlog
import json

from .base_llm import BaseLocalLLM, ModelInfo, ModelSize

logger = structlog.get_logger()


class OllamaAgent(BaseLocalLLM):
    """
    Ollama integration agent for local LLMs

    Supports:
    - All Ollama models (Llama, Mistral, Phi, Gemma, etc)
    - Streaming responses
    - Chat and completion
    - Model management (pull, delete, list)
    - Embeddings
    - Very small models (0.5-1B) for distributed work
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get('base_url', 'http://localhost:11434')
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def load_model(self) -> bool:
        """
        Load (pull) model if not available

        Returns:
            bool: True if loaded/available
        """
        try:
            # Check if model exists
            session = await self._get_session()

            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m['name'] for m in data.get('models', [])]

                    if self.model_name in models:
                        self.is_loaded = True
                        logger.info(f"Model {self.model_name} already available")
                        return True

            # Pull model if not available
            logger.info(f"Pulling model {self.model_name}")

            async with session.post(
                f"{self.base_url}/api/pull",
                json={'name': self.model_name, 'stream': False}
            ) as response:
                if response.status == 200:
                    self.is_loaded = True
                    logger.info(f"Model {self.model_name} loaded successfully")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"Failed to load model", error=error)
                    return False

        except Exception as e:
            logger.error(f"Error loading model", error=str(e))
            self.is_loaded = False
            return False

    async def unload_model(self):
        """Unload model (Ollama manages this automatically)"""
        self.is_loaded = False
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"Unloaded model {self.model_name}")

    async def generate(self,
                      prompt: str,
                      max_tokens: int = 512,
                      temperature: float = 0.7,
                      top_p: float = 0.9,
                      stop: Optional[List[str]] = None,
                      stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Generate text completion"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        payload = {
            'model': self.model_name,
            'prompt': prompt,
            'stream': stream,
            'options': {
                'num_predict': max_tokens,
                'temperature': temperature,
                'top_p': top_p
            }
        }

        if stop:
            payload['options']['stop'] = stop

        if stream:
            return self._stream_generate(session, payload)
        else:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('response', '')
                else:
                    error = await response.text()
                    raise Exception(f"Generation failed: {error}")

    async def _stream_generate(self, session: aiohttp.ClientSession,
                               payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Stream generation tokens"""
        async with session.post(
            f"{self.base_url}/api/generate",
            json=payload
        ) as response:
            if response.status == 200:
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if 'response' in data:
                                yield data['response']
                        except json.JSONDecodeError:
                            continue
            else:
                error = await response.text()
                raise Exception(f"Streaming failed: {error}")

    async def chat(self,
                  messages: List[Dict[str, str]],
                  max_tokens: int = 512,
                  temperature: float = 0.7,
                  stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Chat completion"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        payload = {
            'model': self.model_name,
            'messages': messages,
            'stream': stream,
            'options': {
                'num_predict': max_tokens,
                'temperature': temperature
            }
        }

        if stream:
            return self._stream_chat(session, payload)
        else:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['message']['content']
                else:
                    error = await response.text()
                    raise Exception(f"Chat failed: {error}")

    async def _stream_chat(self, session: aiohttp.ClientSession,
                          payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Stream chat tokens"""
        async with session.post(
            f"{self.base_url}/api/chat",
            json=payload
        ) as response:
            if response.status == 200:
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if 'message' in data and 'content' in data['message']:
                                yield data['message']['content']
                        except json.JSONDecodeError:
                            continue
            else:
                error = await response.text()
                raise Exception(f"Chat streaming failed: {error}")

    async def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Generate embeddings"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        # Handle single text or list
        texts = [text] if isinstance(text, str) else text
        results = []

        for t in texts:
            async with session.post(
                f"{self.base_url}/api/embeddings",
                json={'model': self.model_name, 'prompt': t}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results.append(data.get('embedding', []))
                else:
                    error = await response.text()
                    raise Exception(f"Embedding failed: {error}")

        return results[0] if isinstance(text, str) else results

    async def get_info(self) -> ModelInfo:
        """Get model information"""
        if self.model_info:
            return self.model_info

        try:
            session = await self._get_session()

            async with session.post(
                f"{self.base_url}/api/show",
                json={'name': self.model_name}
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # Parse model details
                    details = data.get('details', {})
                    params = details.get('parameter_size', 'unknown')
                    quant = details.get('quantization_level', None)

                    # Estimate size category
                    size = self.get_model_size()

                    self.model_info = ModelInfo(
                        name=self.model_name,
                        size=size,
                        parameters=params,
                        context_length=data.get('model_info', {}).get('context_length', 2048),
                        quantization=quant,
                        capabilities=['generate', 'chat', 'embed']
                    )

                    return self.model_info

        except Exception as e:
            logger.error("Failed to get model info", error=str(e))

        # Fallback
        return ModelInfo(
            name=self.model_name,
            size=self.get_model_size(),
            parameters='unknown',
            context_length=2048,
            capabilities=['generate', 'chat']
        )

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models"""
        try:
            session = await self._get_session()

            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('models', [])

        except Exception as e:
            logger.error("Failed to list models", error=str(e))

        return []

    async def delete_model(self, model_name: Optional[str] = None) -> bool:
        """Delete a model"""
        name = model_name or self.model_name

        try:
            session = await self._get_session()

            async with session.delete(
                f"{self.base_url}/api/delete",
                json={'name': name}
            ) as response:
                if response.status == 200:
                    logger.info(f"Deleted model {name}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"Failed to delete model", error=error)
                    return False

        except Exception as e:
            logger.error("Error deleting model", error=str(e))
            return False

    @staticmethod
    def get_recommended_small_models() -> List[Dict[str, str]]:
        """Get list of recommended small models for distributed work"""
        return [
            {
                'name': 'phi3:mini',
                'size': '0.5B',
                'description': 'Microsoft Phi-3 Mini - excellent for reasoning',
                'tasks': ['analytical', 'coding', 'factual']
            },
            {
                'name': 'tinyllama',
                'size': '1.1B',
                'description': 'TinyLlama - fast general purpose model',
                'tasks': ['chat', 'summarization', 'general']
            },
            {
                'name': 'gemma:2b',
                'size': '2B',
                'description': 'Google Gemma 2B - balanced performance',
                'tasks': ['chat', 'creative', 'analytical']
            },
            {
                'name': 'stablelm2:1.6b',
                'size': '1.6B',
                'description': 'StableLM 2 - good for creative tasks',
                'tasks': ['creative', 'chat', 'summarization']
            },
            {
                'name': 'qwen:0.5b',
                'size': '0.5B',
                'description': 'Qwen 0.5B - ultra-fast for simple tasks',
                'tasks': ['classification', 'extraction', 'simple_qa']
            }
        ]
