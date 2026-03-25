from __future__ import annotations

import unittest

from app.core.config import ChunkingSettings
from app.modules.document_center import DocumentLocation, DocumentParseResult
from app.runtime.retrieval.chunking import (
    ChunkingPolicyConfig,
    ChunkingRequest,
    ChunkingService,
)
from app.runtime.tools.schemas import OCRPage


class ChunkingServiceTestCase(unittest.TestCase):
    def test_chunking_service_splits_raw_text_by_heading_and_overlap(self) -> None:
        service = ChunkingService(
            settings=ChunkingSettings(
                chunking_default_policy_name="default",
                chunking_max_chars=70,
                chunking_overlap_chars=20,
                chunking_split_by_heading=True,
                chunking_split_by_paragraph=True,
                chunking_keep_heading_prefix=True,
            )
        )
        text = "# Intro\n\n" + "A" * 28 + "\n\n" + "B" * 28 + "\n\n" + "C" * 28

        result = service.chunk_document(
            ChunkingRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                document_id="doc-1",
                scene="knowledge_ingest",
                raw_text=text,
            )
        )

        self.assertEqual(result.total_chunks, 2)
        self.assertEqual(result.chunks[0].title_path, ["Intro"])
        self.assertIn("B" * 28, result.chunks[1].text)
        self.assertIn("C" * 28, result.chunks[1].text)
        self.assertTrue(
            any(
                position.metadata.get("is_overlap")
                for position in result.chunks[1].source_positions
            )
        )
        self.assertTrue(
            any(
                position.metadata.get("kind") == "heading"
                for position in result.chunks[0].source_positions
            )
        )

    def test_chunking_service_preserves_page_locations_from_parsed_document(self) -> None:
        service = ChunkingService(
            settings=ChunkingSettings(
                chunking_default_policy_name="default",
                chunking_max_chars=200,
                chunking_overlap_chars=20,
                chunking_split_by_heading=True,
                chunking_split_by_paragraph=True,
                chunking_keep_heading_prefix=True,
            )
        )
        parsed_document = DocumentParseResult(
            trace_id="trace-1",
            asset_hash="hash-1",
            cache_key="cache-1",
            parser_name="pdf_document_parser",
            parser_version="v1",
            source_type="file_path",
            source_value="sample.pdf",
            file_name="sample.pdf",
            file_type="pdf",
            text="First page paragraph\n\nSecond page paragraph",
            pages=[
                OCRPage(page_no=1, text="First page paragraph"),
                OCRPage(page_no=2, text="Second page paragraph"),
            ],
            locations=[
                DocumentLocation(page_no=1),
                DocumentLocation(page_no=2),
            ],
            metadata={},
            provider=None,
            model=None,
            cache_hit=False,
            latency_ms=1,
            raw_response=None,
        )

        result = service.chunk_document(
            ChunkingRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                document_id="doc-2",
                scene="knowledge_ingest",
                parsed_document=parsed_document,
                policy=ChunkingPolicyConfig(max_chars=200, overlap_chars=20),
            )
        )

        self.assertEqual(result.total_chunks, 1)
        self.assertEqual(result.chunks[0].page_range, [1, 2])
        self.assertEqual(
            [position.page_no for position in result.chunks[0].source_positions],
            [1, 2],
        )
        self.assertTrue(
            all(position.start_offset is not None for position in result.chunks[0].source_positions)
        )

    def test_chunking_service_preserves_row_locations_from_parsed_document(self) -> None:
        service = ChunkingService(
            settings=ChunkingSettings(
                chunking_default_policy_name="default",
                chunking_max_chars=200,
                chunking_overlap_chars=20,
                chunking_split_by_heading=False,
                chunking_split_by_paragraph=True,
                chunking_keep_heading_prefix=False,
            )
        )
        parsed_document = DocumentParseResult(
            trace_id="trace-2",
            asset_hash="hash-2",
            cache_key="cache-2",
            parser_name="xlsx_document_parser",
            parser_version="v1",
            source_type="file_path",
            source_value="sample.xlsx",
            file_name="sample.xlsx",
            file_type="xlsx",
            text="[Sheet1] Name | Value\n[Sheet1] Alice | 42\n[Sheet1] Bob | 43",
            pages=[],
            locations=[
                DocumentLocation(row_index=1),
                DocumentLocation(row_index=2),
                DocumentLocation(row_index=3),
            ],
            metadata={},
            provider=None,
            model=None,
            cache_hit=False,
            latency_ms=1,
            raw_response=None,
        )

        result = service.chunk_document(
            ChunkingRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                document_id="doc-3",
                scene="knowledge_ingest",
                parsed_document=parsed_document,
            )
        )

        self.assertEqual(result.total_chunks, 1)
        self.assertEqual(
            [position.row_index for position in result.chunks[0].source_positions],
            [1, 2, 3],
        )
        self.assertEqual(
            result.chunks[0].source_block_ids,
            ["row:1", "row:2", "row:3"],
        )


if __name__ == "__main__":
    unittest.main()
