"""
Streaming analysis windows — buffering, hop timing, memory bounds, isolation
between sessions, and safe handling of malformed frames.
"""

import numpy as np
import pytest

from app.ml.preprocessing.stream import StreamWindower

SR = 16000


def frame(seconds: float = 1.0, value: float = 0.1) -> np.ndarray:
    return np.full(int(SR * seconds), value, dtype=np.float32)


@pytest.fixture
def windower() -> StreamWindower:
    return StreamWindower(window_ms=4038, hop_ms=1000, sample_rate=SR)


def test_no_window_until_a_full_window_has_accumulated(windower):
    for _ in range(4):                       # 4 s < 4.038 s
        assert windower.push("s", frame()) is None
    assert windower.push("s", frame()) is not None


def test_emitted_window_has_exactly_the_configured_length(windower):
    out = None
    while out is None:
        out = windower.push("s", frame())
    assert out.shape == (windower.window_samples,)
    assert out.dtype == np.float32


def test_hop_controls_how_often_windows_are_emitted():
    w = StreamWindower(window_ms=4000, hop_ms=2000, sample_rate=SR)
    emitted = [w.push("s", frame()) is not None for _ in range(9)]
    # Fills at frame 4, then one window per 2 s of new audio.
    assert emitted[:4] == [False, False, False, True]
    assert sum(emitted) < 9, "hop must throttle emission"


def test_memory_stays_bounded_over_a_long_call(windower):
    for _ in range(600):                     # ten minutes of audio
        windower.push("s", frame())
    stats = windower.stats("s")
    assert stats.buffered_samples <= windower.window_samples + windower.hop_samples
    assert stats.frames_received == 600


def test_window_content_is_the_most_recent_audio(windower):
    for _ in range(4):
        windower.push("s", frame(value=0.1))
    out = windower.push("s", frame(value=0.9))
    assert out is not None
    assert out[-1] == pytest.approx(0.9), "window must end at the newest sample"


def test_returned_window_does_not_alias_the_live_buffer(windower):
    out = None
    while out is None:
        out = windower.push("s", frame())
    out[:] = 12345.0
    nxt = windower.push("s", frame())
    if nxt is not None:
        assert not np.any(nxt == 12345.0)


def test_sessions_are_isolated(windower):
    for _ in range(5):
        windower.push("a", frame())
    assert windower.stats("a").ready is True
    assert windower.stats("b").ready is False
    assert windower.push("b", frame()) is None


def test_reset_discards_buffered_audio(windower):
    for _ in range(5):
        windower.push("s", frame())
    windower.reset("s")
    stats = windower.stats("s")
    assert stats.buffered_samples == 0
    assert stats.windows_emitted == 0


@pytest.mark.parametrize("bad", [
    None,
    np.array([], dtype=np.float32),
    np.array([np.nan] * 100, dtype=np.float32),
    np.array([np.inf] * 100, dtype=np.float32),
])
def test_malformed_frames_are_ignored_without_raising(windower, bad):
    assert windower.push("s", bad) is None
    assert windower.stats("s").buffered_samples == 0


def test_a_malformed_frame_does_not_break_the_following_stream(windower):
    windower.push("s", np.array([np.nan] * 100, dtype=np.float32))
    for _ in range(5):
        windower.push("s", frame())
    assert windower.stats("s").ready is True


def test_stats_report_progress_toward_the_first_window(windower):
    windower.push("s", frame())
    stats = windower.stats("s")
    assert stats.buffered_ms == 1000
    assert stats.ready is False
    assert stats.windows_emitted == 0


def test_unknown_session_reports_empty_stats(windower):
    stats = windower.stats("never-seen")
    assert stats.buffered_samples == 0 and stats.ready is False
