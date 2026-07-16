import pandas as pd
from pathlib import Path
from typing import Dict
import uuid

from app.services.file_validator import FileValidator, FileValidationError
from app.services.schema_detector import SchemaDetector
from app.config import get_settings

settings = get_settings()


class UploadService:
    @staticmethod
    def parse_file(file_path: Path, extension: str, encoding: str) -> pd.DataFrame:
        if extension == ".csv":
            df = pd.read_csv(file_path, encoding=encoding, on_bad_lines="skip")
        elif extension in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path, engine="openpyxl" if extension == ".xlsx" else "xlrd")
        else:
            raise ValueError(f"Unsupported file type: {extension}")

        df.columns = df.columns.str.strip()
        
        return df

    @staticmethod
    async def process_upload(
        file_path: Path,
        original_filename: str,
        file_size: int,
        business_id: str,
        uploaded_by: str,
    ) -> Dict:
        validation = FileValidator.validate(file_path, original_filename, file_size)

        df = UploadService.parse_file(
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
            "status": "mapping_required",
        }
