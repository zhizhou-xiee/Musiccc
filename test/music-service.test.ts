import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeCursor,
  formatSegmentText,
  musicNext,
  musicSeek,
  musicStart,
  segmentTransition,
} from "../src/music-service.js";

test("client cursor is deterministic and stateless", () => {
  const startA = musicStart("jieyue");
  const startB = musicStart("jieyue");
  assert.equal(startA.cursor, startB.cursor);
  assert.equal(startA.segment?.id, "a_cappella");

  const nextA = musicNext("jieyue", startA.cursor);
  const repeated = musicNext("jieyue", startA.cursor);
  assert.equal(nextA.segment?.id, "intro");
  assert.deepEqual(nextA, repeated);
  assert.equal(decodeCursor(startB.cursor).index, 0);
});

test("seek supports sections, lyric lines, time and replay cursors", () => {
  assert.equal(musicSeek("jieyue", { kind: "section_id", value: "bridge" }).segment?.id, "bridge");
  assert.equal(musicSeek("jieyue", { kind: "line_id", value: "line-005" }).segment?.id, "verse_1");
  assert.equal(musicSeek("jieyue", { kind: "time_ms", value: 119_138 }).segment?.id, "interlude");
  const outro = musicSeek("jieyue", { kind: "section_id", value: "outro" });
  assert.deepEqual(musicSeek("jieyue", { kind: "cursor", value: outro.cursor }), outro);
});

test("reviewed handoff and layered outro facts are present", () => {
  const interlude = musicSeek("jieyue", { kind: "time_ms", value: 119_138 }).segment;
  assert.match(interlude?.music_observations.map((item) => item.description).join(" ") ?? "", /横笛退出/);
  assert.match(interlude?.music_observations.map((item) => item.description).join(" ") ?? "", /古筝或琵琶/);
  const outro = musicSeek("jieyue", { kind: "time_ms", value: 242_489 }).segment;
  assert.match(outro?.music_observations.map((item) => item.description).join(" ") ?? "", /吉他衔接古筝/);
});

test("project-owner timing correction assigns 直至 to line 013", () => {
  const verse = musicSeek("jieyue", { kind: "line_id", value: "line-013" }).segment;
  const previous = verse?.lyrics.find((line) => line.id === "line-012");
  const corrected = verse?.lyrics.find((line) => line.id === "line-013");
  assert.equal(previous?.end_ms, 68_651);
  assert.equal(previous?.timing_status.end, "verified");
  assert.equal(corrected?.start_ms, 68_651);
  assert.equal(corrected?.timing_status.start, "verified");
});

test("project-owner timing correction assigns 也 to line 029", () => {
  const chorus = musicSeek("jieyue", { kind: "line_id", value: "line-029" }).segment;
  const previous = chorus?.lyrics.find((line) => line.id === "line-028");
  const corrected = chorus?.lyrics.find((line) => line.id === "line-029");
  assert.equal(previous?.end_ms, 107_154);
  assert.equal(previous?.timing_status.end, "verified");
  assert.equal(corrected?.start_ms, 107_154);
  assert.equal(corrected?.timing_status.start, "verified");
});

test("invalid or stale cursors are rejected", () => {
  assert.throws(() => decodeCursor("not-a-cursor"), /Invalid cursor|current song revision/);
  const stale = Buffer.from(JSON.stringify({ v: "old", song: "jieyue", index: 0 })).toString("base64url");
  assert.throws(() => decodeCursor(stale), /current song revision/);
});

test("listener text is a compact score rather than an engineering dump", () => {
  const intro = musicSeek("jieyue", { kind: "section_id", value: "intro" });
  const text = formatSegmentText(intro);
  assert.match(text, /《借月》· 前奏/);
  assert.match(text, /声音事件/);
  assert.match(text, /音乐运动/);
  assert.match(text, /响度.*[▁▂▃▄▅▆▇█]/);
  assert.match(text, new RegExp(intro.cursor));
  assert.doesNotMatch(text, /confirmed_by_listener|p02-p98|明确未知|自动未校/);
});

test("prediction is committed before reveal and transition preserves the segment seam", () => {
  const previous = musicStart("jieyue");
  const next = musicNext("jieyue", previous.cursor);
  const prediction = "我猜伴奏会从稀疏处慢慢进入。";
  const text = formatSegmentText(next, {
    prediction,
    previousSegment: previous.segment,
  });
  assert.ok(text.indexOf(prediction) < text.indexOf("—— 揭晓 ——"));
  assert.ok(text.indexOf("—— 揭晓 ——") < text.indexOf("《借月》· 前奏"));
  assert.match(text, /与上一段的衔接/);
  assert.match(text, /│/);

  const transition = segmentTransition(previous.segment, next.segment);
  assert.equal(transition.length, 4);
  assert.deepEqual(transition[0]?.previous_tail, [41, 0]);
  assert.deepEqual(transition[0]?.current_head, [31, 42]);
});
