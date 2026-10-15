import assert from "node:assert/strict";
import test from "node:test";

import { routeMusicRequest } from "../edge/cloudflare/worker.js";

test("Cloudflare route proxies the gallery without consuming redirects", async () => {
  let forwarded: Request | undefined;
  const upstreamResponse = new Response(null, {
    status: 307,
    headers: { location: "https://bucket.example/video.mp4" },
  });
  const response = await routeMusicRequest(
    new Request("https://crotown.app/music/media/jieyue-mv-720p.mp4?download=1"),
    async (request) => {
      forwarded = request;
      return upstreamResponse;
    },
  );

  assert.equal(forwarded?.url, "https://musiccc-production.up.railway.app/music/media/jieyue-mv-720p.mp4?download=1");
  assert.equal(forwarded?.redirect, "manual");
  assert.equal(forwarded?.headers.get("x-forwarded-host"), "crotown.app");
  assert.equal(response, upstreamResponse);
  assert.equal(response.status, 307);
});

test("Cloudflare route preserves MCP method, body and content type", async () => {
  let forwarded: Request | undefined;
  await routeMusicRequest(
    new Request("https://crotown.app/music/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "tools/list", id: 1 }),
      duplex: "half",
    } as RequestInit & { duplex: "half" }),
    async (request) => {
      forwarded = request;
      return new Response("ok");
    },
  );

  assert.equal(forwarded?.method, "POST");
  assert.equal(forwarded?.headers.get("content-type"), "application/json");
  assert.deepEqual(await forwarded?.json(), { jsonrpc: "2.0", method: "tools/list", id: 1 });
});

test("Cloudflare route passes similarly named town paths to the existing origin", async () => {
  const request = new Request("https://crotown.app/musical");
  let forwarded: Request | undefined;
  await routeMusicRequest(request, async (candidate) => {
    forwarded = candidate;
    return new Response("town");
  });

  assert.equal(forwarded, request);
});
