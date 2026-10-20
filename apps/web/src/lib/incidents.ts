export const severities = ["critical", "high", "medium", "low"] as const;
export const statuses = ["open", "investigating", "resolved"] as const;
export type Severity = typeof severities[number];
export type IncidentStatus = typeof statuses[number];
export type IncidentDraft = { title: string; description: string; severity: string; service_name: string };
export type Incident = Omit<IncidentDraft, "severity"> & {
  id: string; severity: Severity; status: IncidentStatus; created_at: string; updated_at: string;
};

export function validateIncidentDraft(draft: IncidentDraft): string | null {
  for (const [label, value, limit] of [
    ["Title", draft.title, 200], ["Description", draft.description, 10000],
    ["Service name", draft.service_name, 100],
  ] as const) {
    const size = [...value.trim()].length;
    if (size < 1 || size > limit) return `${label} must contain 1 to ${limit} characters.`;
  }
  if (!severities.some((severity) => severity === draft.severity)) return "Select a valid severity.";
  return null;
}

export function isIncident(value: unknown): value is Incident {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(item.id)
    && typeof item.title === "string" && typeof item.description === "string"
    && typeof item.service_name === "string"
    && severities.some((severity) => severity === item.severity)
    && statuses.some((status) => status === item.status)
    && typeof item.created_at === "string" && Number.isFinite(Date.parse(item.created_at))
    && typeof item.updated_at === "string" && Number.isFinite(Date.parse(item.updated_at));
}

export async function fetchIncidents(signal?: AbortSignal): Promise<Incident[]> {
  const response = await fetch("/api/v1/incidents", { cache: "no-store", signal });
  if (!response.ok) throw new Error("Unable to load incidents. Check the backend and retry.");
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isIncident)) throw new Error("Invalid incident list response.");
  return body;
}

export async function fetchIncident(id: string, signal?: AbortSignal): Promise<Incident> {
  const response = await fetch(`/api/v1/incidents/${encodeURIComponent(id)}`, { cache: "no-store", signal });
  if (response.status === 404) throw new Error("Incident not found. It may have been lost after a backend restart.");
  if (!response.ok) throw new Error("Unable to load incident details. Try again.");
  const body: unknown = await response.json();
  if (!isIncident(body)) throw new Error("Invalid incident detail response.");
  return body;
}

export async function createIncident(draft: IncidentDraft): Promise<Incident> {
  const validation = validateIncidentDraft(draft);
  if (validation) throw new Error(validation);
  const response = await fetch("/api/v1/incidents", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: draft.title.trim(), description: draft.description.trim(), service_name: draft.service_name.trim(), severity: draft.severity }),
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(response.status === 422
    ? "The incident was rejected. Check all fields and try again."
    : "Unable to create incident. Your input has been kept. Check the list before retrying.");
  const body: unknown = await response.json();
  if (!isIncident(body)) throw new Error("Invalid create response. Check the list before retrying.");
  return body;
}
