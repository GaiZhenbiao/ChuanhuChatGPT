import base64
import json
import logging
import os
import textwrap
import requests
from typing import List, Dict, Any, Generator

from ..utils import count_token
from ..index_func import construct_index
from ..presets import i18n
from .base_model import BaseLLMModel


class GoogleGeminiClient(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name, config={"api_key": api_key})
        # Determine if this is a multimodal model
        if "vision" in model_name.lower() or "pro" in model_name.lower() or "flash" in model_name.lower():
            self.multimodal = True
        else:
            self.multimodal = False

        self.image_paths = []
        self.api_host = os.environ.get("GOOGLE_GENAI_API_HOST", self.api_host or "generativelanguage.googleapis.com")
        self.api_version = "v1beta"
        self.base_url = f"https://{self.api_host}/{self.api_version}"

        # Safety settings
        self.safetySettings = None

        # Additional generation config parameters
        self.stopSequences = None
        self.topK = 40  # Default value
        self.seed = None
        self.presencePenalty = None
        self.frequencyPenalty = None

    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encode an image file to base64 string"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _get_mime_type(self, image_path: str) -> str:
        """Determine MIME type from file extension"""
        ext = os.path.splitext(image_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            return "image/jpeg"
        elif ext == '.png':
            return "image/png"
        elif ext == '.webp':
            return "image/webp"
        elif ext == '.heic':
            return "image/heic"
        elif ext == '.heif':
            return "image/heif"
        else:
            logging.warning(f"Unsupported image format: {ext}. Using JPEG as default.")
            return "image/jpeg"

    def _prepare_request_payload(self, stream: bool = False) -> Dict[str, Any]:
        """Prepare the request payload for the Gemini API"""
        # Initialize parts and image buffer
        parts = []
        image_buffer = []
        processed_images = []

        # Process history with image buffering (similar to OpenAIVisionClient)
        for item in self.history:
            if item["role"] == "user":
                # For user messages, add any buffered images first, then the text
                user_content = []

                # Add any buffered images to the parts list
                for image_path in image_buffer:
                    if image_path not in processed_images:
                        mime_type = self._get_mime_type(image_path)
                        image_data = self._encode_image_to_base64(image_path)

                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_data
                            }
                        })
                        processed_images.append(image_path)

                # Now add the user text
                if isinstance(item["content"], list):
                    # Handle multimodal content (text + images)
                    text_content = item["content"][0]["text"]
                    parts.append({"text": text_content})
                else:
                    # Regular text content
                    parts.append({"text": item["content"]})

                # Clear the image buffer after processing a user message
                image_buffer = []

            elif item["role"] == "assistant":
                # Add assistant responses as text
                parts.append({"text": item["content"]})

            elif item["role"] == "image":
                # For image messages, add to the buffer
                image_path = item["content"]
                image_buffer.append(image_path)

        # Add any remaining buffered images that weren't associated with a user message
        for image_path in image_buffer:
            if image_path not in processed_images:
                mime_type = self._get_mime_type(image_path)
                image_data = self._encode_image_to_base64(image_path)

                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_data
                    }
                })
                processed_images.append(image_path)

        # Add any new images from self.image_paths that weren't already processed
        for image_path in self.image_paths:
            if image_path not in processed_images:
                mime_type = self._get_mime_type(image_path)
                image_data = self._encode_image_to_base64(image_path)

                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_data
                    }
                })
                processed_images.append(image_path)

        # Reset image_paths after processing
        self.image_paths = []

        # Build the generation config
        generation_config = {
            "temperature": self.temperature,
            "topP": self.top_p,
            "candidateCount": self.n_choices,
        }

        # Add optional generation config parameters if set
        if self.max_generation_token:
            generation_config["maxOutputTokens"] = self.max_generation_token

        if self.stop_sequence:
            generation_config["stopSequences"] = self.stop_sequence

        if self.seed:
            generation_config["seed"] = self.seed

        if self.presence_penalty:
            generation_config["presencePenalty"] = self.presence_penalty

        if self.frequency_penalty:
            generation_config["frequencyPenalty"] = self.frequency_penalty

        # Build the complete payload
        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": generation_config
        }

        # Add system prompt if provided
        if self.system_prompt:
            payload["system_instruction"] = {"parts": [{"text": self.system_prompt}]}

        return payload

    def _send_request(self, payload: Dict[str, Any], stream: bool = False) -> requests.Response:
        """Send request to the Gemini API"""
        headers = {"Content-Type": "application/json"}

        try:
            if stream:
                # Use streamGenerateContent endpoint with SSE format for streaming
                url = f"{self.base_url}/models/{self.model_name}:streamGenerateContent?alt=sse&key={self.api_key}"
            else:
                # Use regular generateContent endpoint for non-streaming
                url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=stream,
                timeout=60
            )

            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Error making request to Gemini API: {e}")
            raise

    def _process_streaming_response(self, response: requests.Response) -> Generator[str, None, None]:
        """Process streaming response from the Gemini API in SSE format"""
        partial_text = ""
        for line in response.iter_lines():
            if not line:
                continue

            # Parse SSE format - lines starting with "data: "
            if line.startswith(b'data: '):
                line = line[6:]

                # Skip "[DONE]" marker
                if line == b'[DONE]':
                    continue

                try:
                    chunk = json.loads(line)
                    # Process chunks that contain text content
                    if "candidates" in chunk and chunk["candidates"]:
                        for candidate in chunk["candidates"]:
                            if "content" in candidate and "parts" in candidate["content"]:
                                for part in candidate["content"]["parts"]:
                                    if "text" in part:
                                        partial_text += part["text"]
                                        yield partial_text
                except json.JSONDecodeError as e:
                    # Skip parsing errors but log them
                    logging.warning(f"Failed to parse JSON from SSE chunk: {e}")
                    continue

        # Ensure the final text is yielded
        if partial_text:
            yield partial_text

    def _process_response(self, response: requests.Response) -> str:
        """Process non-streaming response from the Gemini API"""
        try:
            data = response.json()

            if "candidates" in data and data["candidates"]:
                text = ""
                for candidate in data["candidates"]:
                    if "content" in candidate and "parts" in candidate["content"]:
                        for part in candidate["content"]["parts"]:
                            if "text" in part:
                                text += part["text"]
                return text

            # Handle error cases
            if "promptFeedback" in data:
                return i18n("由于下面的原因，Google 拒绝返回 Gemini 的回答：\n\n") + str(data["promptFeedback"])

            return i18n("未能从 Gemini API 获取有效响应")
        except Exception as e:
            logging.error(f"Error processing Gemini API response: {e}")
            return f"Error: {str(e)}"

    def get_answer_at_once(self):
        """Get complete answer at once (non-streaming)"""
        try:
            payload = self._prepare_request_payload(stream=False)
            response = self._send_request(payload, stream=False)
            text = self._process_response(response)
            token_count = count_token(text)
            return text, token_count
        except Exception as e:
            logging.error(f"Error in get_answer_at_once: {e}")
            return f"Error: {str(e)}", 0

    def get_answer_stream_iter(self):
        """Get streaming answer iterator"""
        try:
            payload = self._prepare_request_payload(stream=True)
            response = self._send_request(payload, stream=True)

            final_text = ""
            for partial_text in self._process_streaming_response(response):
                final_text = partial_text
                yield partial_text

            # Update token count at the end
            if final_text and len(self.all_token_counts) > 0:
                self.all_token_counts[-1] = count_token(final_text)
        except Exception as e:
            logging.error(f"Error in get_answer_stream_iter: {e}")
            yield f"Error: {str(e)}"
