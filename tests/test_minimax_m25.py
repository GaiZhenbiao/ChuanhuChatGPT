"""Unit tests for MiniMax provider integration (M2.5 and M2.7 models)."""

import pytest


class TestMiniMaxM25ModelType:
    """Test MiniMaxM25 ModelType enum and type detection."""

    def test_minimax_m25_enum_exists(self):
        """MiniMaxM25 enum value should exist in ModelType."""
        from modules.models.base_model import ModelType
        assert hasattr(ModelType, "MiniMaxM25")
        assert isinstance(ModelType.MiniMaxM25.value, int)

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

    def test_minimax_m27_type_detection(self):
        """MiniMax-M2.7 should be detected as MiniMaxM25 type via metadata."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.7")
        assert model_type == ModelType.MiniMaxM25

    def test_minimax_m27_highspeed_type_detection(self):
        """MiniMax-M2.7-highspeed should be detected as MiniMaxM25 type via metadata."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.7-highspeed")
        assert model_type == ModelType.MiniMaxM25

    def test_old_minimax_type_detection(self):
        """Old minimax-abab5-chat should still be detected as Minimax type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("minimax-abab5-chat")
        assert model_type == ModelType.Minimax


class TestMiniMaxModelMetadata:
    """Test MiniMax model metadata configuration."""

    def test_m25_in_online_models(self):
        """MiniMax-M2.5 should be in ONLINE_MODELS list."""
        from modules.presets import ONLINE_MODELS
        assert "MiniMax-M2.5" in ONLINE_MODELS
        assert "MiniMax-M2.5-highspeed" in ONLINE_MODELS

    def test_m27_in_online_models(self):
        """MiniMax-M2.7 should be in ONLINE_MODELS list."""
        from modules.presets import ONLINE_MODELS
        assert "MiniMax-M2.7" in ONLINE_MODELS
        assert "MiniMax-M2.7-highspeed" in ONLINE_MODELS

    def test_m27_listed_before_m25(self):
        """MiniMax-M2.7 should appear before M2.5 in ONLINE_MODELS (newest first)."""
        from modules.presets import ONLINE_MODELS
        idx_m27 = ONLINE_MODELS.index("MiniMax-M2.7")
        idx_m25 = ONLINE_MODELS.index("MiniMax-M2.5")
        assert idx_m27 < idx_m25

    def test_m25_metadata_exists(self):
        """MiniMax-M2.5 should have metadata entry."""
        from modules.presets import MODEL_METADATA
        assert "MiniMax-M2.5" in MODEL_METADATA
        assert "MiniMax-M2.5-highspeed" in MODEL_METADATA

    def test_m27_metadata_exists(self):
        """MiniMax-M2.7 should have metadata entry."""
        from modules.presets import MODEL_METADATA
        assert "MiniMax-M2.7" in MODEL_METADATA
        assert "MiniMax-M2.7-highspeed" in MODEL_METADATA

    def test_m25_metadata_model_name(self):
        """Model name should be the API model ID."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["model_name"] == "MiniMax-M2.5"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["model_name"] == "MiniMax-M2.5-highspeed"

    def test_m27_metadata_model_name(self):
        """Model name should be the API model ID."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.7"]["model_name"] == "MiniMax-M2.7"
        assert MODEL_METADATA["MiniMax-M2.7-highspeed"]["model_name"] == "MiniMax-M2.7-highspeed"

    def test_m25_metadata_api_host(self):
        """API host should be the MiniMax OpenAI-compatible endpoint."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["api_host"] == "https://api.minimax.io"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["api_host"] == "https://api.minimax.io"

    def test_m27_metadata_api_host(self):
        """API host should be the MiniMax OpenAI-compatible endpoint."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.7"]["api_host"] == "https://api.minimax.io"
        assert MODEL_METADATA["MiniMax-M2.7-highspeed"]["api_host"] == "https://api.minimax.io"

    def test_m25_metadata_token_limit(self):
        """Token limit should be 204800 for M2.5 models."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["token_limit"] == 204800
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["token_limit"] == 204800

    def test_m27_metadata_token_limit(self):
        """Token limit should be 204800 for M2.7 models."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.7"]["token_limit"] == 204800
        assert MODEL_METADATA["MiniMax-M2.7-highspeed"]["token_limit"] == 204800

    def test_m25_metadata_model_type(self):
        """Model type should be MiniMaxM25."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["model_type"] == "MiniMaxM25"
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["model_type"] == "MiniMaxM25"

    def test_m27_metadata_model_type(self):
        """Model type should be MiniMaxM25 (same OpenAI-compatible API)."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.7"]["model_type"] == "MiniMaxM25"
        assert MODEL_METADATA["MiniMax-M2.7-highspeed"]["model_type"] == "MiniMaxM25"

    def test_m25_metadata_not_multimodal(self):
        """M2.5 models should not be multimodal."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.5"]["multimodal"] is False
        assert MODEL_METADATA["MiniMax-M2.5-highspeed"]["multimodal"] is False

    def test_m27_metadata_not_multimodal(self):
        """M2.7 models should not be multimodal."""
        from modules.presets import MODEL_METADATA
        assert MODEL_METADATA["MiniMax-M2.7"]["multimodal"] is False
        assert MODEL_METADATA["MiniMax-M2.7-highspeed"]["multimodal"] is False

    def test_m25_metadata_has_description(self):
        """M2.5 models should have descriptions."""
        from modules.presets import MODEL_METADATA
        assert len(MODEL_METADATA["MiniMax-M2.5"]["description"]) > 0
        assert len(MODEL_METADATA["MiniMax-M2.5-highspeed"]["description"]) > 0

    def test_m27_metadata_has_description(self):
        """M2.7 models should have descriptions."""
        from modules.presets import MODEL_METADATA
        assert len(MODEL_METADATA["MiniMax-M2.7"]["description"]) > 0
        assert len(MODEL_METADATA["MiniMax-M2.7-highspeed"]["description"]) > 0

    def test_old_minimax_still_exists(self):
        """Old minimax-abab5-chat metadata should still exist."""
        from modules.presets import MODEL_METADATA
        assert "minimax-abab5-chat" in MODEL_METADATA


class TestMiniMaxApiHost:
    """Test API host URL formatting for MiniMax."""

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


class TestMiniMaxModelRouting:
    """Test model routing for MiniMax models in models.py."""

    def test_m25_resolves_to_minimax_m25_type(self):
        """MiniMax-M2.5 should resolve to MiniMaxM25 model type via get_type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.5")
        assert model_type == ModelType.MiniMaxM25

    def test_m25_highspeed_resolves_to_minimax_m25_type(self):
        """MiniMax-M2.5-highspeed should resolve to MiniMaxM25 model type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.5-highspeed")
        assert model_type == ModelType.MiniMaxM25

    def test_m27_resolves_to_minimax_m25_type(self):
        """MiniMax-M2.7 should resolve to MiniMaxM25 model type via get_type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.7")
        assert model_type == ModelType.MiniMaxM25

    def test_m27_highspeed_resolves_to_minimax_m25_type(self):
        """MiniMax-M2.7-highspeed should resolve to MiniMaxM25 model type."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("MiniMax-M2.7-highspeed")
        assert model_type == ModelType.MiniMaxM25

    def test_old_minimax_resolves_to_minimax_type(self):
        """Old minimax-abab5-chat should resolve to Minimax (not MiniMaxM25)."""
        from modules.models.base_model import ModelType
        model_type = ModelType.get_type("minimax-abab5-chat")
        assert model_type == ModelType.Minimax
        assert model_type != ModelType.MiniMaxM25


class TestMiniMaxDefaultConfig:
    """Test default configuration values for MiniMax models."""

    def test_default_temperature(self):
        """Default temperature should be 1.0 (from DEFAULT_METADATA)."""
        from modules.presets import DEFAULT_METADATA
        assert DEFAULT_METADATA["temperature"] == 1.0

    def test_m25_inherits_default_temperature(self):
        """M2.5 models should inherit default temperature after config merge."""
        from modules.presets import MODEL_METADATA, DEFAULT_METADATA
        default_temp = DEFAULT_METADATA["temperature"]
        m25_temp = MODEL_METADATA["MiniMax-M2.5"].get("temperature", default_temp)
        m25hs_temp = MODEL_METADATA["MiniMax-M2.5-highspeed"].get("temperature", default_temp)
        assert m25_temp == default_temp
        assert m25hs_temp == default_temp

    def test_m27_inherits_default_temperature(self):
        """M2.7 models should inherit default temperature after config merge."""
        from modules.presets import MODEL_METADATA, DEFAULT_METADATA
        default_temp = DEFAULT_METADATA["temperature"]
        m27_temp = MODEL_METADATA["MiniMax-M2.7"].get("temperature", default_temp)
        m27hs_temp = MODEL_METADATA["MiniMax-M2.7-highspeed"].get("temperature", default_temp)
        assert m27_temp == default_temp
        assert m27hs_temp == default_temp

    def test_default_stream(self):
        """Default stream should be True."""
        from modules.presets import DEFAULT_METADATA
        assert DEFAULT_METADATA["stream"] is True
