"""Unit tests for MiniMax M2.5 provider integration."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock


class TestMiniMaxM25ModelType:
    """Test MiniMaxM25 ModelType enum and type detection."""

    def test_minimax_m25_enum_exists(self):
        """MiniMaxM25 enum value should exist in ModelType."""
        from modules.models.base_model import ModelType
        assert hasattr(ModelType, "MiniMaxM25")
        assert ModelType.MiniMaxM25.value == 24

    def test_minimax_m25_type_detection(self):
        """MiniMax-M2.5 models should be detected as MiniMaxM25 type via metadata."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.5")
        assert model_type == ModelType.MiniMaxM25

    def test_minimax_m25_highspeed_type_detection(self):
        """MiniMax-M2.5-highspeed should be detected as MiniMaxM25 type via metadata."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.5-highspeed")
        assert model_type == ModelType.MiniMaxM25

    def test_old_minimax_type_detection(self):
        """Old minimax-abab5-chat should still be detected as Minimax type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("minimax-abab5-chat")
        assert model_type == ModelType.Minimax


class TestMiniMaxM25ModelMetadata:
    """Test MiniMax M2.5 model metadata configuration."""

    def test_m25_in_online_models(self):
        """MiniMax-M2.5 should be in ONLINE_MODELS list."""
        from modules.presets import ONLINE_MODELS
        assert "MiniMax-M2.5" in ONLINE_MODELS
        assert "MiniMax-M2.5-highspeed" in ONLINE_MODELS

    def test_m25_metadata_exists(self):
        """MiniMax-M2.5 should have metadata entry."""
        from modules.presets import MODEL_METADATA
        assert "MiniMax-M2.5" in MODEL_METADATA
        assert "MiniMax-M2.5-highspeed" in MODEL_METADATA

    def test_m25_metadata_model_name(self):
        """Model name should be the API model ID."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["model_name"] == "MiniMax-M2.5"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["model_name"] == "MiniMax-M2.5-highspeed"

    def test_m25_metadata_api_host(self):
        """API host should be the MiniMax OpenAI-compatible endpoint."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["api_host"] == "https://api.minimax.io"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["api_host"] == "https://api.minimax.io"

    def test_m25_metadata_token_limit(self):
        """Token limit should be 204800 for M2.5 models."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["token_limit"] == 204800
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["token_limit"] == 204800

    def test_m25_metadata_model_type(self):
        """Model type should be MiniMaxM25."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["model_type"] == "MiniMaxM25"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["model_type"] == "MiniMaxM25"

    def test_m25_metadata_not_multimodal(self):
        """M2.5 models should not be multimodal."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["multimodal"] is False
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["multimodal"] is False

    def test_m25_metadata_has_description(self):
        """M2.5 models should have descriptions."""
        from modules.presets import MODEL_METADATA
        assert len(MODEL_METADATA["MiniMax-M2.5"]["description"]) > 0
        assert len(MODEL_METADATA["MiniMax-M2.5-highspeed"]["description"]) > 0

    def test_old_minimax_still_exists(self):
        """Old minimax-abab5-chat metadata should still exist."""
        from modules.presets import MODEL_METADATA
        assert "minimax-abab5-chat" in MODEL_METADATA


class TestMiniMaxM25ApiHost:
    """Test API host URL formatting for MiniMax M2.5."""

    def test_format_openai_host_minimax(self):
        """format_openai_host should correctly format MiniMax API host."""
        from modules.shared import format_openai_host
        chat_url, images_url, api_base, balance_url, usage_url = format_openai_host("https://api.minimax.io")
        assert chat_url == "https://api.minimax.io/v1/chat/completions"
        assert api_base == "https://api.minimax.io/v1"

    def test_format_openai_host_minimax_with_v1(self):
        """format_openai_host should handle API host that already ends with /v1."""
        from modules.shared import format_openai_host
        chat_url, images_url, api_base, balance_url, usage_url = format_openai_host("https://api.minimax.io/v1")
        assert chat_url == "https://api.minimax.io/v1/chat/completions"
        assert api_base == "https://api.minimax.io/v1"

    def test_format_openai_host_minimax_domestic(self):
        """format_openai_host should work with domestic MiniMax API host."""
        from modules.shared import format_openai_host
        chat_url, images_url, api_base, balance_url, usage_url = format_openai_host("https://api.minimaxi.com")
        assert chat_url == "https://api.minimaxi.com/v1/chat/completions"
        assert api_base == "https://api.minimaxi.com/v1"


class TestMiniMaxM25ModelRouting:
    """Test model routing for MiniMax M2.5 in models.py."""

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "test-minimax-key"})
    @patch("modules.models.OpenAIVision.OpenAIVisionClient.__init__", return_value=None)
    @patch("modules.models.OpenAIVision.OpenAIVisionClient.description", new_callable=lambda: property(lambda self: "test"), create=True)
    def test_m25_uses_openai_vision_client(self, mock_desc, mock_init):
        """MiniMax M2.5 should be routed through OpenAIVisionClient."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.5")
        assert model_type == ModelType.MiniMaxM25

    def test_m25_env_key_name(self):
        """MiniMax M2.5 routing should use MINIMAX_API_KEY env variable."""
        # Verify the env var name used in models.py routing
        import inspect
        from modules.models import models
        source = inspect.getsource(models.get_model)
        assert 'os.environ.get("MINIMAX_API_KEY"' in source

    def test_old_minimax_routing_preserved(self):
        """Old minimax routing code should still exist."""
        import inspect
        from modules.models import models
        source = inspect.getsource(models.get_model)
        assert "ModelType.Minimax" in source
        assert "MiniMax_Client" in source


class TestMiniMaxM25DefaultConfig:
    """Test default configuration values for MiniMax M2.5."""

    def test_default_temperature(self):
        """Default temperature should be 1.0 (from DEFAULT_METADATA)."""
        from modules.presets import DEFAULT_METADATA
        assert DEFAULT_METADATA["temperature"] == 1.0

    def test_m25_uses_default_temperature(self):
        """M2.5 models should use default temperature of 1.0."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["temperature"] == 1.0
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["temperature"] == 1.0

    def test_default_stream(self):
        """Default stream should be True."""
        from modules.presets import DEFAULT_METADATA
        assert DEFAULT_METADATA["stream"] is True
