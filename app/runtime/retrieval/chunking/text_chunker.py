from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.runtime.retrieval.chunking.base import BaseChunker
from app.runtime.retrieval.chunking.schemas import (
    ChunkDocument,
    ChunkSourcePosition,
    ChunkingPolicyConfig,
)

MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
NUMERIC_HEADING_PATTERN = re.compile(r"^(\d+(?:\.\d+){0,4})(?:\u3001|[.\s])+\s*(.+)$")
CHINESE_HEADING_PATTERN = re.compile(
    r"^(?:\u7b2c[0-9\u4e00-\u9fff]+[\u7ae0\u8282\u7bc7\u90e8\u5206].+)$"
)


@dataclass(frozen=True)
class SourceUnit:
    text: str
    page_no: int | None = None
    row_index: int | None = None
    block_id: str | None = None
    paragraph_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedUnit:
    text: str
    title_path: tuple[str, ...]
    source_position: ChunkSourcePosition
    heading_positions: tuple[ChunkSourcePosition, ...] = ()

    @property
    def char_count(self) -> int:
        return len(self.text)

    def as_overlap_copy(self) -> "PreparedUnit":
        overlap_position = self.source_position.model_copy(
            update={
                "metadata": {
                    **self.source_position.metadata,
                    "is_overlap": True,
                }
            }
        )
        heading_positions = tuple(
            position.model_copy(
                update={
                    "metadata": {
                        **position.metadata,
                        "is_heading_prefix": True,
                    }
                }
            )
            for position in self.heading_positions
        )
        return PreparedUnit(
            text=self.text,
            title_path=self.title_path,
            source_position=overlap_position,
            heading_positions=heading_positions,
        )


class TextChunker(BaseChunker):
    def chunk(
        self,
        *,
        document_id: str,
        policy: ChunkingPolicyConfig,
        raw_text: str | None = None,
        units: list[SourceUnit] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> list[ChunkDocument]:
        if units is None:
            if raw_text is None:
                return []
            units = self._build_units_from_text(raw_text, policy)

        prepared_units = self._prepare_units(units, policy)
        if not prepared_units:
            return []
        return self._build_chunks(
            document_id=document_id,
            prepared_units=prepared_units,
            policy=policy,
            metadata=metadata or {},
        )

    def _build_units_from_text(
        self,
        text: str,
        policy: ChunkingPolicyConfig,
    ) -> list[SourceUnit]:
        segments = split_text_segments(text, split_by_paragraph=policy.split_by_paragraph)
        located = locate_segments(text, segments)
        units: list[SourceUnit] = []
        for index, (segment_text, start_offset, end_offset) in enumerate(
            located,
            start=1,
        ):
            units.append(
                SourceUnit(
                    text=segment_text,
                    block_id=f"text:block:{index}",
                    paragraph_id=f"text:paragraph:{index}",
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )
        return units

    def _prepare_units(
        self,
        units: list[SourceUnit],
        policy: ChunkingPolicyConfig,
    ) -> list[PreparedUnit]:
        prepared: list[PreparedUnit] = []
        title_path: list[str] = []
        heading_positions: list[ChunkSourcePosition] = []
        saw_heading = False

        for unit in units:
            normalized_text = unit.text.strip()
            if not normalized_text:
                continue

            heading_level, heading_text = detect_heading(normalized_text)
            if policy.split_by_heading and heading_level is not None:
                saw_heading = True
                title_path = title_path[: heading_level - 1] + [heading_text]
                heading_positions = heading_positions[: heading_level - 1] + [
                    to_source_position(unit, metadata={"kind": "heading"})
                ]
                continue

            for split_unit in split_long_unit(unit, policy):
                prepared.append(
                    PreparedUnit(
                        text=split_unit.text,
                        title_path=tuple(title_path),
                        source_position=to_source_position(split_unit),
                        heading_positions=tuple(heading_positions)
                        if policy.keep_heading_prefix
                        else (),
                    )
                )

        if prepared or not saw_heading:
            return prepared

        fallback_units: list[PreparedUnit] = []
        for unit in units:
            normalized_text = unit.text.strip()
            if not normalized_text:
                continue
            fallback_units.append(
                PreparedUnit(
                    text=normalized_text,
                    title_path=(),
                    source_position=to_source_position(unit),
                )
            )
        return fallback_units

    def _build_chunks(
        self,
        *,
        document_id: str,
        prepared_units: list[PreparedUnit],
        policy: ChunkingPolicyConfig,
        metadata: dict[str, object],
    ) -> list[ChunkDocument]:
        chunks: list[ChunkDocument] = []
        current_units: list[PreparedUnit] = []

        for unit in prepared_units:
            if current_units and policy.split_by_heading and (
                current_units[0].title_path != unit.title_path
            ):
                chunks.append(
                    build_chunk_document(
                        document_id=document_id,
                        chunk_index=len(chunks),
                        units=current_units,
                        policy=policy,
                        metadata=metadata,
                    )
                )
                current_units = []

            projected_units = current_units + [unit]
            if current_units and projected_chunk_length(projected_units, policy) > policy.max_chars:
                chunks.append(
                    build_chunk_document(
                        document_id=document_id,
                        chunk_index=len(chunks),
                        units=current_units,
                        policy=policy,
                        metadata=metadata,
                    )
                )
                current_units = build_overlap_seed(current_units, policy)
                while current_units and projected_chunk_length(
                    current_units + [unit], policy
                ) > policy.max_chars:
                    current_units = current_units[1:]

            current_units.append(unit)

        if current_units:
            chunks.append(
                build_chunk_document(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    units=current_units,
                    policy=policy,
                    metadata=metadata,
                )
            )
        return chunks


def split_text_segments(text: str, *, split_by_paragraph: bool) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    if not split_by_paragraph:
        return [normalized]

    paragraph_segments = [
        segment.strip()
        for segment in re.split(r"\n\s*\n", normalized)
        if segment.strip()
    ]
    if len(paragraph_segments) > 1:
        return paragraph_segments

    line_segments = [line.strip() for line in normalized.split("\n") if line.strip()]
    return line_segments or paragraph_segments


def locate_segments(text: str, segments: list[str]) -> list[tuple[str, int | None, int | None]]:
    located: list[tuple[str, int | None, int | None]] = []
    cursor = 0
    for segment in segments:
        start_offset = text.find(segment, cursor)
        if start_offset < 0:
            start_offset = text.find(segment)
        if start_offset < 0:
            located.append((segment, None, None))
            continue
        end_offset = start_offset + len(segment)
        located.append((segment, start_offset, end_offset))
        cursor = end_offset
    return located


def split_long_unit(
    unit: SourceUnit,
    policy: ChunkingPolicyConfig,
) -> list[SourceUnit]:
    if len(unit.text) <= policy.max_chars:
        return [unit]

    segments: list[SourceUnit] = []
    start = 0
    step = max(1, policy.max_chars - policy.overlap_chars)
    while start < len(unit.text):
        end = min(len(unit.text), start + policy.max_chars)
        text_slice = unit.text[start:end].strip()
        if text_slice:
            left_trim = unit.text[start:end].find(text_slice)
            right_trim = left_trim + len(text_slice)
            slice_start = start + max(left_trim, 0)
            slice_end = start + right_trim
            segments.append(
                SourceUnit(
                    text=text_slice,
                    page_no=unit.page_no,
                    row_index=unit.row_index,
                    block_id=unit.block_id,
                    paragraph_id=unit.paragraph_id,
                    start_offset=(
                        None
                        if unit.start_offset is None
                        else unit.start_offset + slice_start
                    ),
                    end_offset=(
                        None if unit.start_offset is None else unit.start_offset + slice_end
                    ),
                    metadata={
                        **unit.metadata,
                        "window_start": slice_start,
                        "window_end": slice_end,
                    },
                )
            )
        if end >= len(unit.text):
            break
        start += step
    return segments or [unit]


def detect_heading(text: str) -> tuple[int | None, str]:
    if "\n" in text or len(text) > 120:
        return None, text

    markdown_match = MARKDOWN_HEADING_PATTERN.match(text)
    if markdown_match:
        return len(markdown_match.group(1)), markdown_match.group(2).strip()

    numeric_match = NUMERIC_HEADING_PATTERN.match(text)
    if numeric_match:
        return len(numeric_match.group(1).split(".")), text.strip()

    if CHINESE_HEADING_PATTERN.match(text):
        return 1, text.strip()

    return None, text


def to_source_position(
    unit: SourceUnit,
    *,
    metadata: dict[str, object] | None = None,
) -> ChunkSourcePosition:
    merged_metadata = dict(unit.metadata)
    if metadata:
        merged_metadata.update(metadata)
    return ChunkSourcePosition(
        page_no=unit.page_no,
        row_index=unit.row_index,
        block_id=unit.block_id,
        paragraph_id=unit.paragraph_id,
        start_offset=unit.start_offset,
        end_offset=unit.end_offset,
        metadata=merged_metadata,
    )


def projected_chunk_length(
    units: list[PreparedUnit],
    policy: ChunkingPolicyConfig,
) -> int:
    title_path = list(units[0].title_path) if units else []
    title_prefix = ""
    if title_path and policy.keep_heading_prefix:
        title_prefix = "\n".join(title_path) + "\n\n"
    body = "\n\n".join(unit.text for unit in units).strip()
    return len(title_prefix) + len(body)


def build_overlap_seed(
    units: list[PreparedUnit],
    policy: ChunkingPolicyConfig,
) -> list[PreparedUnit]:
    if policy.overlap_chars <= 0 or not units:
        return []

    seed: list[PreparedUnit] = []
    remaining = policy.overlap_chars
    target_title_path = units[-1].title_path

    for unit in reversed(units):
        if policy.split_by_heading and unit.title_path != target_title_path:
            break
        seed.insert(0, unit.as_overlap_copy())
        remaining -= unit.char_count
        if remaining <= 0:
            break
    return seed


def build_chunk_document(
    *,
    document_id: str,
    chunk_index: int,
    units: list[PreparedUnit],
    policy: ChunkingPolicyConfig,
    metadata: dict[str, object],
) -> ChunkDocument:
    title_path = list(units[0].title_path) if units else []
    body = "\n\n".join(unit.text for unit in units).strip()
    title_prefix = ""
    if title_path and policy.keep_heading_prefix:
        title_prefix = "\n".join(title_path) + "\n\n"
    text = f"{title_prefix}{body}".strip()

    source_positions = deduplicate_positions(
        [
            *(position for position in units[0].heading_positions if title_prefix),
            *(unit.source_position for unit in units),
        ]
    )
    page_range = sorted(
        {
            position.page_no
            for position in source_positions
            if position.page_no is not None
        }
    )
    source_block_ids = list(
        dict.fromkeys(
            position.block_id
            for position in source_positions
            if position.block_id is not None
        )
    )

    chunk_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{document_id}:{policy.policy_name}:{chunk_index}:{text}",
    ).hex
    return ChunkDocument(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        title_path=title_path,
        page_range=page_range,
        source_block_ids=source_block_ids,
        source_positions=source_positions,
        policy_name=policy.policy_name,
        metadata={
            **metadata,
            "char_count": len(text),
            "unit_count": len(units),
        },
    )


def deduplicate_positions(
    positions: list[ChunkSourcePosition],
) -> list[ChunkSourcePosition]:
    deduplicated: list[ChunkSourcePosition] = []
    seen: set[tuple[object, ...]] = set()
    for position in positions:
        key = (
            position.page_no,
            position.row_index,
            position.block_id,
            position.paragraph_id,
            position.start_offset,
            position.end_offset,
            tuple(sorted(position.metadata.items())),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(position)
    return deduplicated
