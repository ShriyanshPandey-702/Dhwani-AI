/**
 * Dhwani AI Client SDK (TypeScript / JavaScript)
 * 
 * Official client library for integrating Dhwani AI Voice Cloning & Impersonation
 * Defense into Core Banking systems, Contact Centers, Enterprise Communication tools,
 * and Telecom/VoIP services.
 * 
 * Capabilities:
 * - JWT & Token-based API Authentication
 * - Session Lifecycle Management
 * - Real-time 16 kHz Mono int16 PCM Audio Streaming over WebSocket
 * - Instantaneous Multi-Modal Risk & Policy Evaluation
 * - Pre-Transaction Context Scoring (Banking & Executive Approvals)
 * - Forensic Audio File Analysis
 * - Audit Incidents & Outbound Webhook Verification
 */

import axios, { AxiosInstance } from "axios";

export interface DhwaniClientConfig {
  baseUrl: string;
  wsUrl?: string;
  token?: string;
  timeoutMs?: number;
}

export interface RiskSnapshot {
  session_id: string;
  risk_score: number;
  risk_state: "insufficient_evidence" | "low" | "suspicious" | "high" | "critical";
  authenticity: number | null;
  identity: number | null;
  context: number | null;
  consequence: string | null;
  reasons: string[];
}

export interface SecurityPolicyDecision {
  decision: "ALLOW" | "VERIFY" | "CHALLENGE" | "HOLD" | "BLOCK" | "ESCALATE";
  action: string;
  reasons: string[];
  recommended_action: string;
  risk_state: string;
  risk_score: number;
}

export interface WebSocketEvent {
  type: string;
  event_id: string;
  seq: number;
  session_id: string;
  timestamp: string;
  [key: string]: any;
}

export interface TransactionContext {
  transaction_id: string;
  amount: number;
  currency: string;
  transaction_type: string;
  risk_sensitivity: "STANDARD" | "ELEVATED" | "CRITICAL";
}

export class DhwaniClient {
  private config: DhwaniClientConfig;
  private http: AxiosInstance;
  private activeWs: WebSocket | null = null;
  private token: string | null = null;

  constructor(config: DhwaniClientConfig) {
    this.config = {
      timeoutMs: 15000,
      ...config,
    };
    this.token = config.token || null;

    this.http = axios.create({
      baseURL: this.config.baseUrl,
      timeout: this.config.timeoutMs,
      headers: {
        "Content-Type": "application/json",
      },
    });

    this.http.interceptors.request.use((req) => {
      if (this.token) {
        req.headers.Authorization = `Bearer ${this.token}`;
      }
      return req;
    });
  }

  // ── Authentication ──────────────────────────────────────────────────────────

  public setToken(token: string) {
    this.token = token;
  }

  public async login(email: string, password: string): Promise<{ access_token: string; refresh_token: string }> {
    const res = await this.http.post("/auth/login", { email, password });
    this.token = res.data.access_token;
    return res.data;
  }

  public async register(email: string, password: string, fullName: string = ""): Promise<{ access_token: string; refresh_token: string }> {
    const res = await this.http.post("/auth/register", { email, password, full_name: fullName });
    this.token = res.data.access_token;
    return res.data;
  }

  public async refreshToken(refreshToken: string): Promise<{ access_token: string; refresh_token: string }> {
    const res = await this.http.post("/auth/refresh", { refresh_token: refreshToken });
    this.token = res.data.access_token;
    return res.data;
  }

  // ── System & Integration Capabilities ───────────────────────────────────────

  public async getHealth(): Promise<{ status: string; service: string }> {
    const res = await this.http.get("/health");
    return res.data;
  }

  public async getCapabilities(): Promise<any> {
    const res = await this.http.get("/system/capabilities");
    return res.data;
  }

  public async getIntegrationStatus(): Promise<any> {
    const res = await this.http.get("/system/integration/status");
    return res.data;
  }

  public async getPolicyConfig(): Promise<any> {
    const res = await this.http.get("/system/policy");
    return res.data;
  }

  public async getPrivacyControls(): Promise<any> {
    const res = await this.http.get("/system/privacy");
    return res.data;
  }

  public async testWebhook(body: {
    event_type?: string;
    session_id?: string;
    risk_score?: number;
    risk_state?: string;
    decision?: string;
    target_url?: string;
  }): Promise<any> {
    const res = await this.http.post("/system/webhooks/test", body);
    return res.data;
  }

  // ── Session Management ──────────────────────────────────────────────────────

  public async createSession(metadata: Record<string, any> = {}): Promise<{
    id: string;
    state: string;
    created_at: string;
  }> {
    const res = await this.http.post("/sessions", { metadata });
    return res.data;
  }

  public async startSession(sessionId: string): Promise<any> {
    const res = await this.http.post(`/sessions/${sessionId}/start`);
    return res.data;
  }

  public async stopSession(sessionId: string): Promise<any> {
    const res = await this.http.post(`/sessions/${sessionId}/stop`);
    return res.data;
  }

  public async getSession(sessionId: string): Promise<any> {
    const res = await this.http.get(`/sessions/${sessionId}`);
    return res.data;
  }

  // ── Risk & Incident Retrieval ───────────────────────────────────────────────

  public async getRisk(sessionId: string): Promise<RiskSnapshot> {
    const res = await this.http.get(`/risk/${sessionId}`);
    return res.data;
  }

  public async getOverviewStats(): Promise<any> {
    const res = await this.http.get("/incidents/stats/overview");
    return res.data;
  }

  public async listIncidents(): Promise<any[]> {
    const res = await this.http.get("/incidents");
    return res.data;
  }

  public async getIncident(incidentId: string): Promise<any> {
    const res = await this.http.get(`/incidents/${incidentId}`);
    return res.data;
  }

  // ── Audio File Analysis ─────────────────────────────────────────────────────

  public async analyzeAudioFile(formData: FormData): Promise<any> {
    const res = await this.http.post("/analysis/audio", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 60000,
    });
    return res.data;
  }

  // ── Real-Time WebSocket Streaming ───────────────────────────────────────────

  public connectStream(params: {
    sessionId: string;
    onEvent: (event: WebSocketEvent) => void;
    onError?: (err: any) => void;
    onClose?: () => void;
  }): void {
    if (this.activeWs) {
      this.closeStream();
    }

    const host = this.config.wsUrl || this.config.baseUrl.replace(/^http/, "ws");
    const wsUrl = `${host}/ws/sessions/${params.sessionId}${this.token ? `?token=${encodeURIComponent(this.token)}` : ""}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      // Stream established
    };

    ws.onmessage = (event) => {
      try {
        const payload: WebSocketEvent = JSON.parse(event.data);
        params.onEvent(payload);
      } catch (err) {
        if (params.onError) params.onError(err);
      }
    };

    ws.onerror = (err) => {
      if (params.onError) params.onError(err);
    };

    ws.onclose = () => {
      this.activeWs = null;
      if (params.onClose) params.onClose();
    };

    this.activeWs = ws;
  }

  /**
   * Send 16 kHz Mono Signed 16-bit Linear PCM audio chunk base64 encoded.
   * Standard chunk size is 250 ms (4,000 samples = 8,000 bytes).
   */
  public sendAudioChunk(base64Pcm: string): void {
    if (!this.activeWs || this.activeWs.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket stream is not connected or open.");
    }
    this.activeWs.send(
      JSON.stringify({
        type: "audio_chunk",
        data: base64Pcm,
      })
    );
  }

  public closeStream(): void {
    if (this.activeWs) {
      try {
        this.activeWs.close();
      } catch (_) {}
      this.activeWs = null;
    }
  }
}
