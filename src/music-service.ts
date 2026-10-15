import { musicData, type MusicSegment } from "./music-data.js";

const CURSOR_VERSION = musicData.revision;
const MAX_TOOL_RESPONSE_BYTES = 32 * 1024;

interface CursorPayload {
  v: string;
  song: string;
  index: number;
}

export interface SegmentEnvelope {
  song_id: string;
  revision: string;
  cursor: string;
  completed: boolean;
  segment: MusicSegment | null;
  perception_route: string;
  perception_notice: string;
  unknown: string[];
}

export type SeekTarget =
  | { kind: "time_ms"; value: number }
  | { kind: "section_id"; value: string }
  | { kind: "line_id"; value: string }
  | { kind: "cursor"; value: string };

function requireSong(songId: string): void {
  if (songId !== musicData.song.id) {
    throw new Error(`Unknown song_id: ${songId}`);
  }
}

export function encodeCursor(index: number): string {
  const payload: CursorPayload = { v: CURSOR_VERSION, song: musicData.song.id, index };
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

export function decodeCursor(cursor: string): CursorPayload {
  if (cursor.length > 512) throw new Error("Cursor is too long");
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
  } catch {
    throw new Error("Invalid cursor encoding");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    (parsed as CursorPayload).v !== CURSOR_VERSION ||
    (parsed as CursorPayload).song !== musicData.song.id ||
    !Number.isInteger((parsed as CursorPayload).index) ||
    (parsed as CursorPayload).index < 0 ||
    (parsed as CursorPayload).index >= musicData.segments.length
  ) {
    throw new Error("Cursor does not match the current song revision");
  }
  return parsed as CursorPayload;
}

function envelope(index: number): SegmentEnvelope {
  const segment = musicData.segments[index];
  if (!segment) throw new Error("Segment index is out of range");
  return {
    song_id: musicData.song.id,
    revision: musicData.revision,
    cursor: encodeCursor(index),
    completed: index === musicData.segments.length - 1,
    segment,
    perception_route: musicData.perception_route,
    perception_notice: musicData.perception_notice,
    unknown: musicData.unknown,
  };
}

export function musicCatalog(): Record<string, unknown> {
  return {
    songs: [
      {
        ...musicData.song,
        segment_count: musicData.segments.length,
        perception_route: musicData.perception_route,
        native_audio_content: false,
      },
    ],
    perception_notice: musicData.perception_notice,
  };
}

export function musicStart(songId: string): SegmentEnvelope {
  requireSong(songId);
  return envelope(0);
}

export function musicNext(songId: string, cursor: string): SegmentEnvelope {
  requireSong(songId);
  const current = decodeCursor(cursor);
  const nextIndex = Math.min(current.index + 1, musicData.segments.length - 1);
  return envelope(nextIndex);
}

export function musicSeek(songId: string, target: SeekTarget): SegmentEnvelope {
  requireSong(songId);
  let index = -1;
  if (target.kind === "cursor") {
    index = decodeCursor(target.value).index;
  } else if (target.kind === "section_id") {
    index = musicData.segments.findIndex((segment) => segment.id === target.value);
  } else if (target.kind === "line_id") {
    index = musicData.segments.findIndex((segment) =>
      segment.lyrics.some((line) => line.id === target.value),
    );
  } else {
    index = musicData.segments.findIndex(
      (segment) => target.value >= segment.start_ms && target.value < segment.end_ms,
    );
    if (index < 0 && target.value === musicData.song.duration_ms) {
      index = musicData.segments.length - 1;
    }
  }
  if (index < 0) throw new Error(`Seek target not found: ${target.kind}=${target.value}`);
  return envelope(index);
}

export function formatSegmentText(value: SegmentEnvelope): string {
  const segment = value.segment;
  if (!segment) return `《${musicData.song.title}》已结束。`;
  const lyrics = segment.lyrics.length
    ? segment.lyrics
        .map(
          (line) =>
            `${line.start_ms}-${line.end_ms} ${line.performers.map((item) => item.name).join("、")}: ${line.text}`,
        )
        .join("\n")
    : "（本段无歌词）";
  const observations = segment.music_observations.length
    ? segment.music_observations
        .map((item) => `${item.start_ms}: ${item.description} [${item.certainty}]`)
        .join("\n")
    : "（本段没有独立的人工乐器事件记录）";
  const curves = segment.acoustic_curves
    .map(
      (curve) =>
        `${curve.label}[自动未校]: ${curve.points.map((point) => `${point.time_ms}:${point.value}`).join(",")}`,
    )
    .join("\n");
  return [
    `《${musicData.song.title}》${segment.title} ${segment.start_ms}-${segment.end_ms}ms`,
    musicData.perception_notice,
    "歌词与演唱者：",
    lyrics,
    "人工听音事实：",
    observations,
    "离线测量曲线（全曲 p02-p98 归一化为 0-63）：",
    curves,
    `明确未知：${musicData.unknown.join("、")}`,
  ].join("\n");
}

export function assertToolResponseSize(value: unknown): void {
  const size = Buffer.byteLength(JSON.stringify(value), "utf8");
  if (size > MAX_TOOL_RESPONSE_BYTES) {
    throw new Error(`Tool response exceeds ${MAX_TOOL_RESPONSE_BYTES} bytes`);
  }
}
