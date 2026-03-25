from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import ChunkingSettings, DocumentParseSettings, OCRSettings
from app.modules.knowledge_center import build_document_chunk_service


class DocumentChunkServiceTestCase(unittest.TestCase):
    def test_document_chunk_service_parses_and_chunks_text_documents(self) -> None:
        ocr_settings = OCRSettings(
            ocr_default_provider="internal_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url=None,
            internal_ocr_api_key=None,
        )
        chunking_settings = ChunkingSettings(
            chunking_default_policy_name="default",
            chunking_max_chars=70,
            chunking_overlap_chars=20,
            chunking_split_by_heading=True,
            chunking_split_by_paragraph=True,
            chunking_keep_heading_prefix=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            parse_settings = DocumentParseSettings(
                document_parse_cache_dir=str(Path(temp_dir) / "cache"),
                document_parse_enable_cache=True,
                document_parse_download_timeout_ms=1000,
            )
            sample_path = Path(temp_dir) / "sample.md"
            sample_path.write_text(
                "# Overview\n\n" + "A" * 28 + "\n\n" + "B" * 28 + "\n\n" + "C" * 28,
                encoding="utf-8",
            )

            service = build_document_chunk_service(
                chunking_settings=chunking_settings,
                ocr_settings=ocr_settings,
                document_parse_settings=parse_settings,
            )
            result = service.parse_and_chunk(
                tenant_id="tenant-a",
                app_id="app-a",
                document_id="doc-service-1",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=str(sample_path),
            )

        self.assertEqual(result.document_id, "doc-service-1")
        self.assertEqual(result.source_type, "file_path")
        self.assertEqual(result.file_name, "sample.md")
        self.assertEqual(result.total_chunks, 2)
        self.assertEqual(result.chunks[0].title_path, ["Overview"])


if __name__ == "__main__":
    unittest.main()
