/** Server-only adapter: browser requests never choose the upstream URL. */
export async function forwardIncidentRequest(method: "GET" | "POST", id?: string, body?: unknown, token?: string): Promise<Response> {
  if (id && !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
    return Response.json({ detail: "Invalid incident ID" }, { status: 422 });
  }
  try {
    const path = `/api/v1/incidents${id ? `/${id}` : ""}`;
    const url = new URL(path, process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
    const response = await fetch(url, {
      method, cache: "no-store", signal: AbortSignal.timeout(5000),
      headers: token ? { Authorization: `Bearer ${token}`, ...(method === "POST" ? { "Content-Type": "application/json" } : {}) }
        : method === "POST" ? { "Content-Type": "application/json" } : undefined,
      body: method === "POST" ? JSON.stringify(body) : undefined,
    });
    if (response.status >= 500) {
      return Response.json({ detail: "Backend unavailable" }, { status: 502 });
    }
    const data: unknown = await response.json();
    const headers: Record<string, string> = { "Cache-Control": "no-store" };
    const location = response.headers.get("Location");
    if (response.status === 201 && location?.startsWith("/api/v1/incidents/")) headers.Location = location;
    return Response.json(data, { status: response.status, headers });
  } catch {
    return Response.json({ detail: "Backend unavailable" }, { status: 502 });
  }
}
