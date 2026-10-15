import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";

import {
  assertToolResponseSize,
  formatSegmentText,
  musicCatalog,
  musicNext,
  musicSeek,
  musicStart,
} from "./music-service.js";

const readOnlyAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false,
};

function result(structuredContent: Record<string, unknown>, text: string) {
  const value = { structuredContent, content: [{ type: "text" as const, text }] };
  assertToolResponseSize(value);
  return value;
}

export function createMusicMcpServer(): McpServer {
  const server = new McpServer(
    { name: "jieyue-music", version: "0.1.0" },
    {
      instructions:
        "逐段欣赏《借月》。返回的是人工听音事实与离线曲线，不代表你直接听见了原始音频；请把事实与自己的联想分开。",
    },
  );

  server.registerTool(
    "music_catalog",
    {
      title: "音乐目录",
      description: "列出可欣赏歌曲、版本、时长、署名与音乐感知说明。",
      inputSchema: z.object({}),
      annotations: readOnlyAnnotations,
    },
    async () => {
      const catalog = musicCatalog();
      return result(catalog, "当前目录收录《借月》正式版。音乐感知内容为预生成客观摘要与离线曲线，并非原始音频输入。");
    },
  );

  server.registerTool(
    "music_start",
    {
      title: "开始欣赏",
      description: "从指定歌曲第一段开始，返回当前段和客户端自持游标。",
      inputSchema: z.object({ song_id: z.literal("jieyue") }),
      annotations: readOnlyAnnotations,
    },
    async ({ song_id }) => {
      const value = musicStart(song_id);
      return result(value as unknown as Record<string, unknown>, formatSegmentText(value));
    },
  );

  server.registerTool(
    "music_next",
    {
      title: "继续欣赏",
      description: "用当前游标推进到下一段；不等待真实播放时长，同一游标重复调用结果一致。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        cursor: z.string().min(1).max(512),
      }),
      annotations: readOnlyAnnotations,
    },
    async ({ song_id, cursor }) => {
      const value = musicNext(song_id, cursor);
      return result(value as unknown as Record<string, unknown>, formatSegmentText(value));
    },
  );

  server.registerTool(
    "music_seek",
    {
      title: "跳转或回听",
      description: "按毫秒、段落 ID、歌词行 ID 或旧游标跳转；可用于回听且不修改任何服务端会话。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        target: z.discriminatedUnion("kind", [
          z.object({ kind: z.literal("time_ms"), value: z.number().int().min(0).max(249594) }),
          z.object({ kind: z.literal("section_id"), value: z.string().min(1).max(64) }),
          z.object({ kind: z.literal("line_id"), value: z.string().min(1).max(64) }),
          z.object({ kind: z.literal("cursor"), value: z.string().min(1).max(512) }),
        ]),
      }),
      annotations: readOnlyAnnotations,
    },
    async ({ song_id, target }) => {
      const value = musicSeek(song_id, target);
      return result(value as unknown as Record<string, unknown>, formatSegmentText(value));
    },
  );

  return server;
}

export const musicMcpHandler = createMcpHandler(() => createMusicMcpServer(), {
  legacy: "stateless",
  responseMode: "json",
  maxRequestBodySize: 64 * 1024,
  maxSubscriptions: 8,
  keepAliveMs: 15_000,
  onerror: (error) => console.error("MCP handler error:", error.message),
});
