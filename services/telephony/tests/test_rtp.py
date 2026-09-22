"""
Deterministic Unit Tests for Telephony Gateway RTP Depacketizer & PCM Accumulator.
"""

import base64
import struct
import pytest

from services.telephony.gateway.rtp import RtpDepacketizer, PcmAccumulator


def _build_rtp_packet(
    version: int = 2,
    padding: bool = False,
    extension: bool = False,
    csrc_list: list = None,
    marker: bool = False,
    pt: int = 96,
    seq: int = 100,
    ts: int = 160000,
    ssrc: int = 0x12345678,
    payload: bytes = b"",
    pad_bytes: bytes = b"",
) -> bytes:
    csrc_list = csrc_list or []
    cc = len(csrc_list) & 0x0F
    b0 = ((version & 0x03) << 6) | ((1 if padding else 0) << 5) | ((1 if extension else 0) << 4) | cc
    b1 = ((1 if marker else 0) << 7) | (pt & 0x7F)

    header = bytearray(struct.pack(">BBHII", b0, b1, seq, ts, ssrc))
    for csrc in csrc_list:
        header.extend(struct.pack(">I", csrc))

    if extension:
        # Profile 0xBEDE, 1 word of extension data (4 bytes)
        header.extend(struct.pack(">HH", 0xBEDE, 1))
        header.extend(b"\x00\x00\x00\x00")

    packet = bytes(header) + payload
    if padding:
        packet += pad_bytes
    return packet


class TestRtpDepacketizer:
    def test_valid_rtp_packet(self):
        depacketizer = RtpDepacketizer(is_big_endian=True)
        # 16-bit PCM payload: 4 samples [1000, -2000, 3000, -4000] in big-endian
        payload_be = struct.pack(">4h", 1000, -2000, 3000, -4000)
        pkt_bytes = _build_rtp_packet(seq=1, ts=1000, payload=payload_be)

        pkt = depacketizer.parse_packet(pkt_bytes)
        assert pkt is not None
        assert pkt.version == 2
        assert pkt.sequence_number == 1
        assert pkt.timestamp == 1000
        assert pkt.payload == payload_be
        assert depacketizer.telemetry.packets_received == 1
        assert depacketizer.telemetry.packets_invalid == 0

    def test_invalid_rtp_version(self):
        depacketizer = RtpDepacketizer()
        pkt_bytes = _build_rtp_packet(version=1, payload=b"\x00\x00")
        assert depacketizer.parse_packet(pkt_bytes) is None
        assert depacketizer.telemetry.packets_invalid == 1

    def test_short_rtp_packet(self):
        depacketizer = RtpDepacketizer()
        assert depacketizer.parse_packet(b"\x80\x60\x00\x01\x00") is None
        assert depacketizer.telemetry.packets_invalid == 1

    def test_rtp_header_with_csrc(self):
        depacketizer = RtpDepacketizer()
        payload_be = struct.pack(">2h", 500, -500)
        pkt_bytes = _build_rtp_packet(csrc_list=[0xAAAAAAAA, 0xBBBBBBBB], payload=payload_be)
        pkt = depacketizer.parse_packet(pkt_bytes)
        assert pkt is not None
        assert pkt.csrc_count == 2
        assert pkt.payload == payload_be

    def test_rtp_header_with_extension(self):
        depacketizer = RtpDepacketizer()
        payload_be = struct.pack(">2h", 1234, -5678)
        pkt_bytes = _build_rtp_packet(extension=True, payload=payload_be)
        pkt = depacketizer.parse_packet(pkt_bytes)
        assert pkt is not None
        assert pkt.extension is True
        assert pkt.payload == payload_be

    def test_rtp_payload_extraction(self):
        depacketizer = RtpDepacketizer()
        raw_payload = b"\x01\x00\x02\x00\x03\x00"
        pkt_bytes = _build_rtp_packet(payload=raw_payload)
        pkt = depacketizer.parse_packet(pkt_bytes)
        assert pkt is not None
        assert pkt.payload == raw_payload

    def test_odd_payload_rejection(self):
        depacketizer = RtpDepacketizer()
        # Odd payload (3 bytes cannot be 16-bit PCM samples)
        pkt_bytes = _build_rtp_packet(payload=b"\x01\x02\x03")
        assert depacketizer.parse_packet(pkt_bytes) is None
        assert depacketizer.telemetry.packets_invalid == 1

    def test_big_endian_to_little_endian_conversion(self):
        depacketizer = RtpDepacketizer(is_big_endian=True)
        # Big-endian samples: 0x1234, -0x1234
        sample1 = 0x1234
        sample2 = -0x1234
        payload_be = struct.pack(">hh", sample1, sample2)
        pkt_bytes = _build_rtp_packet(payload=payload_be)

        pcm16_le = depacketizer.extract_pcm16_le(pkt_bytes)
        assert pcm16_le is not None
        # Verify decoded samples in little-endian match original integer values
        decoded_samples = struct.unpack("<hh", pcm16_le)
        assert decoded_samples == (sample1, sample2)
        assert depacketizer.telemetry.samples_received == 2

    def test_rtp_sequence_gap_telemetry(self):
        depacketizer = RtpDepacketizer()
        payload = struct.pack(">h", 0)

        # Normal sequential packets
        depacketizer.parse_packet(_build_rtp_packet(seq=10, ts=1000, payload=payload))
        depacketizer.parse_packet(_build_rtp_packet(seq=11, ts=1320, payload=payload))
        assert depacketizer.telemetry.sequence_gaps == 0

        # Gap: jump from 11 to 14
        depacketizer.parse_packet(_build_rtp_packet(seq=14, ts=2280, payload=payload))
        assert depacketizer.telemetry.sequence_gaps == 1


class TestPcmAccumulator:
    def test_pcm_accumulation_and_exact_250ms_chunk(self):
        # 16 kHz, 250 ms = 4,000 samples = 8,000 bytes
        acc = PcmAccumulator(sample_rate=16000, chunk_duration_ms=250)
        assert acc.chunk_samples == 4000
        assert acc.chunk_bytes == 8000

        # Feed 1000 samples (2000 bytes) at a time
        packet_2000b = b"\x00\x01" * 1000

        # Pushes 1, 2, 3: no chunk emitted yet
        assert acc.push(packet_2000b) == []
        assert acc.push(packet_2000b) == []
        assert acc.push(packet_2000b) == []

        # Push 4: exactly 8,000 bytes accumulated -> 1 chunk emitted
        chunks = acc.push(packet_2000b)
        assert len(chunks) == 1
        assert len(chunks[0]) == 8000

    def test_voiceshield_seq_numbering_and_json_framing(self):
        acc = PcmAccumulator(sample_rate=16000, chunk_duration_ms=250)
        chunk_bytes = b"\x12\x34" * 4000  # 8000 bytes

        msg0 = acc.build_chunk_message(chunk_bytes)
        assert msg0["type"] == "audio_chunk"
        assert msg0["seq"] == 0
        decoded0 = base64.b64decode(msg0["data"])
        assert decoded0 == chunk_bytes

        msg1 = acc.build_chunk_message(chunk_bytes)
        assert msg1["type"] == "audio_chunk"
        assert msg1["seq"] == 1

        msg2 = acc.build_chunk_message(chunk_bytes)
        assert msg2["seq"] == 2

    def test_reset(self):
        acc = PcmAccumulator()
        acc.push(b"\x00" * 1000)
        acc.build_chunk_message(b"\x00" * 8000)
        assert acc.current_seq == 1

        acc.reset()
        assert acc.current_seq == 0
        assert acc.push(b"\x00" * 8000) != []
