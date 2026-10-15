import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { extname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { hostHeaderValidation, originValidation, toNodeHandler } from "@modelcontextprotocol/node";

import { musicMcpHandler } from "./mcp.js";
import { signedBucketVideoUrl } from "./bucket-media.js";
import { createRateLimiter } from "./rate-limit.js";

const projectRoot = fileURLToPath(new URL("../..", import.meta.url));
const webRoot = resolve(projectRoot, "web", "music");
const mcpNodeHandler = toNodeHandler(musicMcpHandler, {
  maxRequestBodySize: 64 * 1024,
  onerror: (error) => console.error("MCP adapter error:", error.message),
});
const allowMcpRequest = createRateLimiter(60, 60_000);
const maxConcurrentMcpRequests = 20;
let concurrentMcpRequests = 0;

const contentTypes: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".mp4": "video/mp4",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function allowedHostnames(): string[] {
  const values = new Set(["localhost", "127.0.0.1", "[::1]", "crotown.app"]);
  for (const value of (process.env.ALLOWED_HOSTS ?? "").split(",")) {
    if (value.trim()) values.add(value.trim());
  }
  if (process.env.RAILWAY_PUBLIC_DOMAIN) values.add(process.env.RAILWAY_PUBLIC_DOMAIN);
  if (process.env.PUBLIC_BASE_URL) values.add(new URL(process.env.PUBLIC_BASE_URL).hostname);
  return [...values];
}

function clientKey(request: IncomingMessage): string {
  const forwarded = request.headers["x-forwarded-for"];
  if (typeof forwarded === "string") return forwarded.split(",", 1)[0]?.trim() || "unknown";
  return request.socket.remoteAddress ?? "unknown";
}

function securityHeaders(response: ServerResponse): void {
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  response.setHeader("Content-Security-Policy", "default-src 'self'; media-src 'self' https:; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'");
}

function sendJson(response: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-store",
  });
  response.end(payload);
}

function serveSongData(response: ServerResponse): void {
  const path = resolve(webRoot, "data", "song.json");
  const payload = JSON.parse(readFileSync(path, "utf8")) as {
    media: { video_url: string };
  };
  const configuredVideoUrl = process.env.JIEYUE_VIDEO_URL?.trim();
  if (configuredVideoUrl) {
    const url = new URL(configuredVideoUrl);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      throw new Error("JIEYUE_VIDEO_URL must use http or https");
    }
    payload.media.video_url = url.href;
  }
  sendJson(response, 200, payload);
}

function serveFile(request: IncomingMessage, response: ServerResponse, path: string): void {
  if (!existsSync(path) || !statSync(path).isFile()) {
    sendJson(response, 404, { error: "not_found" });
    return;
  }
  const stat = statSync(path);
  const type = contentTypes[extname(path).toLowerCase()] ?? "application/octet-stream";
  const range = request.headers.range;
  response.setHeader("Content-Type", type);
  response.setHeader("Accept-Ranges", "bytes");
  response.setHeader("Cache-Control", type.startsWith("video/") ? "public, max-age=86400" : "public, max-age=3600");

  if (range && type.startsWith("video/")) {
    const match = /^bytes=(\d+)-(\d*)$/.exec(range);
    const start = match ? Number(match[1]) : Number.NaN;
    const requestedEnd = match?.[2] ? Number(match[2]) : stat.size - 1;
    const end = Math.min(requestedEnd, stat.size - 1);
    if (!Number.isInteger(start) || start < 0 || start > end) {
      response.writeHead(416, { "Content-Range": `bytes */${stat.size}` });
      response.end();
      return;
    }
    response.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${stat.size}`,
      "Content-Length": end - start + 1,
    });
    if (request.method === "HEAD") response.end();
    else createReadStream(path, { start, end }).pipe(response);
    return;
  }

  response.writeHead(200, { "Content-Length": stat.size });
  if (request.method === "HEAD") response.end();
  else createReadStream(path).pipe(response);
}

function staticPath(pathname: string): string | null {
  const paths: Record<string, string> = {
    "/music": "index.html",
    "/music/": "index.html",
    "/music/app.js": "app.js",
    "/music/styles.css": "styles.css",
    "/music/assets/poster.jpg": "assets/poster.jpg",
    "/music/data/song.json": "data/song.json",
    "/music/media/jieyue-mv-720p.mp4": "media/jieyue-mv-720p.mp4",
  };
  const relative = paths[pathname];
  return relative ? resolve(webRoot, relative) : null;
}

export function createMusicHttpServer() {
  const hosts = allowedHostnames();
  const validateHost = hostHeaderValidation(hosts);
  const validateOrigin = originValidation(hosts);
  const server = createServer((request, response) => {
    securityHeaders(response);
    if (!validateHost(request, response) || !validateOrigin(request, response)) return;
    const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
    if (pathname === "/healthz") {
      sendJson(response, 200, { ok: true, service: "jieyue-music" });
      return;
    }
    if (pathname === "/") {
      response.writeHead(308, { Location: "/music" });
      response.end();
      return;
    }
    if (pathname === "/music/mcp") {
      const limit = allowMcpRequest(clientKey(request));
      if (!limit.allowed) {
        response.setHeader("Retry-After", limit.retryAfterSeconds);
        sendJson(response, 429, { error: "rate_limited" });
        return;
      }
      if (concurrentMcpRequests >= maxConcurrentMcpRequests) {
        response.setHeader("Retry-After", "1");
        sendJson(response, 503, { error: "mcp_concurrency_limit" });
        return;
      }
      concurrentMcpRequests += 1;
      let released = false;
      const release = () => {
        if (released) return;
        released = true;
        concurrentMcpRequests -= 1;
      };
      response.once("finish", release);
      response.once("close", release);
      void mcpNodeHandler(request as Parameters<typeof mcpNodeHandler>[0], response).catch((error: unknown) => {
        release();
        if (!response.headersSent) sendJson(response, 500, { error: "mcp_request_failed" });
        console.error("MCP request failed:", error instanceof Error ? error.message : "unknown error");
      });
      return;
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      response.setHeader("Allow", "GET, HEAD");
      sendJson(response, 405, { error: "method_not_allowed" });
      return;
    }
    if (pathname === "/music/media/jieyue-mv-720p.mp4") {
      void signedBucketVideoUrl()
        .then((url) => {
          if (url) {
            response.writeHead(307, {
              Location: url,
              "Cache-Control": "private, max-age=300",
            });
            response.end();
            return;
          }
          serveFile(request, response, resolve(webRoot, "media", "jieyue-mv-720p.mp4"));
        })
        .catch((error: unknown) => {
          console.error("Bucket video URL failed:", error instanceof Error ? error.message : "unknown error");
          if (!response.headersSent) sendJson(response, 503, { error: "video_temporarily_unavailable" });
        });
      return;
    }
    if (pathname === "/music/data/song.json") {
      try {
        serveSongData(response);
      } catch (error) {
        console.error("Song data failed:", error instanceof Error ? error.message : "unknown error");
        sendJson(response, 500, { error: "song_data_failed" });
      }
      return;
    }
    const path = staticPath(pathname);
    if (!path) {
      sendJson(response, 404, { error: "not_found" });
      return;
    }
    serveFile(request, response, path);
  });
  server.requestTimeout = 30_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  return server;
}

async function main(): Promise<void> {
  const port = Number(process.env.PORT ?? 3000);
  // Railway and other container platforms route traffic to the container's
  // network interface. Binding only to loopback makes a healthy process look
  // unreachable to the platform edge, so default to all interfaces. Local
  // development remains reachable at localhost as usual.
  const host = process.env.HOST ?? "0.0.0.0";
  const server = createMusicHttpServer();
  server.listen(port, host, () => console.log(`JieYue Music listening on http://${host}:${port}/music`));
  let shuttingDown = false;
  const shutdown = async (signal: NodeJS.Signals) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`Received ${signal}; draining JieYue Music`);

    const forceClose = setTimeout(() => server.closeAllConnections(), 10_000);
    forceClose.unref();
    try {
      await Promise.all([
        new Promise<void>((resolveClose, rejectClose) => {
          server.close((error) => (error ? rejectClose(error) : resolveClose()));
          server.closeIdleConnections();
        }),
        musicMcpHandler.close(),
      ]);
      console.log("JieYue Music stopped cleanly");
    } catch (error) {
      process.exitCode = 1;
      console.error("JieYue Music shutdown failed:", error);
    } finally {
      clearTimeout(forceClose);
    }
  };
  process.once("SIGINT", () => void shutdown("SIGINT"));
  process.once("SIGTERM", () => void shutdown("SIGTERM"));
}

const entry = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (import.meta.url === entry) void main();
