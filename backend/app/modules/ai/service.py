"""Factory + document text extraction for the assistant service."""

import io
from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import ValidationFailedError
from app.modules.ai.provider import AssistantProvider, SourcePage
from app.modules.ai.rules_provider import RulesProvider

_override: AssistantProvider | None = None


@lru_cache
def _configured_provider() -> AssistantProvider:
    settings = get_settings()
    if settings.ai_provider == "groq" and settings.groq_api_key:
        from app.modules.ai.groq_provider import GroqProvider

        return GroqProvider(settings.groq_api_key, settings.groq_model, settings.ai_timeout_seconds)
    return RulesProvider()


def get_assistant() -> AssistantProvider:
    return _override or _configured_provider()


def set_assistant(provider: AssistantProvider | None) -> None:
    """Tests swap in a deterministic provider."""
    global _override
    _override = provider


def extract_pages(filename: str, content: bytes) -> list[SourcePage]:
    """Read text from PDF, Word or plain text so it can be searched and drafted from."""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(content))
            return [SourcePage(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
        except Exception as exc:
            raise ValidationFailedError("We could not read this PDF. Is it protected or damaged?") from exc
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs)
        return _paginate(text)
    if name.endswith((".txt", ".md", ".csv")):
        return _paginate(content.decode("utf-8", errors="replace"))
    raise ValidationFailedError("Please upload a PDF, Word (.docx) or text file.")


def _paginate(text: str, chars_per_page: int = 2500) -> list[SourcePage]:
    pages: list[SourcePage] = []
    buffer = ""
    for paragraph in text.split("\n"):
        if len(buffer) + len(paragraph) > chars_per_page and buffer:
            pages.append(SourcePage(len(pages) + 1, buffer))
            buffer = ""
        buffer += paragraph + "\n"
    if buffer.strip():
        pages.append(SourcePage(len(pages) + 1, buffer))
    return pages
