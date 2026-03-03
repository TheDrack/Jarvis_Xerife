# -*- coding: utf-8 -*-
"""Vision Adapter - Computer vision integration via Gemini 1.5 Flash.

Captures the current visual context (screenshot or webcam frame) and sends it
to Gemini for a one-sentence description so that JARVIS can understand what the
user is looking at / doing right now.

Implements :class:`app.core.nexuscomponent.NexusComponent`.
"""

import base64
import logging
import os
from typing import Any, Dict, Optional

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

# Gemini model preferred for vision tasks
_VISION_MODEL = "gemini-1.5-flash"

# Prompt sent together with the image
_DESCRIBE_PROMPT = "Descreva o contexto atual do usuário em 1 frase."


class VisionAdapter(NexusComponent):
    """
    Adapter for visual context acquisition.

    On :meth:`capture_and_analyze`, the adapter:
    1. Takes a silent screenshot (or webcam frame if ``use_webcam=True``).
    2. Sends the image to Gemini 1.5 Flash with a short description prompt.
    3. Returns the one-sentence description.

    Args:
        api_key: Google Gemini API key (defaults to ``GEMINI_API_KEY`` env var).
        use_webcam: When True, capture from the default webcam instead of screenshot.
        vision_model: Gemini model to use (default: ``gemini-1.5-flash``).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        use_webcam: bool = False,
        vision_model: str = _VISION_MODEL,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._use_webcam = use_webcam
        self._vision_model = vision_model

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Capture and analyze the current visual context."""
        description = self.capture_and_analyze()
        return {"success": description is not None, "description": description}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture_and_analyze(self, prompt: str = _DESCRIBE_PROMPT) -> Optional[str]:
        """
        Capture the current screen (or webcam) and return a Gemini description.

        Args:
            prompt: The analysis prompt sent to Gemini alongside the image.

        Returns:
            A one-sentence description of the visual context, or ``None`` on failure.
        """
        image_bytes = self._capture_image()
        if image_bytes is None:
            logger.warning("🙈 [VisionAdapter] Nenhuma imagem capturada. Análise abortada.")
            return None

        return self._analyze_with_gemini(image_bytes, prompt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _capture_image(self) -> Optional[bytes]:
        """Capture a screenshot or webcam frame and return raw PNG bytes."""
        if self._use_webcam:
            return self._capture_webcam()
        return self._capture_screenshot()

    def _capture_screenshot(self) -> Optional[bytes]:
        """Take a silent screenshot using Pillow / mss (if available)."""
        # Try mss (fastest, no dependencies besides itself)
        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                sct_img = sct.grab(monitor)
                return mss.tools.to_png(sct_img.rgb, sct_img.size)
        except Exception:
            pass

        # Fallback: Pillow ImageGrab
        try:
            import io
            from PIL import ImageGrab

            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.warning("📸 [VisionAdapter] Screenshot falhou: %s", e)
            return None

    def _capture_webcam(self) -> Optional[bytes]:
        """Capture a single frame from the default webcam using OpenCV."""
        try:
            import io
            import cv2
            from PIL import Image

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.warning("📷 [VisionAdapter] Webcam não encontrada.")
                return None
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return None
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_frame)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.warning("📷 [VisionAdapter] Erro ao capturar webcam: %s", e)
            return None

    def _analyze_with_gemini(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        """Send *image_bytes* to Gemini and return the text response."""
        if not self._api_key:
            logger.error("❌ [VisionAdapter] GEMINI_API_KEY não configurada.")
            return None

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key)
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            response = client.models.generate_content(
                model=self._vision_model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                            types.Part.from_text(text=prompt),
                        ],
                    )
                ],
            )
            description = response.text.strip() if response.text else None
            logger.info("👁️ [VisionAdapter] Contexto visual: %s", description)
            return description
        except Exception as e:
            logger.error("❌ [VisionAdapter] Erro ao analisar imagem com Gemini: %s", e)
            return None
