import io
import logging
from typing import Tuple

from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

from .base import InputProcessor

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False
    logger.info("OpenCV not installed; image preprocessing uses PIL only")


class ImageProcessor(InputProcessor):
    """OCR for images via pytesseract with quality-aware preprocessing."""

    supported_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
        "image/bmp",
    }

    async def extract_text(self, file_bytes: bytes, content_type: str, filename: str | None = None) -> str:
        image = Image.open(io.BytesIO(file_bytes))
        return self._process_image(image)

    def _process_image(self, image: Image.Image) -> str:
        """Run full preprocessing + OCR pipeline, with an alternative fallback."""
        preprocessed = self._preprocess(image)
        text, confidence = self._ocr_with_quality(preprocessed)

        if confidence < 50 and text:
            alt = self._alternative_preprocess(image)
            alt_text, alt_conf = self._ocr_with_quality(alt)
            if alt_conf > confidence:
                text, confidence = alt_text, alt_conf
                logger.info("Alternative preprocessing improved OCR confidence to %.1f", alt_conf)

        logger.info("OCR final: %d chars, confidence=%.1f", len(text), confidence)
        return text

    # ── Preprocessing pipelines ──

    def _preprocess(self, image: Image.Image) -> Image.Image:
        """Primary pipeline: deskew → grayscale → denoise → contrast stretch → adaptive threshold → upscale → contrast."""
        image = self._deskew(image)
        image = self._to_grayscale(image)
        image = self._denoise(image)
        image = self._stretch_contrast(image)  # pull dark/light apart before thresholding
        image = self._adaptive_threshold(image)
        image = self._upscale_if_needed(image)
        image = self._enhance_contrast(image, factor=1.3)
        return image

    def _alternative_preprocess(self, image: Image.Image) -> Image.Image:
        """Fallback pipeline without thresholding — better for high-contrast screenshots."""
        image = self._to_grayscale(image)
        image = self._denoise(image)
        image = self._upscale_if_needed(image)
        image = self._enhance_contrast(image, factor=1.8)
        return image

    # ── Individual steps ──

    def _deskew(self, image: Image.Image) -> Image.Image:
        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            angle = osd.get("rotate", 0)
            if angle and angle != 0:
                logger.debug("Deskewing by %d degrees", angle)
                return image.rotate(-angle, fillcolor="white", expand=True)
        except Exception as exc:
            logger.debug("Deskewing skipped: %s", exc)
        return image

    def _to_grayscale(self, image: Image.Image) -> Image.Image:
        return image.convert("L") if image.mode != "L" else image

    def _denoise(self, image: Image.Image) -> Image.Image:
        if _HAS_CV2:
            arr = np.array(image)
            denoised = cv2.fastNlMeansDenoising(
                arr, None, h=10, templateWindowSize=7, searchWindowSize=21
            )
            return Image.fromarray(denoised)
        # PIL fallback
        return image.filter(ImageFilter.MedianFilter(size=3))

    def _adaptive_threshold(self, image: Image.Image) -> Image.Image:
        if not _HAS_CV2:
            return image
        arr = np.array(image)
        thresh = cv2.adaptiveThreshold(
            arr,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )
        return Image.fromarray(thresh)

    def _upscale_if_needed(self, image: Image.Image, min_dim: int = 1200) -> Image.Image:
        w, h = image.size
        if w < min_dim or h < min_dim:
            scale = min_dim / min(w, h)
            new_size = (int(w * scale), int(h * scale))
            return image.resize(new_size, Image.LANCZOS)
        return image

    def _enhance_contrast(self, image: Image.Image, factor: float = 1.5) -> Image.Image:
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)

    def _stretch_contrast(self, image: Image.Image) -> Image.Image:
        """Normalize image to use full 0-255 range before thresholding."""
        if _HAS_CV2:
            arr = np.array(image)
            normalized = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX)
            return Image.fromarray(normalized)
        # PIL fallback: auto-contrast
        from PIL import ImageOps
        return ImageOps.autocontrast(image, cutoff=1)

    # ── OCR with per-word confidence ──

    def _ocr_with_quality(self, image: Image.Image, lang: str = "eng+deu") -> Tuple[str, float]:
        config = "--psm 6"  # assume single uniform block of text; fewer spurious words
        try:
            data = pytesseract.image_to_data(
                image, lang=lang, config=config, output_type=pytesseract.Output.DICT
            )
        except pytesseract.TesseractError:
            logger.warning("eng+deu tesseract language pack missing, falling back to eng")
            data = pytesseract.image_to_data(
                image, lang="eng", config=config, output_type=pytesseract.Output.DICT
            )

        words = []
        confidences = []
        for i, conf in enumerate(data["conf"]):
            if int(conf) > 30 and data["text"][i].strip():
                words.append(data["text"][i])
                confidences.append(int(conf))

        text = " ".join(words).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return text, avg_conf
