import { test } from "node:test";
import assert from "node:assert/strict";
import { readJson, PayloadTooLarge, sameOrigin, tokenFrom } from "../src/lib/session";

test("bounded JSON rejects large and malformed bodies", async () => {
  const request = (body: string) => new Request("http://localhost/api/auth/login", { method: "POST", body });
  assert.deepEqual(await readJson(request('{"ok":true}')), { ok: true });
  await assert.rejects(readJson(request("x".repeat(65537))), PayloadTooLarge);
  await assert.rejects(readJson(request("invalid")), SyntaxError);
});

test("authenticated mutations require exact origin and valid cookie format", () => {
  const previous = process.env.INCIDENTIQ_AUTH_ENABLED;
  process.env.INCIDENTIQ_AUTH_ENABLED = "true";
  try {
    assert.equal(sameOrigin(new Request("http://localhost/api", { headers: { origin: "http://evil.example" } })), false);
    assert.equal(sameOrigin(new Request("http://localhost/api", { headers: { origin: "http://localhost" } })), true);
    assert.equal(sameOrigin(new Request("http://localhost:3001/api", { headers: { host: "127.0.0.1:3001", origin: "http://127.0.0.1:3001" } })), true);
    assert.equal(sameOrigin(new Request("http://localhost/api", { headers: { host: "evil.example", origin: "http://evil.example" } })), false);
    assert.equal(tokenFrom(new Request("http://localhost", { headers: { cookie: "incidentiq_session=short" } })), undefined);
    assert.equal(tokenFrom(new Request("http://localhost", { headers: { cookie: `incidentiq_session=${"a".repeat(48)}` } })), "a".repeat(48));
  } finally {
    if (previous === undefined) delete process.env.INCIDENTIQ_AUTH_ENABLED;
    else process.env.INCIDENTIQ_AUTH_ENABLED = previous;
  }
});
