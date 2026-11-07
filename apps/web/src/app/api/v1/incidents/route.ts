import { forwardIncidentRequest } from "../../../../lib/incident-proxy";
import { authEnabled, tokenFrom, sameOrigin, readJson, PayloadTooLarge } from "../../../../lib/session";

export async function GET(request: Request): Promise<Response> {
  const token = tokenFrom(request);
  if (authEnabled() && !token) return Response.json({ detail: "Sign in required" }, { status: 401 });
  return forwardIncidentRequest("GET", undefined, undefined, token);
}

export async function POST(request: Request): Promise<Response> {
  if (!sameOrigin(request)) return Response.json({ detail: "Invalid origin" }, { status: 403 });
  const token = tokenFrom(request);
  if (authEnabled() && !token) return Response.json({ detail: "Sign in required" }, { status: 401 });
  let body: unknown;
  try {
    body = await readJson(request);
  } catch (error) {
    if (error instanceof PayloadTooLarge) return Response.json({ detail: "Request too large" }, { status: 413 });
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  return forwardIncidentRequest("POST", undefined, body, token);
}
