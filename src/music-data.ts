import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface Performer {
  id: string;
  name: string;
  role: string;
}

export interface LyricLine {
  id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  performers: Performer[];
  timing_status: { start: string; end: string };
}

export interface MusicObservation {
  id: string;
  start_ms: number;
  end_ms?: number;
  description: string;
  certainty: string;
  source: string;
}

export interface AcousticCurve {
  id: string;
  label: string;
  status: "automatic_unverified";
  scale: string;
  points: Array<{ time_ms: number; value: number }>;
}

export interface MusicSegment {
  index: number;
  id: string;
  title: string;
  start_ms: number;
  end_ms: number;
  lyrics: LyricLine[];
  music_observations: MusicObservation[];
  acoustic_curves: AcousticCurve[];
}

export interface McpMusicData {
  schema_version: string;
  revision: string;
  perception_route: string;
  perception_notice: string;
  song: {
    id: string;
    title: string;
    version: { id: string; display_name: string };
    duration_ms: number;
    credits: Record<string, string[]>;
    performers: Array<{ id: string; display_name: string }>;
    media: { video_url: string | null; audio_url: string | null };
  };
  unknown: string[];
  segments: MusicSegment[];
  limits: {
    segment_count: number;
    max_segments_per_response: number;
    native_audio_content: boolean;
  };
  provenance: Record<string, string>;
}

const dataUrl = new URL("../../data/songs/jieyue/mcp.json", import.meta.url);

function loadMusicData(): McpMusicData {
  const parsed = JSON.parse(readFileSync(fileURLToPath(dataUrl), "utf8")) as McpMusicData;
  if (parsed.song?.id !== "jieyue" || parsed.segments?.length !== 12) {
    throw new Error("Invalid generated MCP music data");
  }
  return parsed;
}

export const musicData = loadMusicData();
