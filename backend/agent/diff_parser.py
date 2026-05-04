"""
Unified diff parser.
Converts raw unified diff text into structured FileDiff and DiffChunk objects
with accurate GitHub diff positions for inline comment anchoring.
"""
import re
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class DiffLine:
    """A single line from a unified diff hunk."""
    content: str           # Raw line content (without the +/-/space prefix)
    line_type: str         # "added" | "removed" | "context"
    old_lineno: int | None = None
    new_lineno: int | None = None
    diff_position: int = 0  # 1-based position within the file diff (for GitHub API)


@dataclass
class DiffHunk:
    """A single @@ ... @@ hunk from the unified diff."""
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    """All diff information for a single file."""
    filename: str
    old_filename: str       # before rename
    status: str             # added|removed|modified|renamed
    hunks: list[DiffHunk] = field(default_factory=list)
    raw_patch: str = ""

    @property
    def added_lines(self) -> list[DiffLine]:
        return [l for h in self.hunks for l in h.lines if l.line_type == "added"]

    @property
    def all_lines(self) -> list[DiffLine]:
        return [l for h in self.hunks for l in h.lines]

    @property
    def total_changes(self) -> int:
        return sum(
            1 for h in self.hunks for l in h.lines
            if l.line_type in ("added", "removed")
        )


def parse_diff(raw_diff: str) -> list[FileDiff]:
    """
    Parse a unified diff string into a list of FileDiff objects.
    Accurately tracks diff positions as required by the GitHub Review API.
    """
    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None
    diff_position = 0  # position within current file diff

    lines = raw_diff.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # New file diff section
        if line.startswith("diff --git "):
            diff_position = 0
            current_file = FileDiff(
                filename="",
                old_filename="",
                status="modified",
                raw_patch="",
            )
            files.append(current_file)
            current_hunk = None

        elif line.startswith("--- ") and current_file is not None:
            old = line[4:]
            current_file.old_filename = old.lstrip("a/") if old != "/dev/null" else ""

        elif line.startswith("+++ ") and current_file is not None:
            new = line[4:]
            current_file.filename = new.lstrip("b/") if new != "/dev/null" else ""
            if current_file.old_filename == "":
                current_file.status = "added"
            elif current_file.filename == "":
                current_file.status = "removed"
            else:
                current_file.status = "modified"

        elif line.startswith("new file mode"):
            if current_file:
                current_file.status = "added"

        elif line.startswith("deleted file mode"):
            if current_file:
                current_file.status = "removed"

        elif line.startswith("rename from "):
            if current_file:
                current_file.status = "renamed"
                current_file.old_filename = line[len("rename from "):]

        elif line.startswith("rename to ") and current_file:
            current_file.filename = line[len("rename to "):]

        elif line.startswith("@@") and current_file is not None:
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            match = re.match(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line
            )
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2) or 1)
                new_start = int(match.group(3))
                new_count = int(match.group(4) or 1)
                diff_position += 1  # hunk header counts as position 1
                current_hunk = DiffHunk(
                    header=line,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                )
                current_file.hunks.append(current_hunk)
                old_lineno = old_start
                new_lineno = new_start

                # Track current diff position in the file
                if not hasattr(current_file, "_pos_counter"):
                    current_file._pos_counter = 0  # type: ignore
                current_file._pos_counter += 1  # type: ignore

        elif current_hunk is not None and current_file is not None:
            if line.startswith("+"):
                current_file._pos_counter += 1  # type: ignore
                dl = DiffLine(
                    content=line[1:],
                    line_type="added",
                    old_lineno=None,
                    new_lineno=new_lineno,
                    diff_position=current_file._pos_counter,  # type: ignore
                )
                new_lineno += 1
                current_hunk.lines.append(dl)
            elif line.startswith("-"):
                current_file._pos_counter += 1  # type: ignore
                dl = DiffLine(
                    content=line[1:],
                    line_type="removed",
                    old_lineno=old_lineno,
                    new_lineno=None,
                    diff_position=current_file._pos_counter,  # type: ignore
                )
                old_lineno += 1
                current_hunk.lines.append(dl)
            elif line.startswith(" "):
                current_file._pos_counter += 1  # type: ignore
                dl = DiffLine(
                    content=line[1:],
                    line_type="context",
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                    diff_position=current_file._pos_counter,  # type: ignore
                )
                old_lineno += 1
                new_lineno += 1
                current_hunk.lines.append(dl)
            # No-newline marker or binary — skip

        i += 1

    # Remove files with no filename (binary diffs, etc.)
    return [f for f in files if f.filename]


def get_diff_stats(files: list[FileDiff]) -> dict:
    """Return summary stats for the diff."""
    total_added = sum(len(f.added_lines) for f in files)
    total_lines = sum(f.total_changes for f in files)
    return {
        "files_changed": len(files),
        "lines_added": total_added,
        "total_changes": total_lines,
        "files": [
            {
                "filename": f.filename,
                "status": f.status,
                "changes": f.total_changes,
                "added": len(f.added_lines),
            }
            for f in files
        ],
    }
