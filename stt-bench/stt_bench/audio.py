"""ffmpeg 로 오디오 변환·분할·길이 측정."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".aac", ".wma"}

_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "64k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libopus", "-b:a", "48k"],
}


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def convert(src: Path, dst_dir: Path, fmt: str) -> Path:
    """16 kHz 모노로 변환. 같은 결과가 이미 있으면 재사용."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{src.stem}.{fmt}"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", *_CODEC[fmt], str(dst)],
            check=True,
        )
    return dst


def split(src: Path, dst_dir: Path, seconds: float) -> list[Path]:
    """seconds 길이 조각으로 분할 (재인코딩 없이)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for old in dst_dir.glob(f"{src.stem}.part*{src.suffix}"):
        old.unlink()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-f", "segment", "-segment_time", str(seconds),
         "-c", "copy", str(dst_dir / f"{src.stem}.part%03d{src.suffix}")],
        check=True,
    )
    return sorted(dst_dir.glob(f"{src.stem}.part*{src.suffix}"))


def clip(src: Path, dst: Path, start: str, length: str) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", start, "-t", length, "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         *_CODEC.get(dst.suffix.lstrip("."), []), str(dst)],
        check=True,
    )
    return dst
