import logging
import re

from app.models import ExtractedItem
from .utils import normalize_date, ensure_required_dates

logger = logging.getLogger(__name__)


class LocalTextExtractor:
    """
    Rule-based extractor that turns plain text into structured tasks/events.
    Designed as a fast, zero-API-cost path before Gemini fallback.
    """

    # ── Keyword lexicons ──
    TASK_KEYWORDS = {
        "buy",
        "purchase",
        "get",
        "pick up",
        "order",
        "send",
        "email",
        "write",
        "draft",
        "compose",
        "call",
        "phone",
        "ring",
        "contact",
        "reach out",
        "finish",
        "complete",
        "do",
        "work on",
        "start",
        "pay",
        "submit",
        "upload",
        "post",
        "remind",
        "todo",
        "to do",
        "task",
        "action item",
        "prepare",
        "organize",
        "clean",
        "fix",
        "repair",
        "check",
        "review",
        "read",
        "watch",
        "listen",
        "download",
        "install",
        "update",
        "renew",
        "follow up",
        "follow-up",
    }

    EVENT_KEYWORDS = {
        "meeting",
        "meet",
        "sync",
        "standup",
        "stand-up",
        "review",
        "appointment",
        "reservation",
        "call at",
        "call with",
        "zoom",
        "teams",
        "conference",
        "lunch",
        "dinner",
        "breakfast",
        "coffee",
        "interview",
        "presentation",
        "webinar",
        "workshop",
        "visit",
        "tour",
        "trip",
        "flight",
        "travel",
        "party",
        "celebration",
        "wedding",
        "birthday",
        "concert",
        "show",
        "game",
        "match",
        "doctor",
        "dentist",
        "therapy",
        "class",
        "lesson",
        "seminar",
    }

    IGNORE_KEYWORDS = {
        "already done",
        "completed",
        "finished",
        "was",
        "were",
        "happened",
        "occurred",
        "note:",
        "info:",
        "just so you know",
        "fyi",
        "remember that",
        "i already",
        "has been",
        "had been",
    }

    LOCATION_PATTERNS = [
        re.compile(r"\b(?:[aA][tT]|[iI][nN])\s+([A-Z][A-Za-z0-9\s\-,\.]{2,40})\b"),
        re.compile(
            r"\b(?:location|venue|place|room|office|address)\s*[\-:]?\s*([A-Za-z0-9\s\-,\.]{2,40})\b",
            re.IGNORECASE,
        ),
    ]

    # Raw date-phrase patterns — used when dateparser fails so we still capture
    # the original wording instead of dumping the whole sentence.
    _DATE_PHRASE_PATTERNS = [
        r"\btomorrow(?:\s+(?:morning|afternoon|evening|night|at\s+\d{1,2}[:.]?\d{0,2}))?\b",
        r"\btoday(?:\s+(?:morning|afternoon|evening|night))?\b",
        r"\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|month|year)\b",
        r"\bthis\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|month|year)\b",
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:,?\s+\d{4})?\b",
        r"\bin\s+\d+\s+(?:days?|weeks?|months?|years?)\b",
        r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
        r"\b\d{1,2}[./]\d{1,2}\b",
    ]

    _FILLER_PREFIXES = [
        r"^\s*I\s+(?:would\s+like\s+to|need\s+to|have\s+to|want\s+to|should|will)\s+",
        r"^\s*(?:let's|lets)\s+",
        r"^\s*(?:don't\s+forget\s+to|dont\s+forget\s+to|remember\s+to|remind\s+me\s+to)\s+",
        r"^\s*(?:we\s+need\s+to|could\s+you|can\s+you|please)\s+",
        r"^\s*I\s+",
    ]

    # ── Public API ──

    def extract(self, text: str) -> list[ExtractedItem]:
        segments = self._segment(text)
        items: list[ExtractedItem] = []
        for segment in segments:
            item = self._extract_segment(segment)
            if item:
                ensure_required_dates(item)
                items.append(item)
        return items

    # ── Segmentation ──

    def _segment(self, text: str) -> list[str]:
        """Split text into candidate segments by sentence, line, bullet, or number."""
        # First pass: split by newlines and bullets
        delimiters = r"[\n\r]+|(?:^|\n)\s*[-•*]\s*|(?:^|\n)\s*\d+[\.)]\s*"
        raw = re.split(delimiters, text)

        segments = []
        for piece in raw:
            piece = piece.strip()
            if not piece:
                continue

            # Second pass: try to split long pieces by sentence boundaries
            # when each chunk looks like a separate intent.
            if len(piece) >= 30:
                sentence_chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", piece)
                if len(sentence_chunks) > 1:
                    valid_chunks = []
                    for chunk in sentence_chunks:
                        chunk = chunk.strip()
                        if len(chunk) >= 10:
                            lower = chunk.lower()
                            if any(kw in lower for kw in self.TASK_KEYWORDS | self.EVENT_KEYWORDS):
                                valid_chunks.append(chunk)
                            elif len(chunk) >= 20:
                                valid_chunks.append(chunk)
                        elif 3 <= len(chunk) < 10 and any(
                            kw in chunk.lower() for kw in self.TASK_KEYWORDS | self.EVENT_KEYWORDS
                        ):
                            valid_chunks.append(chunk)
                    if len(valid_chunks) > 1:
                        segments.extend(valid_chunks)
                        continue

            if len(piece) >= 10:
                segments.append(piece)
            elif 3 <= len(piece) < 10 and any(
                kw in piece.lower() for kw in self.TASK_KEYWORDS | self.EVENT_KEYWORDS
            ):
                segments.append(piece)

        return segments

    # ── Per-segment extraction ──

    def _extract_segment(self, segment: str) -> ExtractedItem | None:
        lower = segment.lower()

        # Ignore check
        for ign in self.IGNORE_KEYWORDS:
            if ign in lower:
                return None

        # Type scoring
        task_score = sum(1 for kw in self.TASK_KEYWORDS if kw in lower)
        event_score = sum(1 for kw in self.EVENT_KEYWORDS if kw in lower)

        # Boosters for events with explicit time or weekday
        if re.search(r"\b(?:at|from)\s+\d{1,2}[:.]\d{2}\b", lower):
            event_score += 1
        if re.search(
            r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower
        ):
            event_score += 0.5

        if task_score == 0 and event_score == 0:
            return None

        item_type = "event" if event_score > task_score else "task"

        # Date / time
        date_str, time_str = normalize_date(segment)

        # If full segment fails, try just the date phrase
        if not date_str:
            date_phrase = self._extract_date_phrase(segment)
            if date_phrase:
                date_str, _ = normalize_date(date_phrase)
                # Keep time from the segment extraction if we already found one
                if not time_str:
                    _, time_str = normalize_date(segment)

        # Location
        location = self._extract_location(segment)

        # Title
        title = self._build_title(segment, date_str, time_str, location)

        # Confidence
        confidence = self._compute_confidence(
            item_type, task_score, event_score, date_str, time_str, location
        )

        # Fields
        due_date = date_str if item_type == "task" else None
        event_date = date_str if item_type == "event" else None

        # original_date should capture just the date phrase, not the whole sentence
        if date_str:
            original_date = None
        else:
            original_date = self._extract_date_phrase(segment)

        return ExtractedItem(
            type=item_type,
            title=title,
            status="open",
            original_date=original_date,
            due_date=due_date,
            date=event_date,
            time=time_str,
            location=location,
            confidence=confidence,
            note=None,
        )

    def _extract_location(self, segment: str) -> str | None:
        for pattern in self.LOCATION_PATTERNS:
            match = pattern.search(segment)
            if match:
                raw = match.group(1).strip(" ,-.")
                return re.sub(r"^(?:the|a|an)\s+", "", raw, flags=re.IGNORECASE)
        return None

    def _extract_date_phrase(self, segment: str) -> str | None:
        """Extract the raw date phrase from text when normalization fails."""
        for pattern in self._DATE_PHRASE_PATTERNS:
            match = re.search(pattern, segment, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None

    def _build_title(
        self, segment: str, date_str: str | None, time_str: str | None, location: str | None
    ) -> str:
        title = segment

        # Remove location phrase
        if location:
            title = re.sub(
                rf"\b(?:at|in|location|venue|place|room|office|address)\s*[\-:]?\s*{re.escape(location)}",
                "",
                title,
                flags=re.IGNORECASE,
            )

        # Remove explicit time patterns
        title = re.sub(
            r"\b\d{1,2}[:.]\d{2}(?:\s*(?:to|bis|[-\u2013])\s*\d{1,2}[:.]\d{2})?\b",
            "",
            title,
        )
        title = re.sub(r"\b\d{1,2}\s*[uU][hH][rR]\b", "", title)
        title = re.sub(r"\b\d{1,2}\s*[aApP]\.?[mM]\.?\b", "", title)
        # German dot-style time with h suffix: 14.30h
        title = re.sub(r"\b\d{1,2}\.\d{2}h\b", "", title)
        # Military / compact time: 1700, 0900, 0900h
        title = re.sub(
            r"\b(\d{2})(\d{2})h?\b",
            lambda m: ""
            if 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59
            else m.group(0),
            title,
        )

        # Remove common date shapes (DD.MM.YYYY, DD/MM/YY, etc.)
        title = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", "", title)

        # Remove combined relative-date phrases FIRST (e.g. "next Friday")
        title = re.sub(
            r"\b(?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|month|year)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\b(?:tomorrow|today|yesterday)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\b(?:jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\b(?:morning|afternoon|evening|night|noon|midnight)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove filler prefixes
        for pattern in self._FILLER_PREFIXES:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove stray leading "to"
        title = re.sub(r"^\s*to\s+", "", title, flags=re.IGNORECASE)

        # Collapse whitespace first so trailing preposition detection works
        title = re.sub(r"\s+", " ", title)

        # Strip orphaned prepositions that dangle after date/location removal
        # Loop because removing one may expose another at the new end.
        while True:
            cleaned = re.sub(
                r"\b(?:on|at|in|by|from|to|with|for)\s*[.,;]*$",
                "",
                title,
                flags=re.IGNORECASE,
            )
            if cleaned == title:
                break
            title = cleaned

        # Clean up orphaned preposition pairs left in the middle
        # e.g. "on at" → "at", "at in" → "in" (keep the more meaningful second prep)
        while True:
            cleaned = re.sub(
                r"\b(?:on|at|by|from|with|for)\s+(at|in|to)\b",
                r"\1",
                title,
                flags=re.IGNORECASE,
            )
            if cleaned == title:
                break
            title = cleaned

        # Final clean
        title = title.strip(" .,-:;(")

        if title:
            title = title[0].upper() + title[1:]

        return title or "Untitled"

    def _compute_confidence(
        self,
        item_type: str,
        task_score: float,
        event_score: float,
        date_str: str | None,
        time_str: str | None,
        location: str | None,
    ) -> float:
        confidence = 0.5

        if max(task_score, event_score) >= 2:
            confidence += 0.2
        elif max(task_score, event_score) >= 1:
            confidence += 0.1

        if date_str:
            confidence += 0.15
        if time_str:
            confidence += 0.1
        if location:
            confidence += 0.05

        # Penalty when both type signals are present (ambiguous)
        if task_score > 0 and event_score > 0:
            confidence -= 0.15

        return round(min(max(confidence, 0.0), 1.0), 2)
