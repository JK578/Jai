export type BackendStatus = "ready" | "not_ready" | "unavailable";

export async function getBackendStatus(): Promise<BackendStatus> {
  try {
    const base = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(new URL("/health/ready", base), {
      cache: "no-store", signal: AbortSignal.timeout(3000),
    });
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || !("status" in body)) {
      return "unavailable";
    }
    if (response.ok && body.status === "ready") return "ready";
    if (response.status === 503 && body.status === "not_ready") return "not_ready";
    return "unavailable";
  } catch {
    return "unavailable";
  }
}
