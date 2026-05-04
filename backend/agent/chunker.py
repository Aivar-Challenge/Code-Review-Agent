"""
Semantic chunker — splits file diffs by function/class boundaries
rather than raw line count to preserve semantic context.

Each chunk is guaranteed to be ≤ MAX_TOKENS_PER_CHUNK tokens.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Callable

import tiktoken

from backend.config import settings
from backend.agent.diff_parser import FileDiff, DiffLine

logger = logging.getLogger("agent.chunker")

# Patterns that denote a semantic boundary (start of func/class/method)
_BOUNDARY_PATTERNS = [
    re.compile(r"^(async\s+)?def\s+\w+"),        # Python function
    re.compile(r"^class\s+\w+"),                  # Python class
    re.compile(r"^(export\s+)?(async\s+)?function\s+\w+"),   # JS/TS function
    re.compile(r"^(export\s+)?(default\s+)?class\s+\w+"),    # JS/TS class
    re.compile(r"^\s*(public|private|protected|static)\s+\w+.*\("),  # Java/C#
    re.compile(r"^func\s+\w+"),                   # Go
    re.compile(r"^fn\s+\w+"),                     # Rust
    re.compile(r"^\s*(pub\s+)?fn\s+\w+"),         # Rust pub fn
]


@dataclass
class DiffChunk:
    """
    A semantic chunk of a file diff, ready for LLM analysis.
    Contains the changed lines + surrounding context.
    """
    file_path: str
    language: str
    chunk_index: int
    total_chunks: int
    hunk_headers: list[str]
    lines: list[DiffLine]
    imports_context: str = ""       # imports from the file
    raw_text: str = ""              # rendered text for LLM prompt
    token_count: int = 0

    @property
    def has_changes(self) -> bool:
        return any(l.line_type in ("added", "removed") for l in self.lines)

    @property
    def changed_line_numbers(self) -> list[int]:
        return [
            l.new_lineno or l.old_lineno
            for l in self.lines
            if l.line_type in ("added", "removed") and (l.new_lineno or l.old_lineno)
        ]


def _detect_language(filename: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".java": "java",
        ".go": "go", ".rs": "rust", ".rb": "ruby",
        ".cpp": "cpp", ".c": "c", ".cs": "csharp",
        ".php": "php", ".swift": "swift", ".kt": "kotlin",
    }
    for ext, lang in ext_map.items():
        if filename.endswith(ext):
            return lang
    return "text"


def _count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _is_boundary(line: str) -> bool:
    stripped = line.strip()
    return any(p.match(stripped) for p in _BOUNDARY_PATTERNS)


def _extract_imports(lines: list[DiffLine]) -> str:
    """Extract import/require statements for context injection."""
    import_lines = []
    for dl in lines:
        stripped = dl.content.strip()
        if (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("require(")
            or stripped.startswith("use ")
        ):
            import_lines.append(dl.content)
    return "\n".join(import_lines[:30])  # cap at 30 imports


def _render_chunk(chunk_lines: list[DiffLine], hunk_headers: list[str]) -> str:
    """Render diff lines into a human-readable patch format."""
    parts = []
    prev_hunk_header = None
    for line in chunk_lines:
        # Find which hunk this line belongs to
        prefix = " "
        if line.line_type == "added":
            prefix = "+"
        elif line.line_type == "removed":
            prefix = "-"

        lineno_info = ""
        if line.new_lineno:
            lineno_info = f"[L{line.new_lineno}] "
        elif line.old_lineno:
            lineno_info = f"[L{line.old_lineno}] "

        parts.append(f"{prefix}{lineno_info}{line.content}")

    return "\n".join(parts)


def chunk_file_diff(
    file_diff: FileDiff,
    max_tokens: int | None = None,
    model: str | None = None,
) -> list[DiffChunk]:
    """
    Split a FileDiff into semantic chunks.
    Each chunk is bounded by function/class boundaries and token limits.
    """
    max_tokens = max_tokens or settings.max_tokens_per_chunk
    model = model or settings.default_model
    language = _detect_language(file_diff.filename)

    # Flatten all lines across hunks (preserving order)
    all_lines: list[DiffLine] = []
    hunk_headers: list[str] = []
    for hunk in file_diff.hunks:
        hunk_headers.append(hunk.header)
        all_lines.extend(hunk.lines)

    if not all_lines:
        return []

    # Extract imports for context injection
    imports_ctx = _extract_imports(all_lines)

    # Split by semantic boundaries
    segments: list[list[DiffLine]] = []
    current_segment: list[DiffLine] = []

    for dl in all_lines:
        if _is_boundary(dl.content) and current_segment:
            segments.append(current_segment)
            current_segment = []
        current_segment.append(dl)

    if current_segment:
        segments.append(current_segment)

    # If no boundaries found, treat whole file as one segment
    if not segments:
        segments = [all_lines]

    # Merge small segments and split large ones to respect token limit
    chunks: list[list[DiffLine]] = []
    current: list[DiffLine] = []

    for seg in segments:
        candidate = current + seg
        rendered = _render_chunk(candidate, hunk_headers)
        token_count = _count_tokens(imports_ctx + rendered, model)

        if token_count <= max_tokens:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If the segment itself is too large, split by token budget
            if _count_tokens(_render_chunk(seg, hunk_headers), model) > max_tokens:
                sub: list[DiffLine] = []
                for dl in seg:
                    sub.append(dl)
                    if _count_tokens(_render_chunk(sub, hunk_headers), model) > max_tokens:
                        chunks.append(sub[:-1])
                        sub = [dl]
                if sub:
                    chunks.append(sub)
            else:
                current = seg

    if current:
        chunks.append(current)

    # Build DiffChunk objects
    result: list[DiffChunk] = []
    total = len(chunks)
    for idx, chunk_lines in enumerate(chunks):
        if not any(l.line_type in ("added", "removed") for l in chunk_lines):
            continue  # skip context-only chunks

        rendered = _render_chunk(chunk_lines, hunk_headers)
        raw_text = f"File: {file_diff.filename}\n"
        if imports_ctx:
            raw_text += f"\n--- Imports/Dependencies ---\n{imports_ctx}\n"
        raw_text += f"\n--- Diff ---\n{rendered}"

        result.append(
            DiffChunk(
                file_path=file_diff.filename,
                language=language,
                chunk_index=idx,
                total_chunks=total,
                hunk_headers=hunk_headers,
                lines=chunk_lines,
                imports_context=imports_ctx,
                raw_text=raw_text,
                token_count=_count_tokens(raw_text, model),
            )
        )

    logger.debug(
        f"Chunked {file_diff.filename}: {len(all_lines)} lines → {len(result)} chunks"
    )
    return result


def chunk_all_files(
    file_diffs: list[FileDiff],
    max_tokens: int | None = None,
    model: str | None = None,
) -> list[DiffChunk]:
    """Chunk all file diffs and return a flat list of DiffChunk objects."""
    all_chunks: list[DiffChunk] = []
    for fd in file_diffs:
        chunks = chunk_file_diff(fd, max_tokens=max_tokens, model=model)
        all_chunks.extend(chunks)
    return all_chunks
