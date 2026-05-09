"""Tests for OllamaChatClient."""

from unittest.mock import MagicMock, patch

import pytest

from ksearch.content_optimization.ollama_client import OllamaChatClient


class TestOllamaChatClient:
    def test_chat_sends_correct_request(self):
        client = OllamaChatClient(model="gemma4:e2b", ollama_url="http://localhost:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Hello!"}}

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response) as mock_post:
            result = client.chat([{"role": "user", "content": "Hi"}])

        assert result == "Hello!"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/api/chat" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["model"] == "gemma4:e2b"
        assert body["messages"] == [{"role": "user", "content": "Hi"}]

    def test_chat_json_format(self):
        client = OllamaChatClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"key": "value"}'}}

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response) as mock_post:
            result = client.chat([{"role": "user", "content": "test"}], format_json=True)

        body = mock_post.call_args[1]["json"]
        assert body["format"] == "json"

    def test_chat_temperature_override(self):
        client = OllamaChatClient(temperature=0.3)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "ok"}}

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response) as mock_post:
            client.chat([{"role": "user", "content": "test"}], temperature=0.0)

        body = mock_post.call_args[1]["json"]
        assert body["options"]["temperature"] == 0.0

    def test_chat_temperature_default(self):
        client = OllamaChatClient(temperature=0.5)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "ok"}}

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response) as mock_post:
            client.chat([{"role": "user", "content": "test"}])

        body = mock_post.call_args[1]["json"]
        assert body["options"]["temperature"] == 0.5

    def test_chat_connection_error(self):
        client = OllamaChatClient()
        with patch("ksearch.content_optimization.ollama_client.requests.post", side_effect=ConnectionError):
            with pytest.raises(ConnectionError):
                client.chat([{"role": "user", "content": "test"}])

    def test_chat_non_200_status(self):
        client = OllamaChatClient()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Ollama returned 500"):
                client.chat([{"role": "user", "content": "test"}])

    def test_generate_convenience(self):
        client = OllamaChatClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "response"}}

        with patch("ksearch.content_optimization.ollama_client.requests.post", return_value=mock_response):
            result = client.generate("test prompt", system="be helpful")

        assert result == "response"

    def test_health_check_ok(self):
        client = OllamaChatClient(model="gemma4:e2b")
        mock_tags = MagicMock()
        mock_tags.status_code = 200
        mock_tags.json.return_value = {"models": [{"name": "gemma4:e2b"}]}

        with patch("ksearch.content_optimization.ollama_client.requests.get", return_value=mock_tags):
            result = client.health_check()

        assert result["ollama"] is True
        assert result["model_available"] is True

    def test_health_check_model_missing(self):
        client = OllamaChatClient(model="gemma4:e2b")
        mock_tags = MagicMock()
        mock_tags.status_code = 200
        mock_tags.json.return_value = {"models": [{"name": "llama3"}]}

        with patch("ksearch.content_optimization.ollama_client.requests.get", return_value=mock_tags):
            result = client.health_check()

        assert result["ollama"] is True
        assert result["model_available"] is False

    def test_health_check_connection_error(self):
        client = OllamaChatClient()
        with patch("ksearch.content_optimization.ollama_client.requests.get", side_effect=ConnectionError):
            result = client.health_check()

        assert result["ollama"] is False
