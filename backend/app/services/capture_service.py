import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.models import ExtractedItem
from app.services.extraction.utils import normalize_date, ensure_required_dates

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_GEMINI_TIMEOUT = 30  # seconds


def _today_prefix():
    return f"Today is {datetime.now().strftime('%d %B %Y')}. "


class GeminiExtractionService:
    """Extract tasks and events from text or file bytes using Gemini."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        load_dotenv()
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set and no api_key was provided"
            )
        self._client = genai.Client(api_key=self._api_key)
        self._model = model

    def _generate_with_timeout(self, fn, *args, **kwargs):
        """Run a blocking Gemini API call with a timeout."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=_GEMINI_TIMEOUT)
            except FutureTimeoutError:
                logger.warning("Gemini API call timed out after %s seconds", _GEMINI_TIMEOUT)
                raise TimeoutError(f"Gemini API call timed out after {_GEMINI_TIMEOUT} seconds")

    @staticmethod
    def _clean_json_response(content: str) -> str:
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
        return content.strip()

    @staticmethod
    def _build_system_text() -> str:
        return (
            _today_prefix()
            + "You are SnapCapture, an AI assistant that extracts actionable tasks and "
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

    def _extract_with_gemini_vision(
        self, file_bytes: bytes, content_type: str
    ) -> list[ExtractedItem]:
        """Send file directly to Gemini for multimodal extraction."""
        try:
            parts = [types.Part(text=self._build_system_text())]
            if content_type.startswith("image/"):
                parts.append(
                    types.Part.from_bytes(data=file_bytes, mime_type=content_type)
                )
            elif content_type == "application/pdf":
                parts.append(
                    types.Part.from_bytes(
                        data=file_bytes, mime_type="application/pdf"
                    )
                )
            else:
                logger.warning(
                    "Gemini vision fallback not supported for %s", content_type
                )
                return []

            response = self._generate_with_timeout(
                self._client.models.generate_content,
                model=self._model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.warning("Gemini vision fallback failed: %s", exc)
            return []

        raw = response.text
        if not raw:
            logger.warning("Gemini vision returned empty response")
            return []

        try:
            cleaned = self._clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Gemini vision JSON: %s", exc)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if not isinstance(data, dict):
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []

        results: list[ExtractedItem] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                extracted_item = ExtractedItem(**item)
                normalized_date, normalized_time = normalize_date(
                    extracted_item.original_date
                )
                if normalized_date:
                    if extracted_item.type == "event" and not extracted_item.date:
                        extracted_item.date = normalized_date
                    if extracted_item.type == "task" and not extracted_item.due_date:
                        extracted_item.due_date = normalized_date
                if normalized_time and not extracted_item.time:
                    extracted_item.time = normalized_time
                ensure_required_dates(extracted_item)
                results.append(extracted_item)
            except Exception as exc:
                logger.warning("Skipping invalid vision item at index %d: %s", idx, exc)
        return results

    def extract_items_from_text(self, text: str) -> list[ExtractedItem]:
        try:
            response = self._generate_with_timeout(
                self._client.models.generate_content,
                model=self._model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(text=self._build_system_text()),
                            types.Part(text=f"Input:\n{text}"),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.warning("Gemini API call failed: %s", exc)
            return []

        raw = response.text
        if not raw:
            logger.warning("Gemini returned empty or blocked response")
            return []

        try:
            cleaned = self._clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Gemini JSON response: %s", exc)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if not isinstance(data, dict):
            logger.warning("Unexpected Gemini response shape: not a dict")
            return []

        items = data.get("items")
        if not isinstance(items, list):
            logger.warning("Unexpected Gemini response shape: 'items' is not a list")
            return []

        results: list[ExtractedItem] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            try:
                extracted_item = ExtractedItem(**item)

                normalized_date, normalized_time = normalize_date(
                    extracted_item.original_date
                )

                if normalized_date:
                    if extracted_item.type == "event" and not extracted_item.date:
                        extracted_item.date = normalized_date
                    if extracted_item.type == "task" and not extracted_item.due_date:
                        extracted_item.due_date = normalized_date

                if normalized_time and not extracted_item.time:
                    extracted_item.time = normalized_time

                ensure_required_dates(extracted_item)

                results.append(extracted_item)

            except Exception as exc:
                logger.warning("Skipping invalid item at index %d: %s", idx, exc)

        return results

    def extract_items_from_file_bytes(self, file_bytes: bytes, content_type: str) -> list[ExtractedItem]:
        """Public entrypoint for Gemini vision fallback from the orchestrator."""
        return self._extract_with_gemini_vision(file_bytes, content_type)

    def refine_item(self, item: ExtractedItem, source_text: str) -> ExtractedItem | None:
        """Ask Gemini to correct a poorly extracted item using the original source context."""
        prompt = (
            _today_prefix()
            + "You are SnapCapture, an AI assistant that corrects poorly extracted tasks and events.\n\n"
            "The source context below was produced by OCR or speech-to-text and contains spelling errors, "
            "garbled words, and incorrect capitalization. Your job is to infer the INTENDED words and "
            "produce a corrected extraction. Do NOT simply repeat the input.\n\n"
            "Common OCR errors to fix:\n"
            "- Mixed or random capitalization (e.g., 'cappeLLA' → 'Cappella', 'PICCOM' → 'Piccola')\n"
            "- Letter substitutions (m/n, c/e, i/l, o/a, rn/m)\n"
            "- Missing or extra spaces (e.g., 'PICCOMLeitung' → 'Piccola Leitung')\n"
            "- Numbers misread as letters and vice versa\n\n"
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

        try:
            response = self._generate_with_timeout(
                self._client.models.generate_content,
                model=self._model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=prompt)],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.warning("Gemini refine call failed: %s", exc)
            return None

        raw = response.text
        if not raw:
            logger.warning("Gemini refine returned empty response")
            return None

        try:
            cleaned = self._clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Gemini refine JSON: %s", exc)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            else:
                return None

        if not isinstance(data, dict):
            return None

        try:
            refined = ExtractedItem(**data)
            normalized_date, normalized_time = normalize_date(refined.original_date)
            if normalized_date:
                if refined.type == "event" and not refined.date:
                    refined.date = normalized_date
                if refined.type == "task" and not refined.due_date:
                    refined.due_date = normalized_date
            if normalized_time and not refined.time:
                refined.time = normalized_time
            ensure_required_dates(refined)
            return refined
        except Exception as exc:
            logger.warning("Gemini refine produced invalid item: %s", exc)
            return None

    def refine_item_with_vision(
        self, item: ExtractedItem, file_bytes: bytes, content_type: str
    ) -> ExtractedItem | None:
        """Send the original file to Gemini vision to re-extract a single poorly extracted item."""
        prompt = (
            _today_prefix()
            + "You are SnapCapture, an AI assistant that extracts tasks and events from documents.\n\n"
            "The user uploaded a file and the local OCR produced a poor extraction. "
            "Look at the original file and extract the correct information.\n\n"
            f"The current (incorrect) extraction has:\n"
            f"- type: {item.type}\n"
            f"- title: {item.title}\n"
            f"- original_date: {item.original_date or 'null'}\n"
            f"- due_date: {item.due_date or 'null'}\n"
            f"- date: {item.date or 'null'}\n"
            f"- time: {item.time or 'null'}\n"
            f"- location: {item.location or 'null'}\n"
            f"- note: {item.note or 'null'}\n\n"
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

        try:
            parts = [types.Part(text=prompt)]
            if content_type.startswith("image/"):
                parts.append(
                    types.Part.from_bytes(data=file_bytes, mime_type=content_type)
                )
            elif content_type == "application/pdf":
                parts.append(
                    types.Part.from_bytes(
                        data=file_bytes, mime_type="application/pdf"
                    )
                )
            else:
                logger.warning("Vision refine not supported for %s", content_type)
                return None

            response = self._generate_with_timeout(
                self._client.models.generate_content,
                model=self._model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.warning("Gemini vision refine failed: %s", exc)
            return None

        raw = response.text
        if not raw:
            logger.warning("Gemini vision refine returned empty response")
            return None

        try:
            cleaned = self._clean_json_response(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Gemini vision refine JSON: %s", exc)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            else:
                return None

        if not isinstance(data, dict):
            return None

        try:
            refined = ExtractedItem(**data)
            normalized_date, normalized_time = normalize_date(refined.original_date)
            if normalized_date:
                if refined.type == "event" and not refined.date:
                    refined.date = normalized_date
                if refined.type == "task" and not refined.due_date:
                    refined.due_date = normalized_date
            if normalized_time and not refined.time:
                refined.time = normalized_time
            ensure_required_dates(refined)
            return refined
        except Exception as exc:
            logger.warning("Gemini vision refine produced invalid item: %s", exc)
            return None
