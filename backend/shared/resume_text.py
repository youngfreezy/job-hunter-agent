"""Pure resume text extraction shared by uploads and scheduled launches."""
import logging

logger = logging.getLogger(__name__)

class ResumeTextError(ValueError):
    def __init__(self, status_code: int, detail: str):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


def extract_resume_text(raw: bytes, suffix: str) -> str:
    suffix = suffix.lower().lstrip('.')
    if len(raw) > 10 * 1024 * 1024:
        raise ResumeTextError(413, 'Resume file exceeds 10 MB limit')
    # Validate file signatures (magic bytes)
    if suffix == "pdf" and not raw[:4].startswith(b"%PDF"):
        raise ResumeTextError(status_code=400, detail="File does not appear to be a valid PDF")
    if suffix == "docx" and not raw[:4].startswith(b"PK\x03\x04"):
        raise ResumeTextError(status_code=400, detail="File does not appear to be a valid DOCX")

    if suffix == "txt":
        text = raw.decode("utf-8", errors="replace")
    elif suffix == "pdf":
        import io
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ResumeTextError(
                status_code=500,
                detail="PDF parsing dependency missing (install `pypdf`).",
            ) from exc
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # OCR fallback for image-based PDFs
        if not text.strip():
            try:
                import fitz
                import pytesseract
                from PIL import Image
                doc = fitz.open(stream=raw, filetype="pdf")
                ocr_parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_parts.append(pytesseract.image_to_string(img))
                text = "\n".join(ocr_parts)
            except Exception as ocr_err:
                logger.warning("OCR fallback failed (%s)", type(ocr_err).__name__)
    elif suffix == "docx":
        import io
        try:
            from docx import Document
        except ImportError as exc:
            raise ResumeTextError(
                status_code=500,
                detail="DOCX parsing dependency missing (install `python-docx`).",
            ) from exc
        doc = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == "doc":
        raise ResumeTextError(
            status_code=400,
            detail="Legacy .doc files are not supported. Please upload .docx, .pdf, or .txt.",
        )
    else:
        raise ResumeTextError(status_code=400, detail=f"Unsupported file type: .{suffix}")

    text = text.strip()
    if not text:
        raise ResumeTextError(status_code=422, detail="Could not extract any text from the file")

    return text
