import { forwardIncidentRequest } from "../../../../../lib/incident-proxy";

export async function GET(_request: Request, context: { params: Promise<{ incident_id: string }> }): Promise<Response> {
  const { incident_id } = await context.params;
  return forwardIncidentRequest("GET", incident_id);
}
