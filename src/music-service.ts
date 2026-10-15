import { createHash } from "node:crypto";

import { musicData, type MusicSegment } from "./music-data.js";

const CURSOR_VERSION = musicData.revision;
const CURSOR_TAG = createHash("sha256").update(CURSOR_VERSION, "utf8").digest("base64url").slice(0, 6);
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
}

export interface CurveTransition {
  id: string;
  label: string;
  previous_tail: number[];
  current_head: number[];
}

export interface SegmentTextOptions {
  prediction?: string;
  previousSegment?: MusicSegment | null;
  listenerId?: string;
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
  return `JY1-${CURSOR_TAG}-${index + 1}`;
}

export function decodeCursor(cursor: string): CursorPayload {
  if (cursor.length > 512) throw new Error("Cursor is too long");
  const short = /^JY1-([A-Za-z0-9_-]{6})-(\d{1,3})$/.exec(cursor);
  if (short) {
    const index = Number(short[2]) - 1;
    if (short[1] !== CURSOR_TAG || !Number.isInteger(index) || index < 0 || index >= musicData.segments.length) {
      throw new Error("Cursor does not match the current song revision");
    }
    return { v: CURSOR_VERSION, song: musicData.song.id, index };
  }
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
  };
}

export function musicCatalog(): Record<string, unknown> {
  return {
    songs: [
      {
        ...musicData.song,
        segment_count: musicData.segments.length,
      },
    ],
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

export function segmentTransition(
  previousSegment: MusicSegment | null | undefined,
  currentSegment: MusicSegment | null | undefined,
): CurveTransition[] {
  if (!previousSegment || !currentSegment) return [];
  return currentSegment.acoustic_curves.flatMap((currentCurve) => {
    const previousCurve = previousSegment.acoustic_curves.find(
      (candidate) => candidate.id === currentCurve.id,
    );
    if (!previousCurve) return [];
    return [
      {
        id: currentCurve.id,
        label: currentCurve.label,
        previous_tail: previousCurve.points.slice(-2).map((point) => point.value),
        current_head: currentCurve.points.slice(0, 2).map((point) => point.value),
      },
    ];
  });
}

export function formatSegmentText(
  value: SegmentEnvelope,
  options: SegmentTextOptions = {},
): string {
  const segment = value.segment;
  if (!segment) return `《${musicData.song.title}》已结束。`;

  const formatTime = (timeMs: number): string => {
    const minutes = Math.floor(timeMs / 60_000);
    const seconds = Math.floor((timeMs % 60_000) / 1_000);
    const milliseconds = timeMs % 1_000;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
  };
  const curveNames: Record<string, string> = {
    loudness_rms_dbfs: "响度",
    spectral_centroid_hz: "音色明亮度",
    spectral_flux: "声音变化活跃度",
    positive_energy_change_db: "能量抬升",
  };
  const blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  const sparkline = (values: number[]): string =>
    values
      .map((value) => blocks[Math.max(0, Math.min(7, Math.round((value / 63) * 7)))])
      .join("");
  const melodySparkline = (points: Array<[number, number]>): string => {
    if (!points.length) return "";
    const gaps = points.slice(1).map((point, index) => point[0] - points[index]![0]);
    const orderedGaps = [...gaps].sort((left, right) => left - right);
    const medianGap = orderedGaps[Math.floor(orderedGaps.length / 2)] ?? 0;
    return points
      .map((point, index) => {
        const gap = index > 0 && point[0] - points[index - 1]![0] > Math.max(260, medianGap * 1.8) ? "·" : "";
        const level = Math.max(0, Math.min(7, Math.round(((point[1] + 12) / 24) * 7)));
        return `${gap}${blocks[level]}`;
      })
      .join("");
  };
  const performerLabel = (line: MusicSegment["lyrics"][number]): string => {
    const leads = line.performers.filter((performer) => performer.role === "lead").map((performer) => performer.name);
    const supporting = line.performers.filter((performer) => performer.role !== "lead").map((performer) => performer.name);
    if (leads.length > 1) {
      return `${leads.join("、")}（共同演唱${supporting.length ? `；${supporting.join("、")}和声` : ""}）`;
    }
    if (supporting.length) return `${leads[0] ?? line.performers[0]?.name}（主唱；${supporting.join("、")}和声）`;
    return leads[0] ?? line.performers.map((performer) => performer.name).join("、");
  };

  const lyrics = segment.lyrics.length
    ? segment.lyrics
        .map(
          (line) =>
            `${formatTime(line.start_ms)}–${formatTime(line.end_ms)} ${performerLabel(line)}：${line.text}`,
        )
        .join("\n")
    : "（本段无歌词）";
  const observations = segment.music_observations.length
    ? segment.music_observations
        .map((item) => `${formatTime(item.start_ms)}　${item.description}`)
        .join("\n")
    : "（本段没有额外的乐器进入或退出标记）";
  const curves = segment.acoustic_curves
    .map(
      (curve) =>
        `${(curveNames[curve.id] ?? curve.label).padEnd(8, "　")} ${sparkline(curve.points.map((point) => point.value))}`,
    )
    .join("\n");
  const transition = segmentTransition(options.previousSegment, segment)
    .map(
      (curve) =>
        `${(curveNames[curve.id] ?? curve.label).padEnd(8, "　")} ${sparkline(curve.previous_tail)} │ ${sparkline(curve.current_head)}`,
    )
    .join("\n");
  const melodies = segment.melody_contours
    .map((contour) => {
      const lyric = segment.lyrics.find((line) => line.id === contour.line_id);
      const values = contour.points.map((point) => point[1]);
      const range = values.length ? `　${Math.min(...values)}…${Math.max(...values)} 半音` : "";
      return `${lyric ? formatTime(lyric.start_ms) : contour.line_id} ${lyric?.text ?? contour.line_id}　${melodySparkline(contour.points)}${range}`;
    })
    .join("\n");
  const prediction = options.prediction?.trim();
  const progress = `${segment.index + 1}/${musicData.segments.length}`;
  return [
    ...(prediction ? ["揭晓前的猜测", prediction, "", "—— 揭晓 ——", ""] : []),
    `《${musicData.song.title}》· ${segment.title}　${formatTime(segment.start_ms)}–${formatTime(segment.end_ms)}`,
    `欣赏进度 ${progress}${options.listenerId ? `　已为 ${options.listenerId} 记住这里` : ""}`,
    "",
    "歌词",
    lyrics,
    "",
    "声音事件",
    observations,
    "",
    "音乐运动（全曲共用一把相对尺；从左到右）",
    curves,
    ...(melodies
      ? ["", "旋律走向（每句以自身中位音为中线；低→高，·为间隔）", melodies]
      : []),
    ...(transition
      ? ["", "与上一段的衔接（末尾两点 │ 开头两点）", transition]
      : []),
    "",
    value.completed
      ? "已到达歌曲结尾；可用 music_seek 回听任意片段。"
      : [
          `续听码：${value.cursor}`,
          "继续前，可以先猜下一段会怎样，并把猜测放进 music_next 的 prediction。",
        ].join("\n"),
  ].join("\n");
}

export function assertToolResponseSize(value: unknown): void {
  const size = Buffer.byteLength(JSON.stringify(value), "utf8");
  if (size > MAX_TOOL_RESPONSE_BYTES) {
    throw new Error(`Tool response exceeds ${MAX_TOOL_RESPONSE_BYTES} bytes`);
  }
}
