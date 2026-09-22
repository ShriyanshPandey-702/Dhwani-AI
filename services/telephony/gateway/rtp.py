"""
RTP Depacketizer and PCM Accumulator for VoiceShield Telephony Gateway.

Converts incoming RFC 3550 RTP packets carrying 16 kHz Signed Linear PCM (slin16)
into canonical VoiceShield 250 ms little-endian int16 audio chunks.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class RtpTelemetry:
    packets_received: int = 0
    packets_invalid: int = 0
    packets_dropped: int = 0
    bytes_received: int = 0
    samples_received: int = 0
    sequence_gaps: int = 0
    timestamp_discontinuities: int = 0


@dataclass
class RtpPacket:
    version: int
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes


class RtpDepacketizer:
    """
    Parses RFC 3550 RTP datagrams, validates headers, and extracts PCM audio payloads.
    """

    def __init__(self, is_big_endian: bool = True):
        self.is_big_endian = is_big_endian
        self.telemetry = RtpTelemetry()
        self._last_seq: Optional[int] = None
        self._last_timestamp: Optional[int] = None

    def reset(self) -> None:
        """Reset sequence/timestamp tracking between sessions."""
        self._last_seq = None
        self._last_timestamp = None

    def parse_packet(self, datagram: bytes) -> Optional[RtpPacket]:
        """
        Parse and validate one RTP UDP datagram. Returns None on validation failure.
        """
        self.telemetry.packets_received += 1
        self.telemetry.bytes_received += len(datagram)

        # 1. Validate minimum RTP header length
        if len(datagram) < 12:
            self.telemetry.packets_invalid += 1
            return None

        b0 = datagram[0]
        b1 = datagram[1]

        # 2. Validate RTP version (must be 2)
        version = (b0 >> 6) & 0x03
        if version != 2:
            self.telemetry.packets_invalid += 1
            return None

        padding = bool((b0 >> 5) & 0x01)
        extension = bool((b0 >> 4) & 0x01)
        csrc_count = b0 & 0x0F

        marker = bool((b1 >> 7) & 0x01)
        payload_type = b1 & 0x7F

        seq, timestamp, ssrc = struct.unpack(">HII", datagram[2:12])

        header_len = 12 + (csrc_count * 4)
        if len(datagram) < header_len:
            self.telemetry.packets_invalid += 1
            return None

        # Handle header extensions if present
        if extension:
            if len(datagram) < header_len + 4:
                self.telemetry.packets_invalid += 1
                return None
            ext_words = struct.unpack(">H", datagram[header_len + 2 : header_len + 4])[0]
            ext_len = 4 + (ext_words * 4)
            header_len += ext_len
            if len(datagram) < header_len:
                self.telemetry.packets_invalid += 1
                return None

        # Handle padding if present
        end_idx = len(datagram)
        if padding:
            if end_idx <= header_len:
                self.telemetry.packets_invalid += 1
                return None
            pad_len = datagram[-1]
            if pad_len == 0 or pad_len > (end_idx - header_len):
                self.telemetry.packets_invalid += 1
                return None
            end_idx -= pad_len

        payload = datagram[header_len:end_idx]

        # 6. Validate payload length is even for 16-bit PCM
        if len(payload) % 2 != 0:
            self.telemetry.packets_invalid += 1
            return None

        # Track sequence gaps
        if self._last_seq is not None:
            expected_seq = (self._last_seq + 1) & 0xFFFF
            if seq != expected_seq:
                self.telemetry.sequence_gaps += 1

        # Track timestamp discontinuities (e.g. non-monotonic or huge jump)
        if self._last_timestamp is not None:
            diff = (timestamp - self._last_timestamp) & 0xFFFFFFFF
            # Normal audio packet advancing by 160-960 ticks (10-60 ms @ 16 kHz)
            if diff == 0 or diff > 16000:
                self.telemetry.timestamp_discontinuities += 1

        self._last_seq = seq
        self._last_timestamp = timestamp

        return RtpPacket(
            version=version,
            padding=padding,
            extension=extension,
            csrc_count=csrc_count,
            marker=marker,
            payload_type=payload_type,
            sequence_number=seq,
            timestamp=timestamp,
            ssrc=ssrc,
            payload=payload,
        )

    def extract_pcm16_le(self, datagram: bytes) -> Optional[bytes]:
        """
        Parse RTP datagram, extract payload, and convert from big-endian to little-endian int16.
        """
        pkt = self.parse_packet(datagram)
        if pkt is None or len(pkt.payload) == 0:
            return None

        payload = pkt.payload
        num_samples = len(payload) // 2

        if self.is_big_endian:
            # Network byte order (big-endian) -> Host/VoiceShield (little-endian)
            samples = struct.unpack(f">{num_samples}h", payload)
            converted = struct.pack(f"<{num_samples}h", *samples)
        else:
            converted = payload

        self.telemetry.samples_received += num_samples
        return converted


class PcmAccumulator:
    """
    Accumulates raw little-endian PCM16 samples and yields fixed-duration chunks (e.g. 250 ms).
    Also generates sequence-numbered VoiceShield WebSocket envelopes.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration_ms: int = 250,
    ):
        self.sample_rate = sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
        self.chunk_bytes = self.chunk_samples * 2  # 16-bit = 2 bytes/sample
        self._buffer = bytearray()
        self._vs_seq = 0

    def reset(self) -> None:
        """Reset buffer and sequence counter."""
        self._buffer.clear()
        self._vs_seq = 0

    @property
    def current_seq(self) -> int:
        return self._vs_seq

    def push(self, pcm_bytes: bytes) -> List[bytes]:
        """
        Push raw little-endian PCM bytes and return any full chunks (each 8,000 bytes for 250ms).
        """
        self._buffer.extend(pcm_bytes)
        chunks: List[bytes] = []

        while len(self._buffer) >= self.chunk_bytes:
            chunk = bytes(self._buffer[: self.chunk_bytes])
            del self._buffer[: self.chunk_bytes]
            chunks.append(chunk)

        return chunks

    def build_chunk_message(self, chunk_pcm_bytes: bytes) -> dict:
        """
        Create canonical VoiceShield WebSocket audio_chunk message.
        """
        encoded = base64.b64encode(chunk_pcm_bytes).decode("ascii")
        msg = {
            "type": "audio_chunk",
            "data": encoded,
            "seq": self._vs_seq,
        }
        self._vs_seq += 1
        return msg
