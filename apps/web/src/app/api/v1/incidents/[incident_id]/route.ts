import { forwardIncidentRequest } from "../../../../../lib/incident-proxy";
import { authEnabled, tokenFrom } from "../../../../../lib/session";

export async function GET(_request: Request, context: { params: Promise<{ incident_id: string }> }): Promise<Response> {
  const { incident_id } = await context.params;
  const token = tokenFrom(_request);
  if (authEnabled() && !token) return Response.json({ detail: "Sign in required" }, { status: 401 });
  return forwardIncidentRequest("GET", incident_id, undefined, token);
}
