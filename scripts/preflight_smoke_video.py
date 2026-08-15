#!/usr/bin/env python3
"""Validate the one approved video fixture before RT-VLM inference.

The fixture's checksum is its identity; its encoded metadata, complete decoded frame
set, sampling feasibility, and inference budget form one immutable smoke-test contract.
This command is deliberately not a general video validator and does not assess caption
quality.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from retail_intelligence.inference_budget import evaluate_inference_budget  # noqa: E402


FIXTURE_PATH = REPOSITORY_ROOT / "samples" / "hong-kong-passageway.mp4"
EXPECTED_SHA256 = "8fef7d87a037714d2fc97f19faeac28a3ea41912d00fcced7032cc0674153dd4"
EXPECTED_DURATION_SECONDS = 10.777433
EXPECTED_FRAME_COUNT = 323
EXPECTED_WIDTH = 960
EXPECTED_HEIGHT = 540
EXPECTED_FRAME_RATE = "30000/1001"
SELECTED_FRAME_COUNT = 80


class PreflightError(RuntimeError):
    """The fixture does not match its approved media contract."""


def evenly_spaced_indices(frame_count: int, selected_count: int) -> tuple[int, ...]:
    """Select unique indices spanning the first through last decoded frame."""

    if selected_count < 2:
        raise ValueError("selected_count must be at least 2")
    if frame_count < selected_count:
        raise ValueError(
            f"cannot select {selected_count} distinct frames from {frame_count} frames"
        )

    last_index = frame_count - 1
    return tuple(
        selection * last_index // (selected_count - 1)
        for selection in range(selected_count)
    )


def find_media_tool(name: str) -> str:
    """Find a media tool on PATH or in Homebrew's Apple Silicon prefix."""

    path = shutil.which(name)
    if path:
        return path

    homebrew_path = Path("/opt/homebrew/bin") / name
    if homebrew_path.is_file():
        return str(homebrew_path)

    raise PreflightError(f"{name} is required; install ffmpeg and retry")


def sha256(path: Path) -> str:
    """Return a file's SHA-256 digest without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as fixture:
        for chunk in iter(lambda: fixture.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_checked(command: list[str]) -> str:
    """Run a media command and surface its diagnostic on failure."""

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        diagnostic = result.stderr.strip() or "no diagnostic was reported"
        raise PreflightError(f"media command failed: {diagnostic}")
    return result.stdout


def probe_fixture(ffprobe: str, fixture_path: Path) -> dict[str, object]:
    """Read the fixture's video stream and container metadata."""

    output = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:"
                "stream=codec_name,codec_type,width,height,pix_fmt,"
                "avg_frame_rate,nb_frames"
            ),
            "-of",
            "json",
            str(fixture_path),
        ]
    )
    return json.loads(output)


def validate_metadata(probe: dict[str, object]) -> None:
    """Require the exact approved H.264 media profile."""

    streams = probe.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise PreflightError("fixture must contain exactly one stream")

    stream = streams[0]
    if not isinstance(stream, dict):
        raise PreflightError("ffprobe returned invalid stream metadata")

    expected_values = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": EXPECTED_WIDTH,
        "height": EXPECTED_HEIGHT,
        "pix_fmt": "yuv420p",
        "avg_frame_rate": EXPECTED_FRAME_RATE,
        "nb_frames": str(EXPECTED_FRAME_COUNT),
    }
    mismatches = {
        field: (stream.get(field), expected)
        for field, expected in expected_values.items()
        if stream.get(field) != expected
    }
    if mismatches:
        raise PreflightError(f"unexpected media metadata: {mismatches}")

    format_metadata = probe.get("format")
    if not isinstance(format_metadata, dict) or "duration" not in format_metadata:
        raise PreflightError("ffprobe did not report a duration")
    duration = float(format_metadata["duration"])
    if abs(duration - EXPECTED_DURATION_SECONDS) > 0.001:
        raise PreflightError(
            f"unexpected duration {duration:.6f}s; expected {EXPECTED_DURATION_SECONDS:.6f}s"
        )


def decode_frame_hashes(ffmpeg: str, fixture_path: Path) -> tuple[str, ...]:
    """Completely decode the video and return one pixel hash per frame."""

    output = run_checked(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-i",
            str(fixture_path),
            "-map",
            "0:v:0",
            "-f",
            "framemd5",
            "-",
        ]
    )
    return tuple(
        line.rsplit(",", 1)[1].strip()
        for line in output.splitlines()
        if line and not line.startswith("#")
    )


def preflight(fixture_path: Path = FIXTURE_PATH) -> None:
    """Validate checksum, media metadata, decode, sampling, and token budget."""

    if not fixture_path.is_file():
        raise PreflightError(f"fixture is missing: {fixture_path}")

    actual_sha256 = sha256(fixture_path)
    if actual_sha256 != EXPECTED_SHA256:
        raise PreflightError(
            f"checksum mismatch: got {actual_sha256}, expected {EXPECTED_SHA256}"
        )

    ffprobe = find_media_tool("ffprobe")
    ffmpeg = find_media_tool("ffmpeg")
    probe = probe_fixture(ffprobe, fixture_path)
    validate_metadata(probe)

    frame_hashes = decode_frame_hashes(ffmpeg, fixture_path)
    if len(frame_hashes) != EXPECTED_FRAME_COUNT:
        raise PreflightError(
            f"decoded {len(frame_hashes)} frames; expected {EXPECTED_FRAME_COUNT}"
        )

    distinct_frame_count = len(set(frame_hashes))
    if distinct_frame_count < SELECTED_FRAME_COUNT:
        raise PreflightError(
            f"decoded only {distinct_frame_count} visually distinct frames; "
            f"at least {SELECTED_FRAME_COUNT} are required"
        )

    selected_indices = evenly_spaced_indices(
        frame_count=len(frame_hashes), selected_count=SELECTED_FRAME_COUNT
    )
    selected_hashes = tuple(frame_hashes[index] for index in selected_indices)
    if len(set(selected_indices)) != SELECTED_FRAME_COUNT:
        raise PreflightError("even sampling produced duplicate frame indices")
    if len(set(selected_hashes)) != SELECTED_FRAME_COUNT:
        raise PreflightError("even sampling produced duplicate decoded frames")

    budget = evaluate_inference_budget(448, 448, SELECTED_FRAME_COUNT)
    if not budget.accepted or budget.visual_tokens != 7_840:
        raise PreflightError(
            f"unexpected inference budget: {budget.visual_tokens} visual tokens"
        )

    print(f"PASS checksum: {actual_sha256}")
    print(
        "PASS media: "
        f"H.264, {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}, {EXPECTED_FRAME_RATE} fps, "
        f"{EXPECTED_DURATION_SECONDS:.6f}s"
    )
    print(
        f"PASS decode: {len(frame_hashes)} frames, "
        f"{distinct_frame_count} distinct decoded frames"
    )
    print(
        f"PASS sampling: {len(selected_indices)} unique evenly spaced frames "
        f"({selected_indices[0]} through {selected_indices[-1]})"
    )
    print("PASS inference budget: 448x448, 80 frames, 7,840 visual tokens")


def main() -> int:
    """Run the command-line preflight."""

    try:
        preflight()
    except (OSError, ValueError, json.JSONDecodeError, PreflightError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
