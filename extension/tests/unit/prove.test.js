// Server identity proof: the device credential goes only to a server that proves it issued it (or to an address the
// user set themselves). A tampered config.json pointing elsewhere gets nothing.
import { createHash, createHmac } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";

const store = vi.hoisted(() => new Map());
vi.mock("../../src/lib/vault.js", () => ({
  vault: {
    get: async (k) => store.get(k),
    set: async (k, v) => { store.set(k, v); },
    remove: async (k) => { store.delete(k); },
    clear: async () => { store.clear(); },
  },
}));

const { expectedProof, jobpilot, newNonce, sameString, verifyProof } = await import("../../src/lib/api.js");

const TOKEN = "jpx_secret-device-credential-0123456789";
const GOOD = "https://good.example";
const EVIL = "https://evil.example";
const nodeProof = (token, nonce) =>
  createHmac("sha256", createHash("sha256").update(token).digest()).update(`jobpilot-prove:${nonce}`).digest("hex");
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

/** A fake network: `server(url, init)` answers; every call is recorded so we can check what left the extension. */
function network(server) {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, init = {}) => { calls.push({ url: String(url), init }); return server(String(url), init); });
  return calls;
}
const leaked = (calls) => calls.some(({ url, init }) => url.includes(TOKEN) || String(init.body || "").includes(TOKEN)
  || Object.values(init.headers || {}).some((v) => String(v).includes(TOKEN)));

beforeEach(() => {
  store.clear();
  store.set("token", TOKEN);
  store.set("tokenInfo", { id: 41, issuedAt: Date.now(), expiresAt: null, user: "Test" });
});

describe("proof computation (pure)", () => {
  it("matches the server's HMAC-SHA256 keyed with SHA-256(credential) over 'jobpilot-prove:' + nonce", async () => {
    const nonce = newNonce();
    expect(nonce).toMatch(/^[0-9a-f]{64}$/);
    expect(newNonce()).not.toBe(nonce);
    expect(await expectedProof(TOKEN, nonce)).toBe(nodeProof(TOKEN, nonce));
    expect(await verifyProof(TOKEN, nonce, nodeProof(TOKEN, nonce))).toBe(true);
    expect(await verifyProof(TOKEN, nonce, nodeProof(TOKEN, nonce).toUpperCase())).toBe(true);
  });

  it("rejects a wrong, missing or malformed proof, and a proof for another nonce or credential", async () => {
    const nonce = newNonce();
    expect(await verifyProof(TOKEN, nonce, nodeProof("another-credential", nonce))).toBe(false);
    expect(await verifyProof(TOKEN, nonce, nodeProof(TOKEN, newNonce()))).toBe(false);
    expect(await verifyProof(TOKEN, nonce, "0".repeat(64))).toBe(false);
    for (const bad of [null, undefined, "", "xyz", 42, {}]) expect(await verifyProof(TOKEN, nonce, bad)).toBe(false);
    expect(sameString("abc", "abc")).toBe(true);
    expect(sameString("abc", "abd")).toBe(false);
    expect(sameString("abc", "abcd")).toBe(false);
  });
});

describe("authenticated requests", () => {
  it("prove the published server first (without the credential), then send it, and remember the verified address", async () => {
    store.set("apiBase", GOOD);
    const calls = network((url, init) => {
      if (url === `${GOOD}/api/v1/extension/prove`) {
        const { token_id: id, nonce } = JSON.parse(init.body);
        expect(id).toBe(41);
        expect(nonce).toMatch(/^[0-9a-f]{64}$/);
        return json(200, { proof: nodeProof(TOKEN, nonce) });
      }
      if (url === `${GOOD}/api/v1/extension/status`) return json(200, { connected: true });
      return json(404, {});
    });
    expect(await jobpilot.status()).toEqual({ connected: true });
    expect(calls.map((c) => c.url)).toEqual([`${GOOD}/api/v1/extension/prove`, `${GOOD}/api/v1/extension/status`]);
    expect(calls[0].init.headers.Authorization).toBeUndefined();
    expect(leaked([calls[0]])).toBe(false);
    expect(calls[1].init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(store.get("verifiedBase")).toBe(GOOD);
    // Already verified: no second proof.
    await jobpilot.status();
    expect(calls.filter((c) => c.url.endsWith("/prove"))).toHaveLength(1);
  });

  it("never send the credential (or download a resume) when a tampered address cannot prove itself", async () => {
    store.set("apiBase", EVIL);
    store.set("verifiedBase", GOOD);  // the address changed since it was verified
    const calls = network((url) => (url.endsWith("/prove") ? json(200, { proof: "ab".repeat(32) }) : json(200, { ok: true })));
    await expect(jobpilot.status()).rejects.toThrow(/could not be verified, so nothing was sent/);
    await expect(jobpilot.resume({ kind: "upload" })).rejects.toThrow(/could not be verified/);
    await expect(jobpilot.answers(["Why us?"], 3)).rejects.toThrow(/could not be verified/);
    expect(calls.every((c) => c.url === `${EVIL}/api/v1/extension/prove`)).toBe(true);
    expect(leaked(calls)).toBe(false);
    expect(store.get("verifiedBase")).toBe(GOOD);
    expect(store.get("token")).toBe(TOKEN);  // not disconnected: the user can fix the address
  });

  it("treat an unknown credential (404) as unverified", async () => {
    store.set("apiBase", EVIL);
    const calls = network(() => json(404, { detail: "Unknown connection." }));
    await expect(jobpilot.profile()).rejects.toThrow(/could not be verified/);
    expect(leaked(calls)).toBe(false);
    expect(calls).toHaveLength(1);
  });

  it("trust an address the user set themselves", async () => {
    store.set("apiBaseOverride", "https://mine.example");
    const calls = network(() => json(200, { connected: true }));
    await jobpilot.status();
    expect(calls.map((c) => c.url)).toEqual(["https://mine.example/api/v1/extension/status"]);
  });

  it("after pairing, the server that issued the credential is the verified one", async () => {
    store.clear();
    store.set("apiBase", GOOD);
    network(() => json(201, { token: TOKEN, token_id: 7, expires_at: null, scopes: [], user_display_name: "Test" }));
    await jobpilot.pair("ABC123", "Chrome");
    expect(store.get("verifiedBase")).toBe(GOOD);
    expect(store.get("tokenInfo").id).toBe(7);
  });
});
