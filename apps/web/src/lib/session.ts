/** Server-side request helpers. Access tokens are never returned in JSON. */
export const authEnabled = () => process.env.INCIDENTIQ_AUTH_ENABLED === "true";
export const cookieName = "incidentiq_session";

export class PayloadTooLarge extends Error {}

export async function readJson(request: Request): Promise<unknown> {
  const reader = request.body?.getReader();
  if (!reader) throw new SyntaxError("Missing JSON");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 65536 || chunks.length >= 128) {
        await reader.cancel();
        throw new PayloadTooLarge();
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

export function tokenFrom(request: Request): string | undefined {
  const value = request.headers.get("cookie")?.split(";").map(x => x.trim())
    .find(x => x.startsWith(`${cookieName}=`))?.slice(cookieName.length + 1);
  return value && /^[A-Za-z0-9_-]{32,256}$/.test(value) ? value : undefined;
}

export function sameOrigin(request: Request): boolean {
  if (!authEnabled()) return true;
  const url = new URL(request.url);
  const host = request.headers.get("host") ?? url.host;
  try {
    const expected = new URL(`${url.protocol}//${host}`);
    return ["localhost", "127.0.0.1"].includes(expected.hostname)
      && request.headers.get("origin") === expected.origin;
  } catch { return false; }
}

export async function backendRequest(path: string, method: string, token?: string, body?: unknown): Promise<Response> {
  if (authEnabled() && !token) return Response.json({ detail: "Sign in required" }, { status: 401 });
  try {
    const response = await fetch(new URL(path, process.env.BACKEND_URL ?? "http://127.0.0.1:8000"), {
      method, cache: "no-store", signal: AbortSignal.timeout(60000),
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data: unknown = await response.json();
    return Response.json(data, { status: response.status, headers: { "Cache-Control": "no-store", Vary: "Cookie" } });
  } catch {
    return Response.json({ detail: "Backend unavailable" }, { status: 502 });
  }
}
