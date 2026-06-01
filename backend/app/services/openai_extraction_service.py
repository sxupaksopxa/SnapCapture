import base64
import json
import logging
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from app.models import ExtractedItem
from app.services.extraction.utils import normalize_date, ensure_required_dates

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"


def _today_prefix():
    return f"Today is {datetime.now().strftime('%d %B %Y')}. "

_SYSTEM_PROMPT = (
    "You are SnapCapture, an AI assistant that extracts actionable tasks and "
    "calendar events from user input.\n\n"
    "Return ONLY valid JSON.\n\n"
    "Rules:\n"
    "- If the text contains an action without fixed date/time, create a task.\n"
    "- If the text contains an appointment, meeting, call, visit, or scheduled item with BOTH a specific date AND a specific time, create an event.\n"
    "- An action that has a deadline date but NO specific time (e.g., 'call Anna tomorrow', 'submit report by Friday') is a TASK, not an event.\n"
    "- If the text is only informational and no action is needed, return an empty items array.\n"
    "- Normalize relative dates into dd.mm.yyyy format whenever you can confidently calculate them.\n"
    "- For relative dates like 'next Friday', 'tomorrow', or 'before Monday', compute the actual calendar date and put it in date (for events) or due_date (for tasks).\n"
    "- Only use original_date to store the raw wording when you cannot confidently calculate the exact date.\n"
    "- Preserve the exact original date/time wording in original_date as a fallback.\n"
    "- Examples of original_date: 'Friday', 'next Friday afternoon', 'Monday at 11', 'tomorrow morning', 'before June', '28 May at 10:30'.\n"
    "- For events, put the normalized date in date using dd.mm.yyyy format. date is REQUIRED for every event.\n"
    "- For tasks, put the normalized deadline in due_date using dd.mm.yyyy format. due_date is REQUIRED for every task.\n"
    "- If the year is missing in a date (e.g., '03.06.'), assume the current year 2026.\n"
    "- If no explicit date is given for a task, assume today as the due_date.\n"
    "- If no explicit date is given for an event, assume today as the date.\n"
    "- Use time only when the input explicitly contains a time, for example '11:00', '14:30', or '9:00 to 12:00'.\n"
    "- If the date is truly ambiguous and you cannot calculate it, keep date/due_date as null and store the wording in original_date.\n"
    "- CRITICAL: Any date or time mentioned in the input MUST be captured in original_date, original_date must NEVER be null when a date or time appears in the text.\n"
    "- CRITICAL: Never put date or time information into the note field. note is only for extra context that is not a date, time, or location.\n"
    "- A scheduled appointment, meeting, or call that has BOTH a confirmed date AND a specific time is an event, not a task.\n"
    "- If the input contains multiple independent actions or items, create a separate item for each one.\n"
    "- If the input contains multiple dates and times, create a separate event for each date/time combination.\n"
    "- Phrases like 'meeting on Friday at 15:00', 'appointment scheduled at 14:30', or 'call with Peter at 11:00' indicate a scheduled event.\n"
    "- Phrases like 'call Anna tomorrow', 'submit report by Friday', or 'buy groceries before Monday' indicate a task with a deadline.\n"
    "- Phone calls, follow-ups, requests, and actions without any date or time should be tasks.\n"
    "- Events should represent scheduled appointments, meetings, visits, conferences, or calendar-specific activities.\n"
    "- Only create an event when the appointment or meeting has a specific or relative date/time attached.\n"
    "- Use time for explicit or clearly implied time ranges such as 'afternoon' = '12:00-17:00'.\n"
    "- Use null when information is missing.\n"
    "- Use note only for extra useful details that are not the title, date, time, or location.\n"
    "- CRITICAL: The title must describe the primary action, subject, or meeting. Include key people and main topics in the title.\n"
    "- CRITICAL: Never put the main action, primary subject, or key people into the note. The note is for supplementary context only.\n"
    "- If the input describes a call, meeting, or appointment with someone, that interaction belongs in the title, not the note.\n"
    "- Keep notes short.\n"
    "- Confidence must be between 0 and 1.\n\n"
    "Required JSON format:\n"
    '{\n'
    '  "items": [\n'
    '    {\n'
    '      "type": "task",\n'
    '      "title": "short clear title",\n'
    '      "original_date": "original date/time wording from input or null",\n'
    '      "due_date": "original task deadline text or null",\n'
    '      "date": null,\n'
    '      "time": null,\n'
    '      "location": null,\n'
    '      "confidence": 0.95\n'
    '      "note": "short additional note or null",\n'
    '    },\n'
    '    {\n'
    '      "type": "event",\n'
    '      "title": "short clear title",\n'
    '      "original_date": "original date/time wording from input or null",\n'
    '      "due_date": null,\n'
    '      "date": "original event date text or null",\n'
    '      "time": "event time or null",\n'
    '      "location": "location or null",\n'
    '      "confidence": 0.88\n'
    '      "note": "short additional note or null",\n'
    '    }\n'
    '  ]\n'
    '}\n'
)

_REFINE_SYSTEM_PROMPT = (
    "You are SnapCapture, an AI assistant that corrects poorly extracted tasks and events.\n\n"
    "The source context below was produced by OCR or speech-to-text and contains spelling errors, "
    "garbled words, and incorrect capitalization. Your job is to infer the INTENDED words and "
    "produce a corrected extraction. Do NOT simply repeat the input.\n\n"
    "Common OCR errors to fix:\n"
    "- Mixed or random capitalization (e.g., 'cappeLLA' → 'Cappella', 'PICCOM' → 'Piccola')\n"
    "- Letter substitutions (m/n, c/e, i/l, o/a, rn/m)\n"
    "- Missing or extra spaces (e.g., 'PICCOMLeitung' → 'Piccola Leitung')\n"
    "- Numbers misread as letters and vice versa\n\n"
    "Return ONLY valid JSON with the corrected item in this exact format:\n"
    '{\n'
    '  "type": "task" or "event",\n'
    '  "title": "corrected title",\n'
    '  "original_date": "original date wording or null",\n'
    '  "due_date": "original task deadline or null",\n'
    '  "date": "explicit calendar date or null",\n'
    '  "time": "explicit time or null",\n'
    '  "location": "location or null",\n'
    '  "confidence": 0.95,\n'
    '  "note": "short note or null"\n'
    '}\n'
    "\nRules:\n"
    "- Fix spelling and capitalization errors intelligently.\n"
    "- Preserve the exact original date/time wording in original_date.\n"
    "- CRITICAL: Any date or time mentioned in the source MUST be captured in original_date. original_date must NEVER be null when a date or time appears in the text.\n"
    "- CRITICAL: Never put date or time information into the note field.\n"
    "- CRITICAL: The title must describe the primary action, subject, or meeting. Include key people and main topics in the title.\n"
    "- CRITICAL: Never put the main action, primary subject, or key people into the note. The note is for supplementary context only.\n"
    "- A scheduled appointment, meeting, or call that has BOTH a confirmed date AND a specific time is an event, not a task.\n"
    "- If the input contains multiple independent actions or items, create a separate item for each one.\n"
    "- If the input contains multiple dates and times, create a separate event for each date/time combination.\n"
    "- Phrases like 'meeting on Friday at 15:00', 'appointment scheduled at 14:30', or 'call with Peter at 11:00' indicate a scheduled event.\n"
    "- Phrases like 'call Anna tomorrow', 'submit report by Friday', or 'buy groceries before Monday' indicate a task with a deadline.\n"
    "- For events, put the normalized date in date using dd.mm.yyyy format. date is REQUIRED for every event.\n"
    "- For tasks, put the normalized deadline in due_date using dd.mm.yyyy format. due_date is REQUIRED for every task.\n"
    "- If the year is missing in a date (e.g., '03.06.'), assume the current year 2026.\n"
    "- If no explicit date is given for a task, assume today as the due_date.\n"
    "- If no explicit date is given for an event, assume today as the date.\n"
    "- Use time only for explicit times (e.g., '11:00').\n"
    "- Do not guess missing information.\n"
    "- Keep notes short.\n"
)

_VISION_SYSTEM_PROMPT = (
    "You are SnapCapture, an AI assistant that extracts tasks and events from documents.\n\n"
    "Look at the image and extract tasks and events.\n\n"
    "Return ONLY valid JSON with the corrected item in this exact format:\n"
    '{\n'
    '  "items": [\n'
    '    {\n'
    '      "type": "task" or "event",\n'
    '      "title": "short clear title",\n'
    '      "original_date": "original date wording or null",\n'
    '      "due_date": "original task deadline or null",\n'
    '      "date": "explicit calendar date or null",\n'
    '      "time": "explicit time or null",\n'
    '      "location": "location or null",\n'
    '      "confidence": 0.95,\n'
    '      "note": "short note or null"\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "\nRules:\n"
    "- Preserve the exact original date/time wording in original_date.\n"
    "- CRITICAL: Any date or time mentioned in the source MUST be captured in original_date. original_date must NEVER be null when a date or time appears in the text.\n"
    "- CRITICAL: Never put date or time information into the note field.\n"
    "- CRITICAL: The title must describe the primary action, subject, or meeting. Include key people and main topics in the title.\n"
    "- CRITICAL: Never put the main action, primary subject, or key people into the note. The note is for supplementary context only.\n"
    "- A scheduled appointment, meeting, or call that has BOTH a confirmed date AND a specific time is an event, not a task.\n"
    "- If the input contains multiple independent actions or items, create a separate item for each one.\n"
    "- If the input contains multiple dates and times, create a separate event for each date/time combination.\n"
    "- Phrases like 'meeting on Friday at 15:00', 'appointment scheduled at 14:30', or 'call with Peter at 11:00' indicate a scheduled event.\n"
    "- Phrases like 'call Anna tomorrow', 'submit report by Friday', or 'buy groceries before Monday' indicate a task with a deadline.\n"
    "- For events, put the normalized date in date using dd.mm.yyyy format. date is REQUIRED for every event.\n"
    "- For tasks, put the normalized deadline in due_date using dd.mm.yyyy format. due_date is REQUIRED for every task.\n"
    "- If the year is missing in a date (e.g., '03.06.'), assume the current year 2026.\n"
    "- If no explicit date is given for a task, assume today as the due_date.\n"
    "- If no explicit date is given for an event, assume today as the date.\n"
    "- Use time only for explicit times (e.g., '11:00').\n"
    "- Do not guess missing information.\n"
    "- Keep notes short.\n"
)


def _clean_json_response(content: str) -> str:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content)
    return content.strip()


def _parse_items_json(raw: str) -> list[dict]:
    cleaned = _clean_json_response(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return items


def _normalize_extracted_item(item: dict) -> ExtractedItem | None:
    try:
        extracted = ExtractedItem(**item)
        normalized_date, normalized_time = normalize_date(extracted.original_date)
        if normalized_date:
            if extracted.type == "event" and not extracted.date:
                extracted.date = normalized_date
            if extracted.type == "task" and not extracted.due_date:
                extracted.due_date = normalized_date
        if normalized_time and not extracted.time:
            extracted.time = normalized_time
        ensure_required_dates(extracted)
        return extracted
    except Exception as exc:
        logger.warning("Skipping invalid OpenAI item: %s", exc)
        return None


class OpenAIExtractionService:
    """Extract tasks and events using OpenAI GPT-4o-mini."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        load_dotenv()
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set and no api_key was provided"
            )
        self._client = OpenAI(api_key=self._api_key)
        self._model = model

    def extract_items_from_text(self, text: str) -> list[ExtractedItem]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _today_prefix() + _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Input:\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("OpenAI API call failed: %s", exc)
            return []

        raw = response.choices[0].message.content
        if not raw:
            logger.warning("OpenAI returned empty response")
            return []

        try:
            items = _parse_items_json(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse OpenAI JSON: %s", exc)
            return []

        results: list[ExtractedItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            extracted = _normalize_extracted_item(item)
            if extracted:
                results.append(extracted)
        return results

    def extract_items_from_file_bytes(self, file_bytes: bytes, content_type: str) -> list[ExtractedItem]:
        """Vision fallback for images. For PDFs, extracts text locally then processes as text."""
        if content_type.startswith("image/"):
            return self._extract_from_image(file_bytes, content_type)

        if content_type == "application/pdf":
            # 1) Try embedded text extraction first
            try:
                import pdfplumber
                import io
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    texts = [page.extract_text() or "" for page in pdf.pages]
                extracted_text = "\n".join(texts).strip()
                if extracted_text:
                    return self.extract_items_from_text(extracted_text)
            except Exception as exc:
                logger.warning("PDF text extraction for OpenAI fallback failed: %s", exc)

            # 2) No embedded text — convert pages to images and use vision
            logger.info("PDF has no embedded text — converting pages to images for OpenAI vision")
            try:
                import fitz
                from PIL import Image
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                image_parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    image_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
                doc.close()

                if image_parts:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": _today_prefix() + _VISION_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": image_parts,
                            },
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        timeout=30.0,
                    )
                    raw = response.choices[0].message.content
                    if raw:
                        items = _parse_items_json(raw)
                        results: list[ExtractedItem] = []
                        for item in items:
                            if isinstance(item, dict):
                                extracted = _normalize_extracted_item(item)
                                if extracted:
                                    results.append(extracted)
                        return results
            except Exception as exc:
                logger.warning("OpenAI vision fallback for scanned PDF failed: %s", exc)

        logger.warning("OpenAI vision fallback not supported for %s", content_type)
        return []

    def _extract_from_image(self, file_bytes: bytes, mime_type: str) -> list[ExtractedItem]:
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _today_prefix() + _VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("OpenAI vision call failed: %s", exc)
            return []

        raw = response.choices[0].message.content
        if not raw:
            logger.warning("OpenAI vision returned empty response")
            return []

        try:
            items = _parse_items_json(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse OpenAI vision JSON: %s", exc)
            return []

        results: list[ExtractedItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            extracted = _normalize_extracted_item(item)
            if extracted:
                results.append(extracted)
        return results

    def refine_item(self, item: ExtractedItem, source_text: str) -> ExtractedItem | None:
        prompt = (
            f"Source context:\n{source_text}\n\n"
            f"Poorly extracted item:\n"
            f"- type: {item.type}\n"
            f"- title: {item.title}\n"
            f"- original_date: {item.original_date or 'null'}\n"
            f"- due_date: {item.due_date or 'null'}\n"
            f"- date: {item.date or 'null'}\n"
            f"- time: {item.time or 'null'}\n"
            f"- location: {item.location or 'null'}\n"
            f"- note: {item.note or 'null'}\n\n"
            "Return ONLY valid JSON with the corrected item."
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _today_prefix() + _REFINE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("OpenAI refine call failed: %s", exc)
            return None

        raw = response.choices[0].message.content
        if not raw:
            logger.warning("OpenAI refine returned empty response")
            return None

        try:
            cleaned = _clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse OpenAI refine JSON: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        return _normalize_extracted_item(data)

    def refine_item_with_vision(
        self, item: ExtractedItem, file_bytes: bytes, content_type: str
    ) -> ExtractedItem | None:
        if content_type == "application/pdf":
            # 1) Try embedded text extraction first
            try:
                import pdfplumber
                import io
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    texts = [page.extract_text() or "" for page in pdf.pages]
                extracted_text = "\n".join(texts).strip()
                if extracted_text:
                    return self.refine_item(item, extracted_text)
            except Exception as exc:
                logger.warning("PDF text extraction for OpenAI vision refine failed: %s", exc)

            # 2) No embedded text — convert pages to images and use vision
            logger.info("PDF has no embedded text — converting pages to images for OpenAI vision refine")
            try:
                import fitz
                from PIL import Image
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                image_parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    image_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
                doc.close()

                if image_parts:
                    prompt = (
                        f"The current (incorrect) extraction has:\n"
                        f"- type: {item.type}\n"
                        f"- title: {item.title}\n"
                        f"- original_date: {item.original_date or 'null'}\n"
                        f"- due_date: {item.due_date or 'null'}\n"
                        f"- date: {item.date or 'null'}\n"
                        f"- time: {item.time or 'null'}\n"
                        f"- location: {item.location or 'null'}\n"
                        f"- note: {item.note or 'null'}\n\n"
                        "Return ONLY valid JSON with the corrected item."
                    )
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": _today_prefix() + _VISION_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    *image_parts,
                                ],
                            },
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        timeout=30.0,
                    )
                    raw = response.choices[0].message.content
                    if raw:
                        cleaned = _clean_json_response(raw)
                        data = json.loads(cleaned)
                        if isinstance(data, dict):
                            # Vision prompt returns {"items": [...]}; unwrap first item
                            if "items" in data and isinstance(data["items"], list) and data["items"]:
                                return _normalize_extracted_item(data["items"][0])
                            return _normalize_extracted_item(data)
            except Exception as exc:
                logger.warning("OpenAI vision refine for scanned PDF failed: %s", exc)
            return None

        if not content_type.startswith("image/"):
            logger.warning("OpenAI vision refine only supports images, got %s", content_type)
            return None

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64}"

        prompt = (
            f"The current (incorrect) extraction has:\n"
            f"- type: {item.type}\n"
            f"- title: {item.title}\n"
            f"- original_date: {item.original_date or 'null'}\n"
            f"- due_date: {item.due_date or 'null'}\n"
            f"- date: {item.date or 'null'}\n"
            f"- time: {item.time or 'null'}\n"
            f"- location: {item.location or 'null'}\n"
            f"- note: {item.note or 'null'}\n\n"
            "Return ONLY valid JSON with the corrected item."
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _today_prefix() + _VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("OpenAI vision refine failed: %s", exc)
            return None

        raw = response.choices[0].message.content
        if not raw:
            logger.warning("OpenAI vision refine returned empty response")
            return None

        try:
            cleaned = _clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse OpenAI vision refine JSON: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        # Vision prompt returns {"items": [...]}; unwrap first item
        if "items" in data and isinstance(data["items"], list) and data["items"]:
            return _normalize_extracted_item(data["items"][0])
        return _normalize_extracted_item(data)
