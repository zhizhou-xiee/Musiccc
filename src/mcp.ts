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
import { musicData, type MusicSegment } from "./music-data.js";
import { listeningProgress } from "./listening-progress.js";

const readOnlyAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false,
};

const savedProgressAnnotations = {
  readOnlyHint: false,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false,
};

const advancingProgressAnnotations = {
  ...savedProgressAnnotations,
  idempotentHint: false,
};

function result(structuredContent: Record<string, unknown>, text: string) {
  const value = { structuredContent, content: [{ type: "text" as const, text }] };
  assertToolResponseSize(value);
  return value;
}

function segmentResult(
  value: ReturnType<typeof musicStart>,
  options: { prediction?: string; previousSegment?: MusicSegment | null; listenerId?: string } = {},
) {
  const segment = value.segment;
  const structuredContent = {
    song_id: value.song_id,
    cursor: value.cursor,
    progress: segment
      ? { current: segment.index + 1, total: musicData.segments.length, listener_id: options.listenerId }
      : {
          current: musicData.segments.length,
          total: musicData.segments.length,
          listener_id: options.listenerId,
        },
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
    { name: "jieyue-music", version: "0.2.0" },
    {
      instructions:
        "沿时间阅读歌词、演唱者、声音事件、音乐运动和旋律走向，再形成自己的理解。第一次欣赏时，为自己选一个稳定、无私人信息的 listener_id；同一个 listener_id 会自动续接上次进度。除非明确想从头重听，不要使用 restart。每段也会返回一个短续听码，可在服务重启后交给 music_start 的 resume_cursor 恢复。想体验期待与落差时，请在调用 music_next 前先形成猜测，并放入 prediction。",
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
      title: "开始或继续欣赏",
      description:
        "首次调用会从第一段开始并保存进度；以后使用相同 listener_id 会从上次位置继续。只有明确重听时才设置 restart。若服务重启，可用上一段的短续听码 resume_cursor 恢复。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        listener_id: z
          .string()
          .trim()
          .min(3)
          .max(64)
          .describe("为自己选择的稳定代号；不要包含私人信息。不同听众必须使用不同代号。"),
        resume_cursor: z
          .string()
          .trim()
          .min(1)
          .max(512)
          .optional()
          .describe("可选：上次返回的短续听码，用于服务重启后的恢复。"),
        restart: z.boolean().optional().describe("仅在明确希望从头重听时设为 true。"),
      }),
      annotations: savedProgressAnnotations,
    },
    async ({ song_id, listener_id, resume_cursor, restart }) => {
      const savedCursor = restart ? undefined : listeningProgress.get(listener_id);
      const cursor = restart ? undefined : (resume_cursor ?? savedCursor);
      const value = cursor
        ? musicSeek(song_id, { kind: "cursor", value: cursor })
        : musicStart(song_id);
      listeningProgress.set(listener_id, value.cursor);
      return segmentResult(value, { listenerId: listener_id });
    },
  );

  server.registerTool(
    "music_next",
    {
      title: "继续欣赏",
      description:
        "按 listener_id 保存的进度推进到下一段，不必手动抄游标；也可显式提供 cursor 覆盖保存位置。可先在 prediction 写下尚未揭晓时的猜测。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        listener_id: z.string().trim().min(3).max(64),
        cursor: z.string().min(1).max(512).optional(),
        prediction: z
          .string()
          .trim()
          .min(1)
          .max(600)
          .optional()
          .describe("可选：在看到下一段之前，对它会如何变化的一段简短猜测。"),
      }),
      annotations: advancingProgressAnnotations,
    },
    async ({ song_id, listener_id, cursor, prediction }) => {
      const currentCursor = cursor ?? listeningProgress.get(listener_id);
      if (!currentCursor) {
        throw new Error("还没有保存的欣赏进度；请先调用 music_start。若手边有续听码，也可作为 cursor 传入。");
      }
      const previousSegment = musicSeek(song_id, { kind: "cursor", value: currentCursor }).segment;
      const value = musicNext(song_id, currentCursor);
      listeningProgress.set(listener_id, value.cursor);
      return segmentResult(value, {
        ...(prediction ? { prediction } : {}),
        previousSegment,
        listenerId: listener_id,
      });
    },
  );

  server.registerTool(
    "music_seek",
    {
      title: "跳转或回听",
      description: "按毫秒、段落 ID、歌词行 ID 或续听码跳转；跳转位置会保存到该 listener_id。",
      inputSchema: z.object({
        song_id: z.literal("jieyue"),
        listener_id: z.string().trim().min(3).max(64),
        target: z.discriminatedUnion("kind", [
          z.object({ kind: z.literal("time_ms"), value: z.number().int().min(0).max(249594) }),
          z.object({ kind: z.literal("section_id"), value: z.string().min(1).max(64) }),
          z.object({ kind: z.literal("line_id"), value: z.string().min(1).max(64) }),
          z.object({ kind: z.literal("cursor"), value: z.string().min(1).max(512) }),
        ]),
      }),
      annotations: savedProgressAnnotations,
    },
    async ({ song_id, listener_id, target }) => {
      const value = musicSeek(song_id, target);
      listeningProgress.set(listener_id, value.cursor);
      return segmentResult(value, { listenerId: listener_id });
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
