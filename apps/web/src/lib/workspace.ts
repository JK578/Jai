export async function workspaceRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/workspace/${path}`, {
    method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const messages: Record<number, string> = { 401: "Your session expired. Refresh and sign in again.",
      403: "Your access token does not permit this action.", 404: "This item is not available in your workspace.",
      409: "The investigation changed or cannot continue. Refresh it before trying again.",
      429: "The model is busy or your daily budget is reached. Please try later." };
    throw new Error(messages[response.status] ?? "The request could not be completed. Please try again.");
  }
  return await response.json() as T;
}

export type Evidence = { event_id: string; file_id: string; source_line: number; source_path: string;
  source_commit: string; file_sha256: string; text: string };
export type Investigation = { run_id: string; question: string; provider: "mock" | "openai";
  status: string; attempt: number; report_sha256: string; published: boolean;
  remaining_conservative_microusd: number; error_code?: string;
  report?: { summary: string; findings: { claim: string; evidence_ids: string[] }[];
    uncertainties: string[]; next_steps: string[] }; evidence: Evidence[] };
