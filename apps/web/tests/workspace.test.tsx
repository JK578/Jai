import "./setup";
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import CreateIncidentForm from "../src/components/create-incident-form";
import IncidentWorkspace from "../src/components/incident-workspace";
import { incident } from "./fixtures";

afterEach(cleanup);

function fillForm() {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: incident.title } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: incident.description } });
  fireEvent.change(screen.getByLabelText("Service name"), { target: { value: incident.service_name } });
  fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "high" } });
}

test("form rejects whitespace before sending an API request", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json(incident));
  render(<CreateIncidentForm onCreated={() => assert.fail("must not create")} />);
  fillForm();
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "   " } });
  fireEvent.submit(screen.getByRole("form", { name: "Create incident" }));
  assert.match((await screen.findByRole("alert")).textContent ?? "", /Title must contain/);
  assert.equal(fetch.mock.callCount(), 0);
});

test("form prevents duplicate submission, then resets after success", async (t) => {
  let resolve!: (response: Response) => void;
  const fetch = t.mock.method(globalThis, "fetch", () => new Promise<Response>((done) => { resolve = done; }));
  const created: string[] = [];
  render(<CreateIncidentForm onCreated={(value) => created.push(value.id)} />);
  fillForm();
  const form = screen.getByRole("form", { name: "Create incident" });
  fireEvent.submit(form);
  fireEvent.submit(form);
  assert.equal(fetch.mock.callCount(), 1);
  assert.ok(screen.getByRole("button", { name: "Creating…" }));
  assert.equal((screen.getByLabelText("Title") as HTMLInputElement).closest("fieldset")?.disabled, true);
  resolve(Response.json(incident, { status: 201 }));
  await waitFor(() => assert.deepEqual(created, [incident.id]));
  await waitFor(() => assert.equal((screen.getByLabelText("Title") as HTMLInputElement).value, ""));
});

test("failed create keeps input and offers an actionable error", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({}, { status: 502 }));
  render(<CreateIncidentForm onCreated={() => assert.fail("must not create")} />);
  fillForm();
  fireEvent.submit(screen.getByRole("form", { name: "Create incident" }));
  assert.match((await screen.findByRole("alert")).textContent ?? "", /input has been kept/);
  assert.equal((screen.getByLabelText("Title") as HTMLInputElement).value, incident.title);
});

test("workspace renders loading, empty state, then list and selected details", async (t) => {
  let resolve!: (response: Response) => void;
  const fetch = t.mock.method(globalThis, "fetch", () => new Promise<Response>((done) => { resolve = done; }));
  render(<IncidentWorkspace />);
  assert.match(screen.getByRole("status").textContent ?? "", /Loading incidents/);
  resolve(Response.json([]));
  await screen.findByText("No incidents yet. Create your first incident.");
  fetch.mock.mockImplementation(async (input) => Response.json(String(input).endsWith(incident.id) ? incident : [incident]));
  fireEvent.click(screen.getByRole("button", { name: "Refresh incidents" }));
  fireEvent.click(await screen.findByRole("button", { name: incident.title }));
  const details = screen.getByRole("region", { name: "Incident details" });
  await within(details).findByText(incident.description);
  assert.ok(within(details).getByText(incident.id));
  assert.ok(within(details).getByText("open"));
});

test("workspace recovers from list errors and reports a missing detail", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({}, { status: 502 }));
  render(<IncidentWorkspace />);
  assert.match((await screen.findByRole("alert")).textContent ?? "", /Unable to load incidents/);
  fetch.mock.mockImplementation(async (input) => String(input).endsWith(incident.id)
    ? Response.json({}, { status: 404 }) : Response.json([incident]));
  fireEvent.click(screen.getByRole("button", { name: "Refresh incidents" }));
  fireEvent.click(await screen.findByRole("button", { name: incident.title }));
  assert.match((await screen.findByRole("alert")).textContent ?? "", /Incident not found/);
  fetch.mock.mockImplementation(async () => Response.json(incident));
  fireEvent.click(screen.getByRole("button", { name: "Retry details" }));
  await within(screen.getByRole("region", { name: "Incident details" })).findByText(incident.description);
});

test("successful creation refreshes the list and opens incident details", async (t) => {
  let created = false;
  t.mock.method(globalThis, "fetch", async (input: string | URL | Request, options?: RequestInit) => {
    if (options?.method === "POST") { created = true; return Response.json(incident, { status: 201 }); }
    return Response.json(String(input).endsWith(incident.id) ? incident : created ? [incident] : []);
  });
  render(<IncidentWorkspace />);
  await screen.findByText("No incidents yet. Create your first incident.");
  fillForm();
  fireEvent.submit(screen.getByRole("form", { name: "Create incident" }));
  await screen.findByRole("button", { name: incident.title });
  await within(screen.getByRole("region", { name: "Incident details" })).findByText(incident.description);
  assert.equal((screen.getByLabelText("Title") as HTMLInputElement).value, "");
});
