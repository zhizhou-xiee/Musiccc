import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import test from "node:test";

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";

import { createMusicHttpServer } from "../src/server.js";

test("/music uses prefix-safe absolute asset paths", async () => {
  const previousVideoUrl = process.env.JIEYUE_VIDEO_URL;
  const server = createMusicHttpServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  const base = `http://127.0.0.1:${address.port}`;
  try {
    const page = await fetch(`${base}/music`);
    assert.equal(page.status, 200);
    const html = await page.text();
    assert.match(html, /src="\/music\/app\.js"/);
    assert.match(html, /href="\/music\/styles\.css"/);
    assert.match(html, /src="\/music\/media\/jieyue-mv-720p\.mp4"/);

    const [script, styles, data, poster] = await Promise.all([
      fetch(`${base}/music/app.js`),
      fetch(`${base}/music/styles.css`),
      fetch(`${base}/music/data/song.json`),
      fetch(`${base}/music/assets/poster.jpg`),
    ]);
    assert.deepEqual(
      [script.status, styles.status, data.status, poster.status],
      [200, 200, 200, 200],
    );
    const song = (await data.json()) as { media: { video_url: string; poster_url: string } };
    assert.equal(song.media.video_url, "/music/media/jieyue-mv-720p.mp4");
    assert.equal(song.media.poster_url, "/music/assets/poster.jpg");

    process.env.JIEYUE_VIDEO_URL = "https://media.example/jieyue.mp4";
    const configuredSong = (await (await fetch(`${base}/music/data/song.json`)).json()) as {
      media: { video_url: string };
    };
    assert.equal(configuredSong.media.video_url, "https://media.example/jieyue.mp4");
  } finally {
    if (previousVideoUrl === undefined) delete process.env.JIEYUE_VIDEO_URL;
    else process.env.JIEYUE_VIDEO_URL = previousVideoUrl;
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

test("private Bucket media redirects to a short-lived signed URL", async () => {
  const names = [
    "JIEYUE_BUCKET_ENDPOINT",
    "JIEYUE_BUCKET_ACCESS_KEY_ID",
    "JIEYUE_BUCKET_SECRET_ACCESS_KEY",
    "JIEYUE_BUCKET_NAME",
    "JIEYUE_BUCKET_REGION",
    "JIEYUE_BUCKET_URL_STYLE",
    "JIEYUE_BUCKET_KEY",
  ] as const;
  const previous = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  Object.assign(process.env, {
    JIEYUE_BUCKET_ENDPOINT: "https://storage.example",
    JIEYUE_BUCKET_ACCESS_KEY_ID: "test-access-key",
    JIEYUE_BUCKET_SECRET_ACCESS_KEY: "test-secret-key",
    JIEYUE_BUCKET_NAME: "jieyue-media-test",
    JIEYUE_BUCKET_REGION: "auto",
    JIEYUE_BUCKET_URL_STYLE: "virtual",
    JIEYUE_BUCKET_KEY: "jieyue-mv-720p.mp4",
  });
  const server = createMusicHttpServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  try {
    const response = await fetch(
      `http://127.0.0.1:${address.port}/music/media/jieyue-mv-720p.mp4`,
      { redirect: "manual" },
    );
    assert.equal(response.status, 307);
    const location = response.headers.get("location") ?? "";
    assert.match(location, /^https:\/\/jieyue-media-test\.storage\.example\/jieyue-mv-720p\.mp4\?/);
    assert.match(location, /X-Amz-Algorithm=AWS4-HMAC-SHA256/);
    assert.doesNotMatch(location, /test-secret-key/);
  } finally {
    for (const name of names) {
      const value = previous[name];
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

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
    const startData = started.structuredContent as {
      cursor: string;
      segment: { id: string; melody_contours: Array<{ line_id: string }> };
    };
    assert.equal(startData.segment.id, "a_cappella");
    assert.deepEqual(startData.segment.melody_contours.map((item) => item.line_id), ["line-001"]);

    const next = await client.callTool({
      name: "music_next",
      arguments: {
        song_id: "jieyue",
        cursor: startData.cursor,
        prediction: "我猜清唱之后会有稀疏的伴奏进入。",
      },
    });
    const nextData = next.structuredContent as {
      prediction: string;
      transition: Array<{ previous_tail: number[]; current_head: number[] }>;
      segment: { id: string };
    };
    assert.equal(nextData.segment.id, "intro");
    assert.match(nextData.prediction, /稀疏的伴奏/);
    assert.equal(nextData.transition.length, 4);
    const nextText = next.content.find((item) => item.type === "text");
    assert.match(nextText?.text ?? "", /揭晓前的猜测[\s\S]*—— 揭晓 ——/);
    assert.match(nextText?.text ?? "", /上一段的衔接/);

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
