from io import BytesIO

from pypdf import PdfReader

from app.utils.errors import bad_request


def extract_text(
    content: bytes,
    filename: str,
    content_type: str,
) -> str:
    """
    Extract text from a supported knowledge document.

    Supported formats:
    - text/plain
    - application/pdf
    """

    if not filename:
        raise bad_request("Filename is required.")

    if not content:
        raise bad_request("The uploaded document is empty.")

    if content_type == "text/plain":
        text = content.decode(
            "utf-8",
            errors="replace",
        )

    elif content_type == "application/pdf":
        text = _extract_pdf_text(content)

    else:
        raise bad_request("Text extraction is not supported for this file type.")

    text = text.strip()

    if not text:
        raise bad_request("No extractable text was found in the document.")

    return text


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))

        pages: list[str] = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages.append(page_text)

        return "\n\n".join(pages)

    except Exception as exc:
        raise bad_request("Unable to extract text from the PDF.") from exc
