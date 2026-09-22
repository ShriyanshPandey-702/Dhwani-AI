"""
Controlled SIP/VoIP Call Simulator for VoiceShield End-to-End Testing.

Executes a real SIP dialog with Asterisk:
1. Sends SIP INVITE with SDP (supports TCP or UDP SIP signaling).
2. Handles 100 Trying and 200 OK.
3. Sends SIP ACK.
4. Streams real speech audio via RTP packets to Asterisk at 20 ms cadence.
5. Asterisk transcodes and routes audio into VoiceShield Audio Gateway.
6. Sends SIP BYE to hang up cleanly.
"""

from __future__ import annotations

import argparse
import os
import re
import select
import socket
import struct
import time
import uuid
import wave
from typing import Optional


def _linear_to_ulaw(sample: int) -> int:
    """Convert a 16-bit linear PCM sample to 8-bit G.711 u-law."""
    BIAS = 0x84
    CLIP = 32635

    sign = (sample >> 8) & 0x80
    if sign:
        sample = -sample
    if sample > CLIP:
        sample = CLIP
    sample += BIAS

    exponent = 7
    mask = 0x4000
    while (sample & mask) == 0 and exponent > 0:
        exponent -= 1
        mask >>= 1

    mantissa = (sample >> (exponent + 3)) & 0x0F
    ulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return ulaw_byte


class SipUacClient:
    def __init__(
        self,
        server_ip: str = "127.0.0.1",
        server_port: int = 5060,
        local_sip_port: int = 5070,
        local_rtp_port: int = 20050,
        caller_number: str = "+15550199",
        callee_number: str = "100",
        transport: str = "tcp",
    ):
        self.server_ip = server_ip
        self.server_port = server_port
        self.local_sip_port = local_sip_port
        self.local_rtp_port = local_rtp_port
        self.caller_number = caller_number
        self.callee_number = callee_number
        self.transport = transport.lower()

        self.call_id = f"{uuid.uuid4()}@127.0.0.1"
        self.from_tag = uuid.uuid4().hex[:8]
        self.to_tag: Optional[str] = None
        self.remote_rtp_port: Optional[int] = None
        self.cseq = 1
        self.remote_hungup = False

        self.sip_sock: Optional[socket.socket] = None
        self.rtp_sock: Optional[socket.socket] = None

    def start_sockets(self):
        if self.transport == "tcp":
            self.sip_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sip_sock.settimeout(6.0)
            self.sip_sock.connect((self.server_ip, self.server_port))
        else:
            self.sip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sip_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sip_sock.bind(("0.0.0.0", self.local_sip_port))
            self.sip_sock.settimeout(6.0)

        self.rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rtp_sock.bind(("0.0.0.0", self.local_rtp_port))

    def close(self):
        if self.sip_sock:
            self.sip_sock.close()
        if self.rtp_sock:
            self.rtp_sock.close()

    def build_sdp(self) -> str:
        sdp_lines = [
            "v=0",
            f"o=- 1000 1000 IN IP4 127.0.0.1",
            "s=VoiceShieldTestCall",
            "c=IN IP4 127.0.0.1",
            "t=0 0",
            f"m=audio {self.local_rtp_port} RTP/AVP 0",
            "a=rtpmap:0 PCMU/8000",
            "a=sendrecv",
        ]
        return "\r\n".join(sdp_lines) + "\r\n"

    def _send_sip(self, msg: str):
        data = msg.encode("utf-8")
        if self.transport == "tcp":
            self.sip_sock.sendall(data)
        else:
            self.sip_sock.sendto(data, (self.server_ip, self.server_port))

    def send_invite(self):
        sdp = self.build_sdp()
        via_proto = "TCP" if self.transport == "tcp" else "UDP"
        contact_param = ";transport=tcp" if self.transport == "tcp" else ""
        msg = (
            f"INVITE sip:{self.callee_number}@{self.server_ip}:{self.server_port} SIP/2.0\r\n"
            f"Via: SIP/2.0/{via_proto} 127.0.0.1:{self.local_sip_port};branch=z9hG4bK{uuid.uuid4().hex[:12]}\r\n"
            f"From: <sip:{self.caller_number}@127.0.0.1>;tag={self.from_tag}\r\n"
            f"To: <sip:{self.callee_number}@{self.server_ip}:{self.server_port}>\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {self.cseq} INVITE\r\n"
            f"Contact: <sip:{self.caller_number}@127.0.0.1:{self.local_sip_port}{contact_param}>\r\n"
            f"Max-Forwards: 70\r\n"
            f"User-Agent: VoiceShield-Test-UAC\r\n"
            f"Content-Type: application/sdp\r\n"
            f"Content-Length: {len(sdp)}\r\n\r\n"
            f"{sdp}"
        )
        self._send_sip(msg)

    def wait_for_200_ok(self) -> bool:
        start_t = time.time()
        buf = ""
        while time.time() - start_t < 8.0:
            try:
                if self.transport == "tcp":
                    data = self.sip_sock.recv(4096)
                else:
                    data, _ = self.sip_sock.recvfrom(4096)
                if not data:
                    break

                text = data.decode("utf-8", errors="ignore")
                buf += text

                if "200 OK" in buf:
                    # Extract To tag
                    m = re.search(r"To:.*tag=([a-zA-Z0-9_-]+)", buf, re.IGNORECASE)
                    if m:
                        self.to_tag = m.group(1)

                    # Extract SDP media port
                    m_port = re.search(r"m=audio\s+(\d+)\s+RTP", buf)
                    if m_port:
                        self.remote_rtp_port = int(m_port.group(1))

                    return True
            except socket.timeout:
                pass
        return False

    def send_ack(self):
        via_proto = "TCP" if self.transport == "tcp" else "UDP"
        to_hdr = f"<sip:{self.callee_number}@{self.server_ip}:{self.server_port}>"
        if self.to_tag:
            to_hdr += f";tag={self.to_tag}"

        msg = (
            f"ACK sip:{self.callee_number}@{self.server_ip}:{self.server_port} SIP/2.0\r\n"
            f"Via: SIP/2.0/{via_proto} 127.0.0.1:{self.local_sip_port};branch=z9hG4bK{uuid.uuid4().hex[:12]}\r\n"
            f"From: <sip:{self.caller_number}@127.0.0.1>;tag={self.from_tag}\r\n"
            f"To: {to_hdr}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {self.cseq} ACK\r\n"
            f"Max-Forwards: 70\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        self._send_sip(msg)

    def send_bye(self):
        self.cseq += 1
        via_proto = "TCP" if self.transport == "tcp" else "UDP"
        to_hdr = f"<sip:{self.callee_number}@{self.server_ip}:{self.server_port}>"
        if self.to_tag:
            to_hdr += f";tag={self.to_tag}"

        msg = (
            f"BYE sip:{self.callee_number}@{self.server_ip}:{self.server_port} SIP/2.0\r\n"
            f"Via: SIP/2.0/{via_proto} 127.0.0.1:{self.local_sip_port};branch=z9hG4bK{uuid.uuid4().hex[:12]}\r\n"
            f"From: <sip:{self.caller_number}@127.0.0.1>;tag={self.from_tag}\r\n"
            f"To: {to_hdr}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {self.cseq} BYE\r\n"
            f"Max-Forwards: 70\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        self._send_sip(msg)

    def _send_200_ok_for_bye(self, bye_msg: str):
        cseq_m = re.search(r"CSeq:\s*(\d+)\s+BYE", bye_msg, re.IGNORECASE)
        cseq_num = cseq_m.group(1) if cseq_m else "2"
        via_proto = "TCP" if self.transport == "tcp" else "UDP"
        to_hdr = f"<sip:{self.callee_number}@{self.server_ip}:{self.server_port}>"
        if self.to_tag:
            to_hdr += f";tag={self.to_tag}"
        resp = (
            f"SIP/2.0 200 OK\r\n"
            f"Via: SIP/2.0/{via_proto} 127.0.0.1:{self.local_sip_port}\r\n"
            f"From: <sip:{self.caller_number}@127.0.0.1>;tag={self.from_tag}\r\n"
            f"To: {to_hdr}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {cseq_num} BYE\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        self._send_sip(resp)

    def stream_wav_file(self, wav_path: str, duration_sec: Optional[float] = None) -> int:
        """
        Reads a WAV file, resamples to 8000 Hz PCMU (G.711u), and streams 20 ms packets.
        Returns total packets sent.
        """
        if not self.remote_rtp_port:
            raise RuntimeError("Remote RTP destination unknown (SDP not parsed)")

        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            raw_frames = wf.readframes(wf.getnframes())

        # Unpack int16 samples
        if sampwidth == 2:
            all_samples = struct.unpack(f"<{len(raw_frames)//2}h", raw_frames)
        else:
            raise ValueError(f"Unsupported WAV sample width: {sampwidth}")

        # If stereo, downmix to mono
        if n_channels > 1:
            mono_samples = [
                sum(all_samples[i : i + n_channels]) // n_channels
                for i in range(0, len(all_samples), n_channels)
            ]
        else:
            mono_samples = list(all_samples)

        # Resample to 8000 Hz if needed
        if framerate != 8000:
            step = framerate / 8000.0
            resampled = [mono_samples[int(i * step)] for i in range(int(len(mono_samples) / step))]
            samples_8k = resampled
        else:
            samples_8k = mono_samples

        # Convert to u-law bytes (160 samples per 20 ms packet)
        samples_per_pkt = 160
        packets: list[bytes] = []
        for i in range(0, len(samples_8k), samples_per_pkt):
            slice_s = samples_8k[i : i + samples_per_pkt]
            if len(slice_s) < samples_per_pkt:
                slice_s.extend([0] * (samples_per_pkt - len(slice_s)))
            ulaw_payload = bytes(_linear_to_ulaw(s) for s in slice_s)
            packets.append(ulaw_payload)

        # Transmit RTP packets at 20 ms interval
        rtp_seq = 100
        rtp_ts = 160000
        ssrc = 0x11223344
        pt = 0  # PCMU

        dest = (self.server_ip, self.remote_rtp_port)
        print(f"Streaming {len(packets)} RTP packets (20ms each) to {dest}...")

        start_time = time.time()
        packets_sent = 0

        # Loop audio if needed to fulfill requested duration
        idx = 0
        total_len = len(packets)

        while True:
            elapsed = time.time() - start_time
            if duration_sec and elapsed >= duration_sec:
                break

            payload = packets[idx % total_len]
            idx += 1

            b0 = 0x80  # V=2, P=0, X=0, CC=0
            b1 = pt & 0x7F
            header = struct.pack(">BBHII", b0, b1, rtp_seq, rtp_ts, ssrc)
            packet = header + payload

            self.rtp_sock.sendto(packet, dest)
            packets_sent += 1

            rtp_seq = (rtp_seq + 1) & 0xFFFF
            rtp_ts = (rtp_ts + samples_per_pkt) & 0xFFFFFFFF

            # Paced at exactly 20 ms
            expected_elapsed = packets_sent * 0.020
            actual_elapsed = time.time() - start_time
            sleep_t = expected_elapsed - actual_elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

            # Check if remote hung up (e.g. Asterisk sent BYE on BLOCK)
            if self.sip_sock:
                try:
                    r, _, _ = select.select([self.sip_sock], [], [], 0)
                    if r:
                        if self.transport == "tcp":
                            data = self.sip_sock.recv(4096)
                        else:
                            data, _ = self.sip_sock.recvfrom(4096)
                        if data:
                            text = data.decode("utf-8", errors="ignore")
                            if "BYE" in text:
                                print(f"      [REMOTE HANGUP] SIP BYE received from Asterisk! Remote terminated call.")
                                self.remote_hungup = True
                                self._send_200_ok_for_bye(text)
                                break
                except Exception:
                    pass

        return packets_sent


def run_call(
    wav_path: str,
    server_ip: str = "127.0.0.1",
    server_port: int = 5060,
    caller: str = "+15550199",
    callee: str = "100",
    transport: str = "tcp",
    duration: Optional[float] = 7.0,
):
    print("=" * 60)
    print(f"Initiating SIP test call to {server_ip}:{server_port} via {transport.upper()}")
    print(f"Caller: {caller} -> Callee: {callee}")
    print(f"Audio source: {wav_path}")
    print(f"Target duration: {duration}s")
    print("=" * 60)

    uac = SipUacClient(
        server_ip=server_ip,
        server_port=server_port,
        caller_number=caller,
        callee_number=callee,
        transport=transport,
    )
    uac.start_sockets()

    try:
        print("[1/5] Sending SIP INVITE...")
        uac.send_invite()

        print("[2/5] Waiting for 200 OK from Asterisk...")
        if not uac.wait_for_200_ok():
            raise RuntimeError("Timed out waiting for 200 OK from Asterisk")
        print(f"      200 OK received! Remote RTP port: {uac.remote_rtp_port}")

        print("[3/5] Sending SIP ACK...")
        uac.send_ack()
        print("      Call established! Media dialog active.")

        print(f"[4/5] Streaming RTP audio for {duration} seconds...")
        pkts = uac.stream_wav_file(wav_path, duration_sec=duration)
        print(f"      Audio streaming complete! {pkts} RTP packets sent.")

        if not uac.remote_hungup:
            print("[5/5] Sending SIP BYE to terminate call...")
            uac.send_bye()
            time.sleep(0.5)
            print("      Call hung up cleanly.")
        else:
            print("[5/5] Call was terminated remotely by Asterisk (SIP BYE received and acknowledged).")

    finally:
        uac.close()
        print("=" * 60)
        print("SIP test call sequence finished.")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VoiceShield SIP Test Call Generator")
    parser.add_argument("--wav", default="data/external/LJSpeech-1.1/wavs/LJ007-0005.wav", help="WAV file to stream")
    parser.add_argument("--server", default="127.0.0.1", help="Asterisk SIP server IP")
    parser.add_argument("--port", type=int, default=5060, help="Asterisk SIP port")
    parser.add_argument("--transport", default="tcp", choices=["tcp", "udp"], help="SIP signaling transport")
    parser.add_argument("--caller", default="+15550199", help="Caller phone number")
    parser.add_argument("--callee", default="100", help="Dialed number")
    parser.add_argument("--duration", type=float, default=7.0, help="Duration in seconds")
    args = parser.parse_args()

    run_call(
        wav_path=args.wav,
        server_ip=args.server,
        server_port=args.port,
        transport=args.transport,
        caller=args.caller,
        callee=args.callee,
        duration=args.duration,
    )
