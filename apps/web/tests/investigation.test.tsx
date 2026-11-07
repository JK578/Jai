import "./setup";
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import InvestigationWorkspace from "../src/components/investigation-workspace";

afterEach(cleanup);

test("investigation requires explicit approval of the displayed digest", async (t) => {
  const draft = { run_id: "00000000-0000-0000-0000-000000000001", question: "Review source",
    status: "awaiting_approval", provider: "mock", attempt: 0, report_sha256: "a".repeat(64),
    published: false, evidence: [], report: { summary: "Unverified draft", findings: [],
      uncertainties: ["Cause unknown"], next_steps: ["Review logs"] } };
  const mutations: { path: string; body: unknown }[] = [];
  t.mock.method(globalThis, "fetch", async (input: string | URL | Request, options?: RequestInit) => {
    if (options?.method !== "POST") return Response.json({ items: [] });
    mutations.push({ path: String(input), body: JSON.parse(String(options.body)) });
    return Response.json(String(input).endsWith("/approve") ? { ...draft, status: "completed", published: true } : draft);
  });
  render(<InvestigationWorkspace scopes={["investigations:write", "investigations:approve"]} />);
  fireEvent.change(screen.getByLabelText("Investigation question"), { target: { value: draft.question } });
  fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  const approve = await screen.findByRole("button", { name: "Approve & save report" });
  await waitFor(() => assert.equal((approve as HTMLButtonElement).disabled, false));
  assert.equal(mutations.length, 1);
  assert.equal(screen.queryByRole("button", { name: "Download approved report" }), null);
  fireEvent.click(approve);
  await screen.findByRole("button", { name: "Download approved report" });
  assert.deepEqual(mutations[1].body, { report_sha256: draft.report_sha256 });
});
