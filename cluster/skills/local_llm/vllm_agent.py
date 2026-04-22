"""
vLLM Agent - Integration with vLLM for high-performance local inference
"""

import aiohttp
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import structlog
import json

from .base_llm import BaseLocalLLM, ModelInfo, ModelSize

logger = structlog.get_logger()


class VLLMAgent(BaseLocalLLM):
    """
    vLLM integration agent for high-performance local LLM inference

    vLLM Features:
    - Continuous batching for high throughput
    - PagedAttention for efficient memory
    - Tensor parallelism for multi-GPU
    - Supports many model architectures
    - OpenAI-compatible API

    Best for:
    - Production deployments with high load
    - Multi-user scenarios
    - GPU inference with batching
    - When you need maximum throughput
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get('base_url', 'http://localhost:8000')
        self.session = None
        self.api_key = self.config.get('api_key', 'EMPTY')  # vLLM default

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def load_model(self) -> bool:
        """
        Check if model is loaded (vLLM loads on startup)

        Returns:
            bool: True if server is accessible
        """
        try:
            session = await self._get_session()

            # Check models endpoint
            async with session.get(f"{self.base_url}/v1/models") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m['id'] for m in data.get('data', [])]

                    if self.model_name in models:
                        self.is_loaded = True
                        logger.info(f"vLLM model {self.model_name} is available")
                        return True
                    else:
                        logger.warning(
                            f"Model {self.model_name} not found in vLLM",
                            available=models
                        )
                        return False

        except Exception as e:
            logger.error("Failed to connect to vLLM server", error=str(e))
            self.is_loaded = False
            return False

    async def unload_model(self):
        """Unload model (vLLM manages this on server side)"""
        self.is_loaded = False
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Disconnected from vLLM")

    async def generate(self,
                      prompt: str,
                      max_tokens: int = 512,
                      temperature: float = 0.7,
                      top_p: float = 0.9,
                      stop: Optional[List[str]] = None,
                      stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Generate text completion using vLLM"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        payload = {
            'model': self.model_name,
            'prompt': prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_p': top_p,
            'stream': stream
        }

        if stop:
            payload['stop'] = stop

        if stream:
            return self._stream_generate(session, payload)
        else:
            async with session.post(
                f"{self.base_url}/v1/completions",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['text']
                else:
                    error = await response.text()
                    raise Exception(f"vLLM generation failed: {error}")

    async def _stream_generate(self, session: aiohttp.ClientSession,
                               payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Stream generation tokens"""
        async with session.post(
            f"{self.base_url}/v1/completions",
            json=payload
        ) as response:
            if response.status == 200:
                async for line in response.content:
                    if line:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith('data: '):
                            if line_str == 'data: [DONE]':
                                break

                            try:
                                data = json.loads(line_str[6:])
                                if 'choices' in data and data['choices']:
                                    text = data['choices'][0].get('text', '')
                                    if text:
                                        yield text
                            except json.JSONDecodeError:
                                continue
            else:
                error = await response.text()
                raise Exception(f"vLLM streaming failed: {error}")

    async def chat(self,
                  messages: List[Dict[str, str]],
                  max_tokens: int = 512,
                  temperature: float = 0.7,
                  stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Chat completion using vLLM"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        payload = {
            'model': self.model_name,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': stream
        }

        if stream:
            return self._stream_chat(session, payload)
        else:
            async with session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    error = await response.text()
                    raise Exception(f"vLLM chat failed: {error}")

    async def _stream_chat(self, session: aiohttp.ClientSession,
                          payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Stream chat tokens"""
        async with session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload
        ) as response:
            if response.status == 200:
                async for line in response.content:
                    if line:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith('data: '):
                            if line_str == 'data: [DONE]':
                                break

                            try:
                                data = json.loads(line_str[6:])
                                if 'choices' in data and data['choices']:
                                    delta = data['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
            else:
                error = await response.text()
                raise Exception(f"vLLM chat streaming failed: {error}")

    async def get_info(self) -> ModelInfo:
        """Get model information from vLLM"""
        if self.model_info:
            return self.model_info

        try:
            session = await self._get_session()

            async with session.get(f"{self.base_url}/v1/models") as response:
                if response.status == 200:
                    data = await response.json()

                    for model in data.get('data', []):
                        if model['id'] == self.model_name:
                            # vLLM doesn't provide detailed info in API
                            # Estimate from model name
                            size = self.get_model_size()

                            self.model_info = ModelInfo(
                                name=self.model_name,
                                size=size,
                                parameters='unknown',
                                context_length=model.get('max_model_len', 2048),
                                capabilities=['generate', 'chat']
                            )

                            return self.model_info

        except Exception as e:
            logger.error("Failed to get vLLM model info", error=str(e))

        # Fallback
        return ModelInfo(
            name=self.model_name,
            size=self.get_model_size(),
            parameters='unknown',
            context_length=2048,
            capabilities=['generate', 'chat']
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get vLLM server statistics"""
        try:
            session = await self._get_session()

            # vLLM exposes metrics on /metrics endpoint (Prometheus format)
            # This is a simplified version
            async with session.get(f"{self.base_url}/metrics") as response:
                if response.status == 200:
                    metrics_text = await response.text()
                    # Parse basic metrics (simplified)
                    return {
                        'status': 'healthy',
                        'metrics_available': True
                    }

        except Exception as e:
            logger.error("Failed to get vLLM stats", error=str(e))

        return {'status': 'unknown'}

    @staticmethod
    def get_launch_command(model_name: str,
                          gpu_count: int = 1,
                          port: int = 8000,
                          max_model_len: Optional[int] = None) -> str:
        """
        Get command to launch vLLM server

        Args:
            model_name: HuggingFace model name
            gpu_count: Number of GPUs to use
            port: Port to listen on
            max_model_len: Maximum context length

        Returns:
            Command string
        """
        cmd = f"python -m vllm.entrypoints.openai.api_server "
        cmd += f"--model {model_name} "
        cmd += f"--port {port} "

        if gpu_count > 1:
            cmd += f"--tensor-parallel-size {gpu_count} "

        if max_model_len:
            cmd += f"--max-model-len {max_model_len} "

        # Recommended for small models
        cmd += "--dtype auto "
        cmd += "--max-num-seqs 256 "  # High throughput

        return cmd
