import { createMcpHandler, McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";

import {
  assertToolResponseSize,
  formatSegmentText,
  musicCatalog,
  musicNext,
  musicSeek,
  musicStart,
  segmentTransition,
} from "./music-service.js";
import type { MusicSegment } from "./music-data.js";

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

function segmentResult(
  value: ReturnType<typeof musicStart>,
  options: { prediction?: string; previousSegment?: MusicSegment | null } = {},
) {
  const segment = value.segment;
  const structuredContent = {
    song_id: value.song_id,
    cursor: value.cursor,
    completed: value.completed,
    ...(options.prediction ? { prediction: options.prediction } : {}),
    transition: segmentTransition(options.previousSegment, segment),
    segment: segment
      ? {
          id: segment.id,
          title: segment.title,
          start_ms: segment.start_ms,
          end_ms: segment.end_ms,
          lyrics: segment.lyrics.map(({ id, text, start_ms, end_ms, performers }) => ({
            id,
            text,
            start_ms,
            end_ms,
            performers,
          })),
          music_observations: segment.music_observations.map(
            ({ id, start_ms, end_ms, description }) => ({
              id,
              start_ms,
              end_ms,
              description,
            }),
          ),
          acoustic_curves: segment.acoustic_curves.map(({ id, label, points }) => ({
            id,
            label,
            points,
          })),
          melody_contours: segment.melody_contours,
        }
      : null,
  };
  return result(structuredContent, formatSegmentText(value, options));
}

export function createMusicMcpServer(): McpServer {
  const server = new McpServer(
    { name: "jieyue-music", version: "0.1.0" },
    {
      instructions:
        "沿时间阅读歌词、演唱者、声音事件、音乐运动和旋律走向，再形成自己的理解。多人共同演唱会在歌词署名中直接标出；旋律层只呈现已有可靠曲线，不用缺省占位。使用每段返回的 cursor 继续推进；想体验期待与落差时，请在调用 music_next 前先形成猜测，并放入 prediction。",
    },
  );

  server.registerTool(
    "music_catalog",
    {
      title: "音乐目录",
      description: "列出可欣赏歌曲、版本、时长与署名。",
      inputSchema: z.object({}),
      annotations: readOnlyAnnotations,
    },
    async () => {
      const catalog = musicCatalog();
      return result(
        catalog,
        "音乐厅现收录《借月》正式版。可逐段欣赏歌词、演唱者、声音事件、音乐运动与旋律走向。",
      );
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
      return segmentResult(value);
    },
  );

  server.registerTool(
    "music_next",
    {
      title: "继续欣赏",
      description:
        "用当前游标推进到下一段；可先在 prediction 写下尚未揭晓时的猜测，结果会先重放猜测再揭晓。服务端不评判对错，也不保存猜测。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        cursor: z.string().min(1).max(512),
        prediction: z
          .string()
          .trim()
          .min(1)
          .max(600)
          .optional()
          .describe("可选：在看到下一段之前，对它会如何变化的一段简短猜测。"),
      }),
      annotations: readOnlyAnnotations,
    },
    async ({ song_id, cursor, prediction }) => {
      const previousSegment = musicSeek(song_id, { kind: "cursor", value: cursor }).segment;
      const value = musicNext(song_id, cursor);
      return segmentResult(value, {
        ...(prediction ? { prediction } : {}),
        previousSegment,
      });
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
      return segmentResult(value);
    },
  );

  return server;
}

export const musicMcpHandler = createMcpHandler(() => createMusicMcpServer(), {
  legacy: "stateless",
  responseMode: "auto",
  maxRequestBodySize: 64 * 1024,
  maxSubscriptions: 8,
  keepAliveMs: 15_000,
  onerror: (error) => console.error("MCP handler error:", error.message),
});
