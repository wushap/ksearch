"""Ollama chat/generate API client."""

import logging

import requests

logger = logging.getLogger(__name__)


class OllamaChatClient:
    """Client for Ollama chat API (generation, not embeddings)."""

    def __init__(
        self,
        model: str = "gemma4:e2b",
        ollama_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        timeout: int = 60,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        format_json: bool = False,
        temperature: float | None = None,
    ) -> str:
        """Send chat messages to Ollama and return response text."""
        body: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature if temperature is not None else self.temperature},
        }
        if format_json:
            body["format"] = "json"

        response = requests.post(
            f"{self.ollama_url}/api/chat",
            json=body,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned {response.status_code}: {response.text}")

        try:
            return response.json()["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Ollama response format: {exc}") from exc

    def generate(self, prompt: str, system: str = "", format_json: bool = False, temperature: float | None = None) -> str:
        """Convenience: single prompt to response."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, format_json=format_json, temperature=temperature)

    def health_check(self) -> dict:
        """Check Ollama availability and model presence."""
        result: dict = {"ollama": False, "model_available": False, "model": self.model}
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                result["ollama"] = True
                result["model_available"] = self.model in model_names or any(
                    m.startswith(self.model) for m in model_names
                )
                result["available_models"] = model_names
        except Exception as e:
            result["error"] = str(e)
        return result
