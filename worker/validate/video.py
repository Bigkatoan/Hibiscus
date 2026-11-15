"""Video probing (decode first / middle / last frame of every episode) and H.264 preview clips.

Uses PyAV (bundled FFmpeg with dav1d/libaom for AV1 and libx264 for H.264), the same decoder
stack LeRobot 0.7.1 uses with ``video_backend=pyav``. Previews follow CONTRACT_NOTES 4.5: one
H.264 clip per (camera, episode), <= 480p, CRF 28, starting at t=0, plus a JPEG of the first
frame. The original videos are never modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import av.container
import av.error
import av.video.frame
import av.video.stream

PREVIEW_MAX_HEIGHT = 480
PREVIEW_CRF = 28
JPEG_QUALITY = 85


class DecodeError(Exception):
    pass


@dataclass(slots=True)
class VideoInfo:
    codec: str
    width: int
    height: int
    duration_s: float | None
    frames: int | None


def probe(path: Path) -> VideoInfo:
    try:
        with av.open(str(path)) as c:
            if not c.streams.video:
                raise DecodeError("no video stream")
            s = c.streams.video[0]
            dur: float | None = None
            if s.duration is not None and s.time_base is not None:
                dur = float(s.duration * s.time_base)
            elif c.duration is not None:
                dur = c.duration / 1_000_000
            return VideoInfo(
                codec=str(s.codec_context.name),
                width=int(s.codec_context.width),
                height=int(s.codec_context.height),
                duration_s=dur,
                frames=int(s.frames) if s.frames else None,
            )
    except av.error.FFmpegError as exc:
        raise DecodeError(str(exc)) from exc
    raise DecodeError("unreachable")  # pragma: no cover - av.open always returns or raises


def _frame_time(frame: av.video.frame.VideoFrame, tb: Fraction) -> float:
    if frame.pts is None:
        raise DecodeError("frame without pts")
    return float(frame.pts * tb)


def decode_at(path: Path, timestamps: list[float], fps: float) -> list[tuple[int, int] | None]:
    """Decode one frame at each timestamp (seconds, absolute in the file).

    Returns (width, height) of the decoded frame or ``None`` if no frame within half a frame period
    could be decoded at that position. Raises ``DecodeError`` if the file cannot be opened.
    """
    tol = 0.5 / fps + 1e-4
    out: list[tuple[int, int] | None] = []
    try:
        with av.open(str(path)) as c:
            if not c.streams.video:
                raise DecodeError("no video stream")
            s = c.streams.video[0]
            tb = s.time_base
            if tb is None:
                raise DecodeError("stream without time base")
            for t in timestamps:
                got: tuple[int, int] | None = None
                try:
                    c.seek(max(0, int(t / tb)), stream=s, backward=True, any_frame=False)
                    for frame in c.decode(s):
                        ft = _frame_time(frame, tb)
                        if ft < t - tol:
                            continue
                        if ft <= t + tol:
                            # Force a real conversion so corrupt payloads surface here.
                            frame.to_ndarray(format="rgb24")
                            got = (frame.width, frame.height)
                        break
                except (av.error.FFmpegError, DecodeError, ValueError):
                    got = None
                out.append(got)
    except av.error.FFmpegError as exc:
        raise DecodeError(str(exc)) from exc
    return out


def preview_size(width: int, height: int, max_height: int = PREVIEW_MAX_HEIGHT) -> tuple[int, int]:
    if height <= max_height:
        w, h = width, height
    else:
        w, h = round(width * max_height / height), max_height
    return w - (w % 2), h - (h % 2)


@dataclass(slots=True)
class ClipSpec:
    episode_index: int
    from_s: float
    to_s: float
    mp4_out: Path
    jpg_out: Path


class _ClipWriter:
    def __init__(self, spec: ClipSpec, fps: float, size: tuple[int, int]) -> None:
        self.spec = spec
        self.size = size
        spec.mp4_out.parent.mkdir(parents=True, exist_ok=True)
        self.container: Any = av.open(
            str(spec.mp4_out), mode="w", format="mp4", options={"movflags": "+faststart"}
        )
        rate = Fraction(fps).limit_denominator(1001)
        self.frame_tb = 1 / rate
        self.stream: Any = self.container.add_stream("libx264", rate=rate)
        self.stream.width, self.stream.height = size
        self.stream.pix_fmt = "yuv420p"
        self.stream.options = {"crf": str(PREVIEW_CRF), "preset": "veryfast"}
        self.count = 0
        self.thumb_written = False

    def add(self, frame: av.video.frame.VideoFrame) -> None:
        w, h = self.size
        out = frame.reformat(width=w, height=h, format="yuv420p")
        if not self.thumb_written:
            frame.to_image().resize((w, h)).save(  # type: ignore[no-untyped-call]  # PyAV stub gap
                self.spec.jpg_out, format="JPEG", quality=JPEG_QUALITY
            )
            self.thumb_written = True
        out.pts = self.count
        out.time_base = self.frame_tb
        for packet in self.stream.encode(out):
            self.container.mux(packet)
        self.count += 1

    def close(self) -> None:
        for packet in self.stream.encode(None):
            self.container.mux(packet)
        self.container.close()


def make_clips(src: Path, clips: list[ClipSpec], fps: float) -> dict[int, int]:
    """Decode ``src`` once, sequentially, and write one preview clip per ``ClipSpec``.

    Returns episode_index -> number of frames written. Episodes for which no frame was written
    have no output files.
    """
    pending = sorted(clips, key=lambda c: c.from_s)
    half = 0.5 / fps
    written: dict[int, int] = {}
    writers: dict[int, _ClipWriter] = {}
    try:
        with av.open(str(src)) as c:
            s = c.streams.video[0]
            s.thread_type = "AUTO"
            tb = s.time_base
            if tb is None:
                raise DecodeError("stream without time base")
            size = preview_size(int(s.codec_context.width), int(s.codec_context.height))
            idx = 0
            for frame in c.decode(s):
                t = _frame_time(frame, tb)
                # Close clips that ended before this frame.
                while idx < len(pending) and t >= pending[idx].to_s - half:
                    w = writers.pop(pending[idx].episode_index, None)
                    if w is not None:
                        w.close()
                        written[pending[idx].episode_index] = w.count
                    idx += 1
                if idx >= len(pending):
                    break
                spec = pending[idx]
                if t < spec.from_s - half:
                    continue
                w = writers.get(spec.episode_index)
                if w is None:
                    w = _ClipWriter(spec, fps, size)
                    writers[spec.episode_index] = w
                w.add(frame)
    except av.error.FFmpegError as exc:
        raise DecodeError(str(exc)) from exc
    finally:
        for ep, w in writers.items():
            w.close()
            written[ep] = w.count
    return written


def expected_frames(from_s: float, to_s: float, fps: float) -> int:
    return math.floor((to_s - from_s) * fps + 0.5)
