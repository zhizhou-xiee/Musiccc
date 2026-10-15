const DATA_URL = "../../data/songs/jieyue/experiments/melody-harmony-poc/outputs/candidates.json";
const STORAGE_KEY = "jieyue-melody-review-v01";

const $ = (selector) => document.querySelector(selector);
const el = {
  chooseAudio: $("#choose-audio"), audioFile: $("#audio-file"), audio: $("#audio"), audioDot: $("#audio-dot"), audioStatus: $("#audio-status"),
  importReview: $("#import-review"), reviewFile: $("#review-file"), exportReview: $("#export-review"), reviewProgress: $("#review-progress"), resetReview: $("#reset-review"),
  keyCandidates: $("#key-candidates"), tempoCandidates: $("#tempo-candidates"), harmonySummary: $("#harmony-summary"), relationSummary: $("#relation-summary"),
  filter: $("#filter"), lineList: $("#line-list"), position: $("#position"), section: $("#section"), status: $("#status"), lyric: $("#lyric"), lineMeta: $("#line-meta"),
  previous: $("#previous"), next: $("#next"), playOriginal: $("#play-original"), playContour: $("#play-contour"), playDiagnostic: $("#play-diagnostic"), stop: $("#stop"), loop: $("#loop"), scrubber: $("#scrubber"), playhead: $("#playhead"), lineEnd: $("#line-end"),
  coverage: $("#coverage"), melodyChart: $("#melody-chart"), noteStrip: $("#note-strip"), manualObservation: $("#manual-observation"), relationCopy: $("#relation-copy"), harmonyList: $("#harmony-list"), notes: $("#notes"),
  markPending: $("#mark-pending"), markUnknown: $("#mark-unknown"), markCorrection: $("#mark-correction"), markVerified: $("#mark-verified"), toast: $("#toast"),
};

let data;
let activeIndex = 0;
let reviews = {};
let audioUrl;
let audioContext;
let synthNodes = [];
let toastTimer;

function line() { return data.melody_lines[activeIndex]; }
function reviewFor(id) {
  if (reviews[id]) return reviews[id];
  const source = data?.melody_lines?.find((item) => item.line_id === id)?.manual_observation;
  return source ? { status: source.status || "pending", notes: source.observation || "", source: "project_owner_listener" } : { status: "pending", notes: "" };
}
function analysisStart(item) { return item.analysis_start_ms ?? item.start_ms; }
function analysisEnd(item) { return item.analysis_end_ms ?? item.end_ms; }
function formatTime(ms) {
  const safe = Math.max(0, Number(ms) || 0), minutes = Math.floor(safe / 60000), seconds = Math.floor((safe % 60000) / 1000), millis = Math.floor(safe % 1000);
  return `${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}.${String(millis).padStart(3,"0")}`;
}
function statusLabel(status) { return ({ pending: "待校对", verified: "已确认", needs_correction: "需修正", unknown: "无法判断" })[status] || "待校对"; }
function toast(message) { el.toast.textContent = message; el.toast.classList.add("visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.toast.classList.remove("visible"), 2200); }
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews)); updateProgress(); }
function performers(item) { return item.performers.map((person) => `${person.name}（${person.role}）`).join("、"); }

function renderOverview() {
  const keys = data.analysis.key.candidates.slice(0, 3).map((item) => `${item.key} ${item.score.toFixed(2)}`).join(" · ");
  el.keyCandidates.textContent = keys;
  const tempo = data.analysis.tempo;
  el.tempoCandidates.textContent = `中位拍间隔 ${tempo.median_beat_interval_bpm} BPM · 聚合 ${tempo.aggregate_bpm} BPM`;
  const accepted = data.harmony_windows.filter((item) => item.candidate).length;
  el.harmonySummary.textContent = `${accepted} / ${data.harmony_windows.length} 个超过候选阈值`;
  const strong = data.relations.filter((item) => item.relation === "strong_recurrence_candidate").length;
  el.relationSummary.textContent = `${strong} / ${data.relations.length} 对为强复现候选`;
}

function isRepeatLine(id) { return data.relations.some((relation) => relation.source_line_id === id || relation.target_line_id === id); }
function visible(item) {
  const value = el.filter.value;
  if (value === "all") return true;
  if (value === "repeat") return isRepeatLine(item.line_id);
  return reviewFor(item.line_id).status === value;
}
function renderList() {
  el.lineList.replaceChildren();
  let priorSection = "";
  data.melody_lines.forEach((item, index) => {
    if (!visible(item)) return;
    if (item.section_id !== priorSection) {
      const label = document.createElement("div"); label.className = "section-label"; label.textContent = item.section_title; el.lineList.append(label); priorSection = item.section_id;
    }
    const button = document.createElement("button"); button.type = "button"; button.className = `line-item${index === activeIndex ? " active" : ""}`;
    const number = document.createElement("span"); number.className = "line-number"; number.textContent = String(index + 1).padStart(2,"0");
    const copy = document.createElement("span"); copy.className = "line-copy"; copy.textContent = item.text;
    const mark = document.createElement("span"); mark.className = `mark ${reviewFor(item.line_id).status}`;
    button.append(number, copy, mark); button.title = `${formatTime(item.start_ms)} · ${item.text}`; button.addEventListener("click", () => select(index)); el.lineList.append(button);
  });
}

function renderChart(item) {
  const width = 900, height = 260, pad = { left: 44, right: 18, top: 18, bottom: 30 };
  const values = item.contour_points.map((point) => point.relative_semitones).filter((value) => value !== null);
  const extent = Math.max(4, Math.ceil(Math.max(...values.map(Math.abs), 1)));
  const x = (index) => pad.left + index / Math.max(1, item.contour_points.length - 1) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (extent - value) / (2 * extent) * (height - pad.top - pad.bottom);
  const segments = []; let current = [];
  item.contour_points.forEach((point, index) => { if (point.relative_semitones === null) { if (current.length) segments.push(current); current = []; } else current.push([x(index), y(point.relative_semitones)]); });
  if (current.length) segments.push(current);
  const grid = [-extent, 0, extent].map((value) => `<line x1="${pad.left}" y1="${y(value)}" x2="${width-pad.right}" y2="${y(value)}" stroke="rgba(239,225,186,.12)"/><text x="8" y="${y(value)+4}" fill="#9ba7aa" font-size="10">${value > 0 ? "+" : ""}${value}st</text>`).join("");
  const paths = segments.map((points) => `<polyline points="${points.map((point) => point.join(",")).join(" ")}" fill="none" stroke="#e8d398" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`).join("");
  const dots = item.contour_points.map((point,index) => point.relative_semitones === null ? "" : `<circle cx="${x(index)}" cy="${y(point.relative_semitones)}" r="4" fill="#8fc3d5"><title>${formatTime(point.time_ms)} · ${point.note} · ${point.relative_semitones >= 0 ? "+" : ""}${point.relative_semitones}st · p=${point.confidence}</title></circle>`).join("");
  el.melodyChart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">${grid}${paths}${dots}<text x="${pad.left}" y="${height-8}" fill="#9ba7aa" font-size="10">${formatTime(item.start_ms)}</text><text x="${width-pad.right}" y="${height-8}" fill="#9ba7aa" font-size="10" text-anchor="end">${formatTime(item.end_ms)}</text></svg>`;
  el.noteStrip.style.gridTemplateColumns = `repeat(${item.contour_points.length}, minmax(0,1fr))`;
  el.noteStrip.replaceChildren(...item.contour_points.map((point) => { const chip = document.createElement("span"); chip.className = "note-chip"; chip.textContent = point.note || "—"; chip.title = point.note ? `${formatTime(point.time_ms)} · MIDI ${point.midi}` : `${formatTime(point.time_ms)} · 空白`; return chip; }));
}

function relationFor(id) { return data.relations.find((item) => item.source_line_id === id || item.target_line_id === id); }
function renderRelation(item) {
  const relation = relationFor(item.line_id);
  if (!relation) { el.relationCopy.textContent = "本句暂未建立重复关系。"; return; }
  const otherId = relation.source_line_id === item.line_id ? relation.target_line_id : relation.source_line_id;
  const other = data.melody_lines.find((candidate) => candidate.line_id === otherId);
  if (!relation.relative_contour_correlation) { el.relationCopy.textContent = `与 ${otherId}「${other?.text || ""}」配对，但有效音高不足，关系保持 unknown。`; return; }
  const listener = relation.manual_observation ? ` 人工抽听：${relation.manual_observation.observation}` : "";
  el.relationCopy.textContent = `与 ${otherId}「${other?.text || ""}」配对：相对轮廓相关 ${relation.relative_contour_correlation}，中位音高差 ${relation.median_pitch_shift_semitones > 0 ? "+" : ""}${relation.median_pitch_shift_semitones} 半音。标签：${relation.relation}（自动未校对）。${listener}`;
}

function renderHarmony(item) {
  const padding = 1800;
  const windows = data.harmony_windows.filter((window) => window.end_ms >= item.start_ms - padding && window.start_ms <= item.end_ms + padding);
  el.harmonyList.replaceChildren();
  if (!windows.length) { const empty = document.createElement("p"); empty.className = "caveat"; empty.textContent = "附近没有可用的和弦窗口。"; el.harmonyList.append(empty); return; }
  windows.forEach((window) => {
    const card = document.createElement("div"); card.className = `harmony-window${window.candidate ? "" : " unknown"}`;
    const time = document.createElement("span"); time.textContent = `${formatTime(window.start_ms)}–${formatTime(window.end_ms)}`;
    const value = document.createElement("strong"); value.textContent = window.candidate ? `${window.candidate} · 次选 ${window.alternate}` : `留空 · 次选 ${window.alternate}`;
    const margin = document.createElement("span"); margin.textContent = `模板差距 ${window.margin.toFixed(3)}`; card.append(time,value,margin); el.harmonyList.append(card);
  });
}

function renderActive() {
  const item = line(), review = reviewFor(item.line_id);
  el.position.textContent = `第 ${activeIndex + 1} / ${data.melody_lines.length} 句`; el.section.textContent = item.section_title; el.lyric.textContent = item.text;
  el.status.className = `status ${review.status}`; el.status.textContent = statusLabel(review.status);
  const extended = analysisEnd(item) !== item.end_ms ? ` · 分析尾部延至 ${formatTime(analysisEnd(item))}` : "";
  el.lineMeta.textContent = `${formatTime(item.start_ms)}–${formatTime(item.end_ms)}${extended} · ${performers(item)} · ${item.line_id}`;
  el.playhead.textContent = formatTime(analysisStart(item)); el.lineEnd.textContent = formatTime(analysisEnd(item)); el.scrubber.value = 0;
  const polyphonic = item.representation_status === "unsupported_polyphonic_unresolved";
  el.coverage.textContent = polyphonic ? `${item.lead_voice_count} 位主唱 · 单线旋律不适用 · 仅主导音高诊断` : `有效覆盖 ${(item.voiced_coverage * 100).toFixed(1)}% · ${item.candidate_range.lowest_note || "?"}–${item.candidate_range.highest_note || "?"}`;
  el.playContour.disabled = polyphonic; el.playContour.title = polyphonic ? "多人主唱不能安全压成一条连续旋律" : "连续播放单旋律候选";
  if (item.manual_observation) { el.manualObservation.hidden = false; el.manualObservation.textContent = `人工抽听：${item.manual_observation.observation}${item.manual_observation.representation_note ? ` ${item.manual_observation.representation_note}` : ""}`; } else { el.manualObservation.hidden = true; el.manualObservation.textContent = ""; }
  el.notes.value = review.notes || ""; renderChart(item); renderRelation(item); renderHarmony(item); renderList();
}
function select(index) { stopAll(); activeIndex = Math.max(0, Math.min(data.melody_lines.length - 1, index)); renderActive(); document.querySelector(".line-item.active")?.scrollIntoView({ block: "nearest" }); }
function updateProgress() { const done = data.melody_lines.filter((item) => reviewFor(item.line_id).status !== "pending").length; el.reviewProgress.textContent = `${done} / ${data.melody_lines.length} 已处理`; }

function stopSynth() { synthNodes.forEach((node) => { try { node.stop(); } catch {} }); synthNodes = []; }
function stopAll() { el.audio.pause(); stopSynth(); el.playOriginal.textContent = "播放母带原句"; }
async function playOriginal() {
  if (!audioUrl) { toast("先选择本机母带 WAV 或 MP3"); return; }
  stopSynth(); const item = line(); el.audio.currentTime = analysisStart(item) / 1000; await el.audio.play(); el.playOriginal.textContent = "暂停";
}
function schedulePointTone(point, start, duration, destination) {
  const oscillator = audioContext.createOscillator(), gain = audioContext.createGain(); oscillator.type = "sine"; oscillator.frequency.value = 440 * 2 ** ((point.midi - 69) / 12);
  gain.gain.setValueAtTime(0.0001, start); gain.gain.exponentialRampToValueAtTime(.055, start + .015); gain.gain.setValueAtTime(.055, start + Math.max(.02,duration-.025)); gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  oscillator.connect(gain).connect(destination); oscillator.start(start); oscillator.stop(start + duration + .02); synthNodes.push(oscillator);
}
async function playDiagnostic() {
  stopAll(); audioContext ||= new AudioContext(); await audioContext.resume(); const item = line(), points = item.contour_points, now = audioContext.currentTime + .06;
  points.forEach((point, index) => {
    if (point.midi === null) return;
    const next = points[index + 1], duration = Math.max(.06, ((next?.time_ms || analysisEnd(item)) - point.time_ms) / 1000 * .72), start = now + (point.time_ms - analysisStart(item)) / 1000;
    schedulePointTone(point, start, duration, audioContext.destination);
  });
}
async function playContour() {
  const item = line(); if (item.representation_status === "unsupported_polyphonic_unresolved") { toast("这句有多位主唱，不能安全压成一条旋律；请用诊断点音或听母带"); return; }
  stopAll(); audioContext ||= new AudioContext(); await audioContext.resume(); const points = item.contour_points, now = audioContext.currentTime + .06;
  const spacing = points.length > 1 ? (points[1].time_ms - points[0].time_ms) / 1000 : .1; let index = 0;
  while (index < points.length) {
    while (index < points.length && points[index].midi === null) index += 1; if (index >= points.length) break;
    const group = []; while (index < points.length && points[index].midi !== null) { group.push(points[index]); index += 1; }
    const start = now + (group[0].time_ms - analysisStart(item)) / 1000, end = now + (group[group.length-1].time_ms - analysisStart(item)) / 1000 + spacing * .72;
    const carrier = audioContext.createOscillator(), overtone = audioContext.createOscillator(), carrierGain = audioContext.createGain(), overtoneGain = audioContext.createGain(), filter = audioContext.createBiquadFilter();
    carrier.type = "triangle"; overtone.type = "sine"; filter.type = "lowpass"; filter.frequency.value = 1250; carrierGain.gain.value = .045; overtoneGain.gain.value = .012;
    group.forEach((point, pointIndex) => { const at = now + (point.time_ms - analysisStart(item)) / 1000, frequency = 440 * 2 ** ((point.midi - 69) / 12); if (pointIndex === 0) { carrier.frequency.setValueAtTime(frequency, at); overtone.frequency.setValueAtTime(frequency*2, at); } else { carrier.frequency.linearRampToValueAtTime(frequency, at); overtone.frequency.linearRampToValueAtTime(frequency*2, at); } });
    const envelope = audioContext.createGain(); envelope.gain.setValueAtTime(.0001,start); envelope.gain.exponentialRampToValueAtTime(1,start+.035); envelope.gain.setValueAtTime(1,Math.max(start+.04,end-.05)); envelope.gain.exponentialRampToValueAtTime(.0001,end);
    carrier.connect(carrierGain).connect(filter); overtone.connect(overtoneGain).connect(filter); filter.connect(envelope).connect(audioContext.destination); carrier.start(start); overtone.start(start); carrier.stop(end+.02); overtone.stop(end+.02); synthNodes.push(carrier,overtone);
  }
}
function setReview(status, advance = false) { const item = line(); reviews[item.line_id] = { status, notes: el.notes.value.trim(), reviewed_at: new Date().toISOString() }; save(); if (advance && activeIndex < data.melody_lines.length - 1) select(activeIndex + 1); else renderActive(); }

el.chooseAudio.addEventListener("click", () => el.audioFile.click());
el.audioFile.addEventListener("change", () => { const file = el.audioFile.files?.[0]; if (!file) return; if (audioUrl) URL.revokeObjectURL(audioUrl); audioUrl = URL.createObjectURL(file); el.audio.src = audioUrl; el.audioDot.classList.add("ready"); el.audioStatus.textContent = `${file.name} · 仅本机读取`; toast("母带已载入"); });
el.playOriginal.addEventListener("click", () => el.audio.paused ? playOriginal() : el.audio.pause()); el.playContour.addEventListener("click", playContour); el.playDiagnostic.addEventListener("click", playDiagnostic); el.stop.addEventListener("click", stopAll);
el.audio.addEventListener("pause", () => { el.playOriginal.textContent = "播放母带原句"; });
el.audio.addEventListener("timeupdate", () => { const item = line(), currentMs = el.audio.currentTime * 1000; if (currentMs >= analysisEnd(item)) { if (el.loop.checked) { el.audio.currentTime = analysisStart(item) / 1000; el.audio.play(); } else el.audio.pause(); } const ratio = (currentMs - analysisStart(item)) / Math.max(1,analysisEnd(item)-analysisStart(item)); el.scrubber.value = Math.max(0,Math.min(1000,ratio*1000)); el.playhead.textContent = formatTime(Math.max(analysisStart(item),currentMs)); });
el.scrubber.addEventListener("input", () => { const item = line(); el.audio.currentTime = (analysisStart(item) + Number(el.scrubber.value)/1000*(analysisEnd(item)-analysisStart(item)))/1000; });
el.previous.addEventListener("click", () => select(activeIndex - 1)); el.next.addEventListener("click", () => select(activeIndex + 1)); el.filter.addEventListener("change", renderList);
el.notes.addEventListener("input", () => { const item = line(), old = reviewFor(item.line_id); reviews[item.line_id] = { ...old, notes: el.notes.value }; save(); });
el.markPending.addEventListener("click", () => setReview("pending")); el.markUnknown.addEventListener("click", () => setReview("unknown")); el.markCorrection.addEventListener("click", () => setReview("needs_correction")); el.markVerified.addEventListener("click", () => setReview("verified", true));
el.resetReview.addEventListener("click", () => { if (!confirm("清除当前浏览器里的全部旋律校对进度？候选源文件不会改变。")) return; reviews = {}; save(); renderActive(); });
el.exportReview.addEventListener("click", () => { const payload = { schema_version: "melody-harmony-review/0.1", song_id: data.song_id, candidate_schema_version: data.schema_version, exported_at: new Date().toISOString(), source_audio_uploaded: false, reviews }; const blob = new Blob([JSON.stringify(payload,null,2)+"\n"],{type:"application/json"}); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href=url; anchor.download="jieyue.melody-harmony.reviewed.json"; anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); });
el.importReview.addEventListener("click", () => el.reviewFile.click()); el.reviewFile.addEventListener("change", async () => { const file=el.reviewFile.files?.[0]; if (!file) return; try { const incoming=JSON.parse(await file.text()); if (incoming.song_id!==data.song_id || !incoming.reviews) throw new Error("不是《借月》旋律校对稿"); reviews=incoming.reviews; save(); renderActive(); toast("校对稿已载入"); } catch (error) { toast(error.message); } });
document.addEventListener("keydown", (event) => { if (["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)) return; if (event.key === "ArrowLeft") select(activeIndex-1); if (event.key === "ArrowRight") select(activeIndex+1); if (event.key === " ") { event.preventDefault(); el.audio.paused ? playOriginal() : el.audio.pause(); } });

async function init() {
  const response = await fetch(DATA_URL); if (!response.ok) throw new Error(`候选数据载入失败：${response.status}`); data = await response.json();
  try { reviews = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch { reviews = {}; }
  renderOverview(); updateProgress(); renderActive();
}
init().catch((error) => { el.lyric.textContent = error.message; console.error(error); });
