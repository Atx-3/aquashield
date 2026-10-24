"""
Ollama LLM Client for AQUA SHIELD AI.

Provides a modular, reusable connection to local Ollama instances.
Allows switching models (e.g. qwen3:1.7b -> qwen3:4b) via configuration or environment variables.
Supports configurable timeout via OLLAMA_TIMEOUT env var.

Ollama runs on your computer and exposes a small web API (default http://127.0.0.1:11434):
    GET  /api/tags      -> list installed models (used to check Ollama is running)
    POST /api/generate  -> send a prompt, get the model's text reply
    POST /api/chat      -> same, but with a list of chat messages
This client uses only Python's built-in urllib, so it needs no extra packages.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OllamaError(Exception):
    """Base exception for Ollama client errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when unable to connect to the Ollama service."""
    pass


class OllamaModelError(OllamaError):
    """Raised when the specified model is not available or fails."""
    pass


class OllamaClient:
    """
    Client for interacting with local Ollama service.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize Ollama client.

        :param model_name: Name of model in Ollama (defaults to env OLLAMA_MODEL or 'qwen3:1.7b')
        :param base_url: Base URL of Ollama API (defaults to env OLLAMA_HOST or 'http://127.0.0.1:11434')
        :param timeout: HTTP request timeout in seconds (defaults to env OLLAMA_TIMEOUT or 90)
        """
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
        raw_url = base_url or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.base_url = raw_url.rstrip("/")

        # Configurable timeout from parameter or environment variable (default: 90 seconds)
        if timeout is not None:
            self.timeout = timeout
        else:
            env_timeout = os.getenv("OLLAMA_TIMEOUT")
            if env_timeout and env_timeout.strip().isdigit():
                self.timeout = int(env_timeout.strip())
            else:
                self.timeout = 90

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Internal helper to make HTTP POST requests to Ollama API."""
        url = f"{self.base_url}{endpoint}"
        # Convert the Python dict to JSON text, then to bytes for sending over HTTP
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.getcode()
                response_text = resp.read().decode("utf-8")
                if status_code != 200:
                    raise OllamaError(f"Ollama returned HTTP {status_code}: {response_text}")
                return json.loads(response_text)
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError) or "refused" in str(e).lower():
                raise OllamaConnectionError(
                    f"Could not connect to Ollama at {self.base_url}. Is Ollama running?"
                ) from e
            raise OllamaConnectionError(f"Network error communicating with Ollama: {e}") from e
        except json.JSONDecodeError as e:
            raise OllamaError(f"Failed to parse Ollama response as JSON: {e}") from e

    def _get(self, endpoint: str) -> Dict[str, Any]:
        """Internal helper to make HTTP GET requests to Ollama API."""
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.getcode()
                response_text = resp.read().decode("utf-8")
                if status_code != 200:
                    raise OllamaError(f"Ollama returned HTTP {status_code}: {response_text}")
                return json.loads(response_text)
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Could not connect to Ollama at {self.base_url}. Is Ollama running?"
            ) from e

    def is_available(self) -> bool:
        """Check if Ollama service is running and accessible."""
        try:
            res = self._get("/api/tags")
            return "models" in res
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """List all model names pulled in Ollama."""
        res = self._get("/api/tags")
        models = res.get("models", [])
        return [m.get("name", "") for m in models if "name" in m]

    def has_model(self, model_name: Optional[str] = None) -> bool:
        """Check if a specific model is installed in Ollama."""
        target = model_name or self.model_name
        available = self.list_models()
        return any(target == m or target == m.split(":")[0] for m in available)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        format: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        """
        Send a generation request to the Ollama model.

        :param prompt: User prompt or formatted input.
        :param system: Optional system prompt.
        :param format: Output format enforcement ("json" or None).
        :param temperature: Sampling temperature (0.0 for deterministic output).
        :return: String response from the model.
        """
        # stream=False -> wait for the whole answer instead of receiving it word by word.
        # temperature 0.0 -> always pick the most likely word, so answers are repeatable.
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format

        res = self._post("/api/generate", payload)
        return res.get("response", "").strip()

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        """
        Send a chat conversation request to the Ollama model.

        :param messages: List of message dicts with 'role' and 'content'.
        :param format: Output format enforcement ("json" or None).
        :param temperature: Sampling temperature (0.0 for deterministic).
        :return: String content of the assistant response.
        """
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if format:
            payload["format"] = format

        res = self._post("/api/chat", payload)
        message = res.get("message", {})
        return message.get("content", "").strip()
