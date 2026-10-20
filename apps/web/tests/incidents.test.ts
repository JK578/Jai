import assert from "node:assert/strict";
import { test } from "node:test";
import { createIncident, fetchIncident, fetchIncidents, validateIncidentDraft } from "../src/lib/incidents";
import { forwardIncidentRequest } from "../src/lib/incident-proxy";
import { POST } from "../src/app/api/v1/incidents/route";
import { incident } from "./fixtures";

test("validation rejects whitespace, oversized fields and unknown severity", () => {
  assert.equal(validateIncidentDraft(incident), null);
  for (const patch of [{ title: " " }, { description: " " }, { service_name: " " },
    { title: "x".repeat(201) }, { description: "x".repeat(10001) }, { service_name: "x".repeat(101) }, { severity: "urgent" }]) {
    assert.ok(validateIncidentDraft({ ...incident, ...patch }));
  }
});

test("create validates before fetch and trims outgoing data", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json(incident, { status: 201 }));
  await assert.rejects(createIncident({ ...incident, title: " " }), /Title/);
  assert.equal(fetch.mock.callCount(), 0);
  assert.deepEqual(await createIncident({ ...incident, title: " Checkout unavailable " }), incident);
  const options = fetch.mock.calls[0].arguments[1] as RequestInit;
  assert.equal(JSON.parse(String(options.body)).title, incident.title);
  assert.equal("id" in JSON.parse(String(options.body)), false);
});

test("client rejects malformed API responses and distinguishes not found", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ unexpected: true }));
  await assert.rejects(fetchIncidents(), /Invalid incident list/);
  await assert.rejects(fetchIncident(incident.id), /Invalid incident detail/);
  fetch.mock.mockImplementation(async () => Response.json({}, { status: 404 }));
  await assert.rejects(fetchIncident(incident.id), /Incident not found/);
});

test("proxy forwards status, body and location without caching", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json(incident, {
    status: 201, headers: { Location: `/api/v1/incidents/${incident.id}` },
  }));
  const response = await forwardIncidentRequest("POST", undefined, { title: "test" });
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), incident);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("location"), `/api/v1/incidents/${incident.id}`);
  const target = fetch.mock.calls[0].arguments[0] as URL;
  assert.equal(target.pathname, "/api/v1/incidents");
});

test("proxy rejects invalid ids and JSON, and sanitizes backend failures", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("sensitive exception", { status: 500 }));
  assert.equal((await forwardIncidentRequest("GET", "../secret")).status, 422);
  const badJson = new Request("http://localhost/api/v1/incidents", { method: "POST", body: "{" });
  assert.equal((await POST(badJson)).status, 400);
  assert.equal(fetch.mock.callCount(), 0);
  const response = await forwardIncidentRequest("GET");
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { detail: "Backend unavailable" });
  fetch.mock.mockImplementation(async () => { throw new Error("offline"); });
  assert.equal((await forwardIncidentRequest("GET")).status, 502);
});
