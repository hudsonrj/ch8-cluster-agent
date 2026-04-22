"""
llama.cpp Agent - Integration with llama.cpp for efficient CPU inference
"""

import aiohttp
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import structlog
import json

from .base_llm import BaseLocalLLM, ModelInfo, ModelSize

logger = structlog.get_logger()


class LlamaCppAgent(BaseLocalLLM):
    """
    llama.cpp integration agent for efficient CPU/Metal/CUDA inference

    llama.cpp Features:
    - Optimized C++ inference (faster than Python)
    - Quantization support (GGUF format)
    - CPU, Apple Metal, CUDA support
    - Low memory footprint
    - No Python dependencies on server

    Best for:
    - CPU-only inference
    - Apple Silicon (M1/M2/M3) with Metal
    - Quantized models (4-bit, 5-bit, 8-bit)
    - Edge devices and laptops
    - When you need minimal dependencies
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get('base_url', 'http://localhost:8080')
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def load_model(self) -> bool:
        """
        Check if model is loaded (llama.cpp loads on startup)

        Returns:
            bool: True if server is accessible
        """
        try:
            session = await self._get_session()

            # Health check endpoint
            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    self.is_loaded = True
                    logger.info(f"llama.cpp server is running with {self.model_name}")
                    return True
                else:
                    logger.warning("llama.cpp server not responding")
                    return False

        except Exception as e:
            logger.error("Failed to connect to llama.cpp server", error=str(e))
            self.is_loaded = False
            return False

    async def unload_model(self):
        """Unload model (llama.cpp manages this on server side)"""
        self.is_loaded = False
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Disconnected from llama.cpp")

    async def generate(self,
                      prompt: str,
                      max_tokens: int = 512,
                      temperature: float = 0.7,
                      top_p: float = 0.9,
                      stop: Optional[List[str]] = None,
                      stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Generate text completion using llama.cpp"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        payload = {
            'prompt': prompt,
            'n_predict': max_tokens,
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
                f"{self.base_url}/completion",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('content', '')
                else:
                    error = await response.text()
                    raise Exception(f"llama.cpp generation failed: {error}")

    async def _stream_generate(self, session: aiohttp.ClientSession,
                               payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Stream generation tokens"""
        async with session.post(
            f"{self.base_url}/completion",
            json=payload
        ) as response:
            if response.status == 200:
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if 'content' in data and not data.get('stop', False):
                                yield data['content']
                        except json.JSONDecodeError:
                            continue
            else:
                error = await response.text()
                raise Exception(f"llama.cpp streaming failed: {error}")

    async def chat(self,
                  messages: List[Dict[str, str]],
                  max_tokens: int = 512,
                  temperature: float = 0.7,
                  stream: bool = False) -> Union[str, AsyncGenerator[str, None]]:
        """Chat completion using llama.cpp"""
        # Convert messages to prompt format
        # llama.cpp doesn't have native chat API, so we format it
        prompt = self._format_chat_prompt(messages)

        return await self.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=stream
        )

    def _format_chat_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format chat messages into prompt"""
        # Basic ChatML format
        prompt = ""
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                prompt += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == 'user':
                prompt += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == 'assistant':
                prompt += f"<|im_start|>assistant\n{content}<|im_end|>\n"

        prompt += "<|im_start|>assistant\n"
        return prompt

    async def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Generate embeddings using llama.cpp"""
        if not self.is_loaded:
            await self.load_model()

        session = await self._get_session()

        # Handle single text or list
        texts = [text] if isinstance(text, str) else text
        results = []

        for t in texts:
            async with session.post(
                f"{self.base_url}/embedding",
                json={'content': t}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results.append(data.get('embedding', []))
                else:
                    error = await response.text()
                    raise Exception(f"llama.cpp embedding failed: {error}")

        return results[0] if isinstance(text, str) else results

    async def get_info(self) -> ModelInfo:
        """Get model information from llama.cpp"""
        if self.model_info:
            return self.model_info

        try:
            session = await self._get_session()

            # Get model props
            async with session.get(f"{self.base_url}/props") as response:
                if response.status == 200:
                    data = await response.json()

                    size = self.get_model_size()

                    # Extract info from props
                    n_ctx = data.get('n_ctx', 2048)
                    model_desc = data.get('model_desc', '')

                    self.model_info = ModelInfo(
                        name=self.model_name,
                        size=size,
                        parameters=model_desc,
                        context_length=n_ctx,
                        quantization=self._detect_quantization(model_desc),
                        capabilities=['generate', 'chat', 'embed']
                    )

                    return self.model_info

        except Exception as e:
            logger.error("Failed to get llama.cpp model info", error=str(e))

        # Fallback
        return ModelInfo(
            name=self.model_name,
            size=self.get_model_size(),
            parameters='unknown',
            context_length=2048,
            capabilities=['generate', 'chat', 'embed']
        )

    def _detect_quantization(self, model_desc: str) -> Optional[str]:
        """Detect quantization level from model description"""
        model_lower = model_desc.lower()

        if 'q4_0' in model_lower or 'q4_k' in model_lower:
            return 'Q4'
        elif 'q5_0' in model_lower or 'q5_k' in model_lower:
            return 'Q5'
        elif 'q8_0' in model_lower:
            return 'Q8'
        elif 'f16' in model_lower:
            return 'F16'
        elif 'f32' in model_lower:
            return 'F32'

        return None

    async def tokenize(self, text: str) -> List[int]:
        """Tokenize text"""
        try:
            session = await self._get_session()

            async with session.post(
                f"{self.base_url}/tokenize",
                json={'content': text}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('tokens', [])

        except Exception as e:
            logger.error("Tokenization failed", error=str(e))

        return []

    async def count_tokens(self, text: str) -> int:
        """Count tokens accurately"""
        tokens = await self.tokenize(text)
        return len(tokens)

    async def detokenize(self, tokens: List[int]) -> str:
        """Detokenize tokens to text"""
        try:
            session = await self._get_session()

            async with session.post(
                f"{self.base_url}/detokenize",
                json={'tokens': tokens}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('content', '')

        except Exception as e:
            logger.error("Detokenization failed", error=str(e))

        return ""

    @staticmethod
    def get_launch_command(model_path: str,
                          n_ctx: int = 2048,
                          n_gpu_layers: int = 0,
                          port: int = 8080,
                          threads: Optional[int] = None) -> str:
        """
        Get command to launch llama.cpp server

        Args:
            model_path: Path to GGUF model file
            n_ctx: Context size
            n_gpu_layers: Number of layers to offload to GPU (0 = CPU only)
            port: Port to listen on
            threads: Number of CPU threads (None = auto)

        Returns:
            Command string
        """
        cmd = f"./server "
        cmd += f"-m {model_path} "
        cmd += f"-c {n_ctx} "
        cmd += f"--port {port} "

        if n_gpu_layers > 0:
            cmd += f"-ngl {n_gpu_layers} "

        if threads:
            cmd += f"-t {threads} "

        # Recommended for servers
        cmd += "--host 0.0.0.0 "
        cmd += "--embedding "  # Enable embeddings

        return cmd

    @staticmethod
    def get_recommended_quantization() -> Dict[str, str]:
        """Get recommended quantization levels by use case"""
        return {
            'fastest': 'Q4_K_M',
            'balanced': 'Q5_K_M',
            'quality': 'Q8_0',
            'best': 'F16',
            'cpu_optimized': 'Q4_0',
            'memory_constrained': 'Q4_K_S'
        }
