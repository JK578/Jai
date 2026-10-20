import { forwardIncidentRequest } from "../../../../lib/incident-proxy";

export async function GET(): Promise<Response> {
  return forwardIncidentRequest("GET");
}

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  return forwardIncidentRequest("POST", undefined, body);
}
