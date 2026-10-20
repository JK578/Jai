export type BackendStatus = "ready" | "not_ready" | "unavailable";
export type BackendHealth = { status: BackendStatus; storage?: "memory" | "postgres" };

export async function getBackendHealth(): Promise<BackendHealth> {
  try {
    const base = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(new URL("/health/ready", base), {
      cache: "no-store", signal: AbortSignal.timeout(3000),
    });
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || !("status" in body)) {
      return { status: "unavailable" };
    }
    const storage = "storage" in body && (body.storage === "memory" || body.storage === "postgres") ? body.storage : undefined;
    if (response.ok && body.status === "ready") return { status: "ready", storage };
    if (response.status === 503 && body.status === "not_ready") return { status: "not_ready", storage };
    return { status: "unavailable" };
  } catch {
    return { status: "unavailable" };
  }
}

export async function getBackendStatus(): Promise<BackendStatus> {
  return (await getBackendHealth()).status;
}
