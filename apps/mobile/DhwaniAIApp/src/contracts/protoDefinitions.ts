/**
 * Dhwani AI Integration Contracts & Proto Definitions
 * Exposes the exact protobuf schema and API structures (SIH 2026 PS26104).
 */

export const PROTO_DEFINITION = `syntax = "proto3";

package dhwani.v1;

// Dhwani AI Voice Impersonation Defense Service
// SIH 2026 Problem Statement PS26104
service DhwaniSecurityService {
  // Bi-directional 16kHz PCM streaming for real-time live call/audio inspection
  rpc StreamAudio(stream AudioChunkRequest) returns (stream RiskEventResponse);

  // Unary forensic analysis for pre-recorded audio files
  rpc AnalyzeAudioFile(AnalyzeAudioFileRequest) returns (ManualAnalysisReportResponse);

  // Query current session risk score & multi-modal evidence snapshot
  rpc GetRiskScore(RiskQueryRequest) returns (RiskSnapshotResponse);

  // Evaluate security policy against transaction/call context
  rpc EvaluatePolicy(PolicyEvaluationRequest) returns (PolicyDecisionResponse);

  // Retrieve immutable security incident audit record
  rpc GetIncident(IncidentQueryRequest) returns (IncidentDetailResponse);
}

message AudioChunkRequest {
  string session_id = 1;
  bytes pcm_data = 2; // 16 kHz Mono int16 Signed Linear PCM
  int64 sequence_number = 3;
  int64 timestamp_ms = 4;
  CallContext context = 5;
}

message RiskEventResponse {
  string event_type = 1; // "risk_update" | "policy_decision"
  string event_id = 2;
  int64 seq = 3;
  string session_id = 4;
  int32 risk_score = 5; // 0 - 100
  string risk_state = 6; // LOW | SUSPICIOUS | HIGH | CRITICAL
  string decision = 7; // ALLOW | VERIFY | CHALLENGE | HOLD | BLOCK | ESCALATE
  repeated string reasons = 8;
  repeated string recommended_actions = 9;
  bool pre_transaction_warning = 10;
}`;

export const TYPESCRIPT_SDK_EXAMPLE = `import { DhwaniClient } from "../sdk/DhwaniClient";

// 1. Initialize Client
const client = new DhwaniClient({
  baseUrl: "http://127.0.0.1:8000",
  wsUrl: "ws://127.0.0.1:8000",
});

// 2. Authenticate
await client.login("security-soc@enterprise.com", "securePassword");

// 3. Create Protected Voice Session
const session = await client.createSession({
  caller_id: "+91-9876543210",
  context: "HIGH_VALUE_WIRE_TRANSFER",
  amount_inr: 250000,
});

// 4. Connect Live 16 kHz PCM Audio Stream
client.connectStream({
  sessionId: session.id,
  onEvent: (event) => {
    if (event.type === "risk_update") {
      console.log(\`Risk: \${event.risk_score} (\${event.risk_state})\`);
      console.log(\`Decision: \${event.decision}\`);
      
      if (event.decision === "HOLD" || event.decision === "BLOCK") {
        // Enforce immediate transaction hold in Core Banking
        triggerFraudHold(session.id, event.reasons);
      }
    }
  },
});

// 5. Send Audio Chunks (4000 samples / 250 ms at 16 kHz)
client.sendAudioChunk(base64PcmChunk);`;

export const PYTHON_INTEGRATION_EXAMPLE = `import asyncio
import base64
import json
import websockets
import httpx

API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

async def monitor_voice_transaction(audio_pcm_stream, transaction_meta):
    # 1. Authenticate with Dhwani AI
    async with httpx.AsyncClient() as client:
        auth = await client.post(f"{API_BASE}/auth/login", json={
            "email": "soc-admin@bank.com", "password": "soc_password"
        })
        token = auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Create Protected Session
        sess = await client.post(f"{API_BASE}/sessions", json={
            "metadata": transaction_meta
        }, headers=headers)
        session_id = sess.json()["id"]

    # 3. Stream 16 kHz Mono PCM16 over WebSocket
    ws_url = f"{WS_BASE}/ws/sessions/{session_id}?token={token}"
    async with websockets.connect(ws_url) as ws:
        async def send_audio():
            for pcm_chunk in audio_pcm_stream:
                b64 = base64.b64encode(pcm_chunk).decode("utf-8")
                await ws.send(json.dumps({"type": "audio_chunk", "data": b64}))
                await asyncio.sleep(0.25)

        async def receive_decisions():
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "risk_update":
                    print(f"Risk: {msg['risk_score']} | Decision: {msg['decision']}")
                    if msg["decision"] in ("HOLD", "BLOCK", "ESCALATE"):
                        return msg

        await asyncio.gather(send_audio(), receive_decisions())`;

export const CURL_EXAMPLE = `# 1. Authenticate
curl -X POST "http://localhost:8000/auth/login" \\
  -H "Content-Type: application/json" \\
  -d '{"email": "user@example.com", "password": "password"}'

# 2. Get Factual Integration Readiness
curl -X GET "http://localhost:8000/system/integration/status"

# 3. Analyze Audio File Forensics
curl -X POST "http://localhost:8000/analysis/audio" \\
  -H "Authorization: Bearer <TOKEN>" \\
  -F "audio_file=@suspect_audio.wav"

# 4. Test Outbound Webhook Dispatch
curl -X POST "http://localhost:8000/system/webhooks/test" \\
  -H "Content-Type: application/json" \\
  -d '{"event_type": "risk_update", "risk_score": 82, "decision": "HOLD"}'`;

export const WEBSOCKET_RAW_EXAMPLE = `// Raw WebSocket Voice Streaming Connection
const ws = new WebSocket("ws://127.0.0.1:8000/ws/sessions/" + sessionId + "?token=" + accessToken);

ws.onopen = () => {
  console.log("Connected to Dhwani AI Voice Gateway");
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  switch(msg.type) {
    case "transcript_update":
      console.log("Transcript:", msg.transcript, "Final:", msg.is_final);
      break;
    case "authenticity_update":
      console.log("AASIST-L Spoof Prob:", msg.spoof_probability);
      break;
    case "identity_update":
      console.log("ECAPA Similarity:", msg.similarity_score);
      break;
    case "risk_update":
      console.log("Composite Risk Score:", msg.risk_score, "State:", msg.risk_state);
      break;
    case "policy_decision":
      console.log("Decision:", msg.decision, "Action:", msg.action);
      break;
  }
};

// Send 16 kHz Mono int16 PCM (250ms chunks / 4000 samples)
function sendAudioChunk(base64Pcm) {
  ws.send(JSON.stringify({
    type: "audio_chunk",
    data: base64Pcm
  }));
}`;

export const WEBHOOK_VERIFY_PYTHON_EXAMPLE = `import hmac
import hashlib
import json

# Verify inbound X-Dhwani-Signature on enterprise SIEM listener
def verify_dhwani_webhook(raw_body_bytes, signature_header, shared_secret):
    expected_sig = hmac.new(
        shared_secret.encode('utf-8'),
        raw_body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    received_sig = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected_sig, received_sig)`;
