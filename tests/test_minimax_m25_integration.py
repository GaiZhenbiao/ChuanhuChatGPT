"""Integration tests for MiniMax M2.5 provider - requires MINIMAX_API_KEY."""

import os
import pytest
import requests

API_KEY = os.environ.get("MINIMAX_API_KEY")
BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")

pytestmark = pytest.mark.skipif(not API_KEY, reason="MINIMAX_API_KEY not set")


class TestMiniMaxM25ChatCompletion:
    """Integration tests for MiniMax M2.5 chat completions via OpenAI-compatible API."""

    def test_basic_chat_completion(self):
        """MiniMax M2.5 should return a valid chat completion."""
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": "MiniMax-M2.5",
                "messages": [{"role": "user", "content": 'Say "test passed"'}],
                "max_tokens": 20,
                "temperature": 1.0,
            },
            timeout=90,
        )
        assert response.status_code == 200, f"API error: {response.text}"
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        content = data["choices"][0]["message"]["content"]
        assert len(content) > 0, "Empty response content"

    def test_highspeed_model(self):
        """MiniMax-M2.5-highspeed should also work."""
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": "MiniMax-M2.5-highspeed",
                "messages": [{"role": "user", "content": "Say hello"}],
                "max_tokens": 20,
                "temperature": 1.0,
            },
            timeout=90,
        )
        assert response.status_code == 200, f"API error: {response.text}"
        data = response.json()
        assert len(data["choices"][0]["message"]["content"]) > 0

    def test_streaming(self):
        """MiniMax M2.5 should support streaming responses."""
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": "MiniMax-M2.5",
                "messages": [{"role": "user", "content": "Count 1 to 3"}],
                "max_tokens": 50,
                "stream": True,
                "temperature": 1.0,
            },
            stream=True,
            timeout=90,
        )
        assert response.status_code == 200, f"API error: {response.text}"
        chunks = 0
        for line in response.iter_lines():
            if line:
                decoded = line.decode()
                if decoded.startswith("data:") and "[DONE]" not in decoded:
                    chunks += 1
        assert chunks > 1, "Expected multiple streaming chunks"

    def test_system_message(self):
        """MiniMax M2.5 should handle system messages."""
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": "MiniMax-M2.5",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Always respond in exactly one word."},
                    {"role": "user", "content": "What color is the sky?"},
                ],
                "max_tokens": 10,
                "temperature": 1.0,
            },
            timeout=90,
        )
        assert response.status_code == 200, f"API error: {response.text}"
        data = response.json()
        assert len(data["choices"][0]["message"]["content"]) > 0

    def test_usage_info(self):
        """Response should include usage information."""
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": "MiniMax-M2.5",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
                "temperature": 1.0,
            },
            timeout=90,
        )
        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert data["usage"]["total_tokens"] > 0
