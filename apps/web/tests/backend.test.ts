import assert from "node:assert/strict";
import { test } from "node:test";
import { getBackendHealth } from "../src/lib/backend";

test("readiness preserves connectivity status and reports storage without exposing configuration", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ status: "ready", storage: "postgres" }));
  assert.deepEqual(await getBackendHealth(), { status: "ready", storage: "postgres" });
  fetch.mock.mockImplementation(async () => Response.json({ status: "not_ready", storage: "postgres" }, { status: 503 }));
  assert.deepEqual(await getBackendHealth(), { status: "not_ready", storage: "postgres" });
  fetch.mock.mockImplementation(async () => { throw new Error("network unavailable"); });
  assert.deepEqual(await getBackendHealth(), { status: "unavailable" });
});
