from __future__ import annotations

from app.modules.document_center.schemas import DocumentLocation, DocumentParseResult
from app.runtime.retrieval.chunking.base import BaseChunker
from app.runtime.retrieval.chunking.schemas import ChunkDocument, ChunkingPolicyConfig
from app.runtime.retrieval.chunking.text_chunker import (
    SourceUnit,
    TextChunker,
    locate_segments,
    split_text_segments,
)


class DocumentChunker(BaseChunker):
    def __init__(self, text_chunker: TextChunker | None = None) -> None:
        self._text_chunker = text_chunker or TextChunker()

    def chunk(
        self,
        *,
        document_id: str,
        policy: ChunkingPolicyConfig,
        parsed_document: DocumentParseResult,
        metadata: dict[str, object] | None = None,
    ) -> list[ChunkDocument]:
        source_units = self._build_source_units(parsed_document, policy)
        return self._text_chunker.chunk(
            document_id=document_id,
            policy=policy,
            units=source_units,
            metadata=metadata,
        )

    def _build_source_units(
        self,
        parsed_document: DocumentParseResult,
        policy: ChunkingPolicyConfig,
    ) -> list[SourceUnit]:
        if parsed_document.pages:
            units = self._build_units_from_pages(parsed_document, policy)
            if units:
                return units
        return self._build_units_from_text_and_locations(parsed_document, policy)

    def _build_units_from_pages(
        self,
        parsed_document: DocumentParseResult,
        policy: ChunkingPolicyConfig,
    ) -> list[SourceUnit]:
        units: list[SourceUnit] = []
        cursor = 0
        full_text = parsed_document.text
        for page in parsed_document.pages:
            segments = split_text_segments(
                page.text,
                split_by_paragraph=policy.split_by_paragraph,
            )
            for segment_index, segment in enumerate(segments, start=1):
                start_offset = full_text.find(segment, cursor)
                if start_offset < 0:
                    start_offset = full_text.find(segment)
                end_offset = (
                    None if start_offset < 0 else start_offset + len(segment)
                )
                if end_offset is not None:
                    cursor = end_offset
                units.append(
                    SourceUnit(
                        text=segment,
                        page_no=page.page_no,
                        block_id=f"page:{page.page_no}:segment:{segment_index}",
                        paragraph_id=f"page:{page.page_no}:paragraph:{segment_index}",
                        start_offset=None if start_offset < 0 else start_offset,
                        end_offset=end_offset,
                    )
                )
        return units

    def _build_units_from_text_and_locations(
        self,
        parsed_document: DocumentParseResult,
        policy: ChunkingPolicyConfig,
    ) -> list[SourceUnit]:
        text = parsed_document.text
        line_segments = [line.strip() for line in text.splitlines() if line.strip()]
        paragraph_segments = split_text_segments(
            text,
            split_by_paragraph=policy.split_by_paragraph,
        )
        segments = paragraph_segments
        locations = parsed_document.locations

        if locations:
            if len(locations) == len(line_segments):
                segments = line_segments
            elif len(locations) == len(paragraph_segments):
                segments = paragraph_segments

        located_segments = locate_segments(text, segments)
        mapped_locations = map_locations_to_segments(
            locations=locations,
            segment_count=len(located_segments),
        )

        units: list[SourceUnit] = []
        for index, ((segment_text, start_offset, end_offset), location) in enumerate(
            zip(located_segments, mapped_locations, strict=False),
            start=1,
        ):
            units.append(
                SourceUnit(
                    text=segment_text,
                    page_no=location.page_no,
                    row_index=location.row_index,
                    block_id=build_block_id(location, index),
                    paragraph_id=f"text:paragraph:{index}",
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )
        return units


def map_locations_to_segments(
    *,
    locations: list[DocumentLocation],
    segment_count: int,
) -> list[DocumentLocation]:
    if not locations:
        return [DocumentLocation() for _ in range(segment_count)]
    if len(locations) == segment_count:
        return locations
    if len(locations) == 1:
        return [locations[0] for _ in range(segment_count)]
    return [DocumentLocation() for _ in range(segment_count)]


def build_block_id(location: DocumentLocation, index: int) -> str:
    if location.page_no is not None and location.row_index is not None:
        return f"page:{location.page_no}:row:{location.row_index}"
    if location.page_no is not None:
        return f"page:{location.page_no}:segment:{index}"
    if location.row_index is not None:
        return f"row:{location.row_index}"
    return f"text:block:{index}"
