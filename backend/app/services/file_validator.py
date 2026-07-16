import hashlib
import magic
import chardet
from pathlib import Path
from typing import Tuple

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE_SIZE = 15 * 1024 * 1024
MAX_ROWS = 500_000

DANGEROUS_PATTERNS = [
    b"<?php",
    b"<script",
    b"javascript:",
    b"vbscript:",
    b"=cmd|",
    b"=HYPERLINK",
    b"+cmd",
    b"-cmd",
    b"@SUM(1+1)",
]


class FileValidationError(Exception):
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class FileValidator:
    @staticmethod
    def validate(file_path: Path, original_filename: str, file_size: int) -> dict:
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise FileValidationError(
                f"File type '{ext}' is not allowed. Upload CSV or Excel files only.",
                "INVALID_EXTENSION"
            )

        if file_size > MAX_FILE_SIZE:
            raise FileValidationError(
                f"File is too large ({file_size / 1024 / 1024:.1f} MB). Maximum is 15 MB.",
                "FILE_TOO_LARGE"
            )

        mime = magic.from_file(str(file_path), mime=True)
        if mime not in ALLOWED_MIME_TYPES:
            raise FileValidationError(
                f"File content does not match a valid spreadsheet format. Detected: {mime}",
                "MIME_MISMATCH"
            )

        with open(file_path, "rb") as f:
            header = f.read(8192)
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in header.lower():
                raise FileValidationError(
                    "File contains potentially dangerous content and has been rejected.",
                    "MALICIOUS_CONTENT"
                )

        encoding = "utf-8"
        if ext == ".csv":
            with open(file_path, "rb") as f:
                raw = f.read()
            result = chardet.detect(raw)
            encoding = result.get("encoding", "utf-8") or "utf-8"

        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)

        return {
            "mime_type": mime,
            "encoding": encoding,
            "sha256_hash": sha256.hexdigest(),
            "detected_extension": ext,
        }
