import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import test from "node:test";

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";

import { createMusicHttpServer } from "../src/server.js";

test("Streamable HTTP initializes, discovers and calls all four tools", async () => {
  const server = createMusicHttpServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  const transport = new StreamableHTTPClientTransport(
    new URL(`http://127.0.0.1:${address.port}/music/mcp`),
  );
  const client = new Client({ name: "jieyue-test", version: "1.0.0" });
  try {
    await client.connect(transport);
    const tools = await client.listTools();
    assert.deepEqual(
      tools.tools.map((tool) => tool.name).sort(),
      ["music_catalog", "music_next", "music_seek", "music_start"],
    );
    const catalog = await client.callTool({ name: "music_catalog", arguments: {} });
    assert.equal(catalog.isError, undefined);

    const started = await client.callTool({ name: "music_start", arguments: { song_id: "jieyue" } });
    const startData = started.structuredContent as { cursor: string; segment: { id: string } };
    assert.equal(startData.segment.id, "a_cappella");

    const next = await client.callTool({
      name: "music_next",
      arguments: { song_id: "jieyue", cursor: startData.cursor },
    });
    assert.equal((next.structuredContent as { segment: { id: string } }).segment.id, "intro");

    const seek = await client.callTool({
      name: "music_seek",
      arguments: { song_id: "jieyue", target: { kind: "line_id", value: "line-005" } },
    });
    assert.equal((seek.structuredContent as { segment: { id: string } }).segment.id, "verse_1");
  } finally {
    await client.close();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

test("modern MCP era negotiates over the same endpoint", async () => {
  const server = createMusicHttpServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  const transport = new StreamableHTTPClientTransport(
    new URL(`http://127.0.0.1:${address.port}/music/mcp`),
  );
  const client = new Client(
    { name: "jieyue-modern-test", version: "1.0.0" },
    { versionNegotiation: { mode: "auto" } },
  );
  try {
    await client.connect(transport);
    assert.equal(client.getProtocolEra(), "modern");
    assert.equal((await client.listTools()).tools.length, 4);
  } finally {
    await client.close();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
