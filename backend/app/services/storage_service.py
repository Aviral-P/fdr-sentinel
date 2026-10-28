"""Private local document storage and content validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
from uuid import uuid4

import fitz
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class ValidatedDocument:
    display_filename: str
    extension: str
    content_type: str
    size_bytes: int
    sha256_checksum: str


IMAGE_MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTENSION_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def _private_storage_root() -> Path:
    root = get_settings().resolved_document_storage_dir.resolve()
    frontend_public = (Path(__file__).resolve().parents[3] / "frontend" / "public").resolve()
    if root == frontend_public or root.is_relative_to(frontend_public):
        raise AppError(500, "unsafe_storage_configuration", "Document storage cannot be inside the frontend public directory.")
    return root


def validate_document(filename: str | None, declared_content_type: str | None, content: bytes) -> ValidatedDocument:
    settings = get_settings()
    if not content:
        raise AppError(400, "empty_document", "The uploaded document is empty.")
    if len(content) > settings.max_document_size_bytes:
        raise AppError(
            413,
            "document_too_large",
            f"The uploaded document exceeds the {settings.max_document_size_bytes}-byte limit.",
        )

    # Treat the supplied name as display metadata only. Strip both POSIX and
    # Windows path components before storing it in the database.
    supplied_name = (filename or "uploaded-document").replace("\\", "/").rsplit("/", 1)[-1]
    supplied_name = "".join(character for character in supplied_name if character.isprintable()).strip()
    extension = Path(supplied_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(415, "unsupported_document_type", "Only PDF, JPEG, PNG, and WebP documents are supported.")

    if extension == ".pdf":
        if b"%PDF-" not in content[:1024]:
            raise AppError(400, "invalid_document_content", "The file extension does not match valid PDF content.")
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                if document.is_encrypted or document.page_count < 1:
                    raise ValueError("encrypted or empty PDF")
                # Force one page read so a header-only or damaged PDF is not accepted.
                document.load_page(0).get_text("text")
        except Exception as exc:
            raise AppError(400, "invalid_document_content", "The PDF is malformed, encrypted, or unreadable.") from exc
        detected_type = "application/pdf"
    else:
        try:
            with Image.open(BytesIO(content)) as image:
                image_format = image.format
                if image.width * image.height > 40_000_000:
                    raise ValueError("image dimensions exceed local processing limit")
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise AppError(400, "invalid_document_content", "The file extension does not match a valid supported image.") from exc
        detected_type = IMAGE_MIME_BY_FORMAT.get(image_format or "")
        if detected_type is None or image_format != IMAGE_EXTENSION_FORMAT[extension]:
            raise AppError(415, "unsupported_document_type", "Only JPEG, PNG, and WebP images are supported.")

    if declared_content_type and declared_content_type not in {detected_type, "application/octet-stream"}:
        raise AppError(400, "content_type_mismatch", "The submitted content type does not match the detected file type.")

    if not supplied_name:
        supplied_name = f"uploaded-document{extension}"
    supplied_name = re.sub(r"[\x00-\x1f\x7f]", "", supplied_name)[:255] or f"uploaded-document{extension}"
    return ValidatedDocument(
        display_filename=supplied_name,
        extension=extension,
        content_type=detected_type,
        size_bytes=len(content),
        sha256_checksum=sha256(content).hexdigest(),
    )


def store_private_document(content: bytes, extension: str) -> tuple[str, Path]:
    root = _private_storage_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        # Filesystem ACLs may not support chmod (for example, some mounted volumes).
        pass
    storage_name = f"{uuid4().hex}{extension}"
    path = (root / storage_name).resolve()
    if path.parent != root:
        raise AppError(500, "storage_error", "Could not create a safe document storage path.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stored_file:
            stored_file.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return storage_name, path


def resolve_private_document(storage_key: str) -> Path:
    root = _private_storage_root()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise AppError(404, "document_file_not_found", "The stored document file could not be found.")
    return path
