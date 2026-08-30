import csv
import pandas as pd
from pathlib import Path
from typing import Dict
import uuid

from app.services.file_validator import FileValidator, FileValidationError, MAX_ROWS
from app.services.schema_detector import SchemaDetector
from app.config import get_settings

settings = get_settings()


class UploadService:
    @staticmethod
    def parse_file_with_report(file_path: Path, extension: str, encoding: str) -> tuple[pd.DataFrame, dict]:
        """Parse without silently dropping financial records."""
        if extension == ".csv":
            malformed: list[dict] = []
            with open(file_path, "r", encoding=encoding, errors="strict", newline="") as handle:
                reader = csv.reader(handle)
                try:
                    header = next(reader)
                except StopIteration:
                    return pd.DataFrame(), {"rows_received": 0, "rows_rejected": [], "row_count_rejected": 0}
                expected = len(header)
                row_count = 0
                for line_no, row in enumerate(reader, start=2):
                    row_count += 1
                    if len(row) != expected:
                        malformed.append({"row": line_no, "reason": "malformed_row", "expected_columns": expected, "actual_columns": len(row)})
                        if len(malformed) >= 100:
                            break
                if row_count > MAX_ROWS:
                    raise FileValidationError(
                        f"File contains more than {MAX_ROWS:,} data rows.",
                        "MAX_ROWS_EXCEEDED",
                        {"max_rows": MAX_ROWS, "rows_received": row_count},
                    )
            if malformed:
                raise FileValidationError(
                    "CSV contains malformed financial records and was not imported.",
                    "MALFORMED_CSV",
                    {"rows_rejected": malformed, "rows_received": row_count},
                )
            df = pd.read_csv(file_path, encoding=encoding, on_bad_lines="error")
        elif extension in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path, engine="openpyxl" if extension == ".xlsx" else "xlrd")
            if len(df) > MAX_ROWS:
                raise FileValidationError(
                    f"File contains more than {MAX_ROWS:,} data rows.",
                    "MAX_ROWS_EXCEEDED",
                    {"max_rows": MAX_ROWS, "rows_received": len(df)},
                )
        else:
            raise ValueError(f"Unsupported file type: {extension}")

        df.columns = df.columns.str.strip()
        return df, {"rows_received": len(df), "rows_rejected": [], "row_count_rejected": 0}

    @staticmethod
    def parse_file(file_path: Path, extension: str, encoding: str) -> pd.DataFrame:
        return UploadService.parse_file_with_report(file_path, extension, encoding)[0]

    @staticmethod
    async def process_upload(
        file_path: Path,
        original_filename: str,
        file_size: int,
        business_id: str,
        uploaded_by: str,
    ) -> Dict:
        validation = FileValidator.validate(file_path, original_filename, file_size)

        df, parse_report = UploadService.parse_file_with_report(
            file_path,
            validation["detected_extension"],
            validation["encoding"],
        )

        detection = SchemaDetector().detect(df)

        return {
            "upload_id": str(uuid.uuid4()),
            "filename": original_filename,
            "file_type": validation["detected_extension"].lstrip("."),
            "mime_type": validation["mime_type"],
            "sha256_hash": validation["sha256_hash"],
            "row_count": len(df),
            "detected_columns": detection["detected_columns"],
            "confidence_scores": detection["confidence_scores"],
            "unmapped_columns": detection["unmapped_columns"],
            "sample_rows": detection["sample_rows"],
            "data_quality_report": parse_report,
            "status": "mapping_required",
        }
