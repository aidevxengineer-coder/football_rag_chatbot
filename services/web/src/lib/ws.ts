/** WebSocket base for gateway pipeline events. */
export function getWsBase(): string {
  if (typeof window === "undefined") return "ws://localhost:8000";

  const secure = window.location.protocol === "https:";
  const protocol = secure ? "wss" : "ws";
  const hostname = window.location.hostname;

  // Local Next.js runs on :3000 while the gateway runs on :8000.
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${protocol}://${hostname}:8000`;
  }

  // Deployed ingress routes /ws to the gateway on the app host.
  return `${protocol}://${window.location.host}`;
}

export function pipelineWsUrl(sessionId: string): string {
  return `${getWsBase()}/ws/pipeline?session_id=${encodeURIComponent(sessionId)}`;
}
