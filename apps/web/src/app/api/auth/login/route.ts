import { backendRequest, cookieName, sameOrigin, readJson, PayloadTooLarge } from "../../../../lib/session";

export async function POST(request: Request): Promise<Response> {
  if (!sameOrigin(request)) return Response.json({ detail: "Invalid origin" }, { status: 403 });
  try {
    const body = await readJson(request);
    if (!body || typeof body !== "object" || !("token" in body) || typeof body.token !== "string"
      || !/^[A-Za-z0-9_-]{32,256}$/.test(body.token)) {
      return Response.json({ detail: "Invalid access token" }, { status: 400 });
    }
    const checked = await backendRequest("/api/v1/auth/session", "GET", body.token);
    if (!checked.ok) return Response.json({ detail: "Sign-in failed" }, { status: checked.status });
    const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
    return Response.json({ signed_in: true }, { headers: { "Cache-Control": "no-store",
      "Set-Cookie": `${cookieName}=${body.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400${secure}` } });
  } catch (error) {
    if (error instanceof PayloadTooLarge) return Response.json({ detail: "Request too large" }, { status: 413 });
    return Response.json({ detail: "Invalid sign-in request" }, { status: 400 });
  }
}
