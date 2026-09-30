import React from "react";
import { DhwaniClient } from "../src/sdk/DhwaniClient";
import { PROTO_DEFINITION, TYPESCRIPT_SDK_EXAMPLE, CURL_EXAMPLE } from "../src/contracts/protoDefinitions";

describe("DhwaniClient SDK & Integration Contracts", () => {
  it("initializes DhwaniClient with correct config", () => {
    const client = new DhwaniClient({
      baseUrl: "http://127.0.0.1:8000",
      wsUrl: "ws://127.0.0.1:8000",
      token: "test-bearer-token",
    });

    expect(client).toBeDefined();
    expect(typeof client.login).toBe("function");
    expect(typeof client.createSession).toBe("function");
    expect(typeof client.startSession).toBe("function");
    expect(typeof client.stopSession).toBe("function");
    expect(typeof client.getRisk).toBe("function");
    expect(typeof client.getCapabilities).toBe("function");
    expect(typeof client.getIntegrationStatus).toBe("function");
    expect(typeof client.connectStream).toBe("function");
    expect(typeof client.sendAudioChunk).toBe("function");
  });

  it("exports valid gRPC proto definition matching SIH PS26104 requirements", () => {
    expect(PROTO_DEFINITION).toContain('syntax = "proto3";');
    expect(PROTO_DEFINITION).toContain("service DhwaniSecurityService");
    expect(PROTO_DEFINITION).toContain("rpc StreamAudio");
    expect(PROTO_DEFINITION).toContain("rpc AnalyzeAudioFile");
    expect(PROTO_DEFINITION).toContain("rpc GetRiskScore");
    expect(PROTO_DEFINITION).toContain("rpc EvaluatePolicy");
  });

  it("exports TypeScript SDK and cURL examples", () => {
    expect(TYPESCRIPT_SDK_EXAMPLE).toContain("DhwaniClient");
    expect(TYPESCRIPT_SDK_EXAMPLE).toContain("client.connectStream");
    expect(CURL_EXAMPLE).toContain("curl -X POST");
    expect(CURL_EXAMPLE).toContain("/system/integration/status");
  });
});
