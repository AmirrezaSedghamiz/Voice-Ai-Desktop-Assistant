"""
Local LLM Client: Interacts with llama-server strictly over loopback HTTP.
Includes safety guards against non-loopback endpoints, streaming token output,
and precise latency / token-per-second measurement.
"""

import json
import logging
import time
from typing import Generator
import httpx

from src.core.config import AssistantSettings

logger = logging.getLogger("assistant.client")


class InferenceMetrics:
    def __init__(self):
        self.time_to_first_token: float = 0.0
        self.total_generation_time: float = 0.0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.tokens_per_second: float = 0.0


class LocalLlmClient:
    """Client for local llama-server completions via loopback."""

    def __init__(self, settings: AssistantSettings):
        self.settings = settings
        self.base_url = f"http://{settings.network.server_host}:{settings.network.server_port}"
        # Assert loopback destination
        if settings.network.server_host not in ("127.0.0.1", "localhost", "::1"):
            raise PermissionError(f"Security boundary violated: Non-loopback host {settings.network.server_host}")

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        stream: bool = False,
    ) -> tuple[str, InferenceMetrics]:
        """Sends chat request to local /v1/chat/completions endpoint."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.settings.governor.max_output_tokens,
            "stream": stream,
        }

        metrics = InferenceMetrics()
        start_time = time.time()

        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"llama-server error {resp.status_code}: {resp.text}")

            metrics.total_generation_time = time.time() - start_time
            data = resp.json()

            choice = data["choices"][0]
            content = choice["message"]["content"]

            usage = data.get("usage", {})
            metrics.prompt_tokens = usage.get("prompt_tokens", 0)
            metrics.completion_tokens = usage.get("completion_tokens", 0)

            if metrics.total_generation_time > 0 and metrics.completion_tokens > 0:
                metrics.tokens_per_second = metrics.completion_tokens / metrics.total_generation_time

            return content, metrics

    def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> Generator[str, None, InferenceMetrics]:
        """Streams chat completion tokens one by one."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.settings.governor.max_output_tokens,
            "stream": True,
        }

        metrics = InferenceMetrics()
        start_time = time.time()
        first_token = True
        generated_tokens = 0

        with httpx.Client(timeout=60.0, trust_env=False) as client:
            with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"llama-server streaming error {resp.status_code}")

                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content_piece = delta.get("content", "")
                            if content_piece:
                                if first_token:
                                    metrics.time_to_first_token = time.time() - start_time
                                    first_token = False
                                generated_tokens += 1
                                yield content_piece
                        except json.JSONDecodeError:
                            pass

        metrics.total_generation_time = time.time() - start_time
        metrics.completion_tokens = generated_tokens
        if metrics.total_generation_time > 0 and generated_tokens > 0:
            metrics.tokens_per_second = generated_tokens / metrics.total_generation_time

        return metrics
