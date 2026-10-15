const EVENT_URL = "../../data/songs/jieyue/source/detailed-listening-annotations.json";
const FEATURE_URL = "../../data/songs/jieyue/experiments/perception/candidate_a_features.json";
const TIMELINE_URL = "../../data/songs/jieyue/timeline.reference.json";
const CURVE_URL = "../../data/songs/jieyue/experiments/mss-curve-poc/outputs/mss.curves.json";
const STORAGE_PREFIX = "jieyue-mss-event-review";
const ARRAY_FIELDS = ["instruments", "instrument_candidates", "actions", "articulation", "timbre"];

const $ = (selector) => document.querySelector(selector);
const elements = {
  audio: $("#audio"), audioFile: $("#audio-file"), loadAudio: $("#load-audio"),
  reviewFile: $("#review-file"), importJson: $("#import-json"), exportJson: $("#export-json"), resetReview: $("#reset-review"),
  fileDot: $("#file-dot"), fileStatus: $("#file-status"), reviewCount: $("#review-count"), progressFill: $("#progress-fill"),
  filter: $("#review-filter"), eventList: $("#event-list"), eventPosition: $("#event-position"), eventSection: $("#event-section"),
  eventStatus: $("#event-status"), eventTitle: $("#event-title"), eventId: $("#event-id"), previous: $("#previous"), next: $("#next"),
  replay: $("#replay"), playPause: $("#play-pause"), loopEvent: $("#loop-event"), scrubber: $("#scrubber"),
  playheadTime: $("#playhead-time"), previewEndTime: $("#preview-end-time"), previewNote: $("#preview-note"),
  startMs: $("#start-ms"), endMs: $("#end-ms"), startFormatted: $("#start-formatted"), endFormatted: $("#end-formatted"),
  eventType: $("#event-type"), certainty: $("#certainty"), instruments: $("#instruments"), instrumentCandidates: $("#instrument-candidates"),
  foreground: $("#foreground"), role: $("#role"), actions: $("#actions"), articulation: $("#articulation"), register: $("#register"),
  motion: $("#motion"), timbre: $("#timbre"), description: $("#description"), descriptionLength: $("#description-length"),
  notes: $("#review-notes"), restoreDraft: $("#restore-draft"), markPending: $("#mark-pending"), markFlagged: $("#mark-flagged"),
  markVerified: $("#mark-verified"), lyricsList: $("#lyrics-list"), featureList: $("#feature-list"), toast: $("#toast"),
  curveChart: $("#curve-chart"), curveValues: $("#curve-values"), guzhengCount: $("#guzheng-count"),
  layerRole: $("#layer-role"), layerBackground: $("#layer-background"), layerForeground: $("#layer-foreground"), layerNote: $("#layer-note"),
};

let sourceData;
let featureData;
let timeline;
let curveData;
let activeIndex = 0;
let reviews = {};
let audioUrl;
let objectVersion = 0;
let toastTimer;

function formatTime(ms) {
  const safe = Math.max(0, Number(ms) || 0);
  const minutes = Math.floor(safe / 60000);
  const seconds = Math.floor((safe % 60000) / 1000);
  const millis = Math.floor(safe % 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function parseList(value) {
  return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
}

function sourceEvent() { return sourceData.events[activeIndex]; }
function sourceSection(id) { return timeline.sections.find((section) => section.id === id); }
function sectionTitle(id) { return sourceSection(id)?.title || id; }
function statusCopy(status) { return ({ pending: "待校对", flagged: "需复核", verified: "已确认" })[status] || "待校对"; }
function isGuzhengRelated(event) {
  return event.instruments?.includes("guzheng") || event.instrument_candidates?.includes("guzheng") || event.actions?.includes("guzheng_exit");
}

function editableFrom(event) {
  return {
    start_ms: event.start_ms,
    end_ms: event.end_ms ?? null,
    type: event.type,
    instruments: [...(event.instruments || [])],
    instrument_candidates: [...(event.instrument_candidates || [])],
    foreground: event.foreground || "",
    actions: [...(event.actions || [])],
    articulation: [...(event.articulation || [])],
    register: event.register || "",
    motion: event.motion || "",
    timbre: [...(event.timbre || [])],
    role: event.role || "",
    description_zh: event.description_zh,
    certainty: event.certainty || "",
  };
}

function reviewFor(event) {
  return reviews[event.id] || { ...editableFrom(event), status: "pending", notes: "" };
}

function ensureReview(event = sourceEvent()) {
  if (!reviews[event.id]) reviews[event.id] = { ...reviewFor(event) };
  return reviews[event.id];
}

function storageKey() {
  return `${STORAGE_PREFIX}:${sourceData.schema_version}:${sourceData.song_id}:${timeline.timeline_timebase.sha256}`;
}

function saveLocal() { localStorage.setItem(storageKey(), JSON.stringify({ version: 1, reviews })); }

function migrateSavedReviews() {
  const bridgeAccent = reviews["detail-event-026"];
  if (!bridgeAccent) return false;
  let changed = false;
  if (JSON.stringify(bridgeAccent.actions) === JSON.stringify(["brief_harmony", "brief_rise"])) {
    bridgeAccent.actions = ["brief_harmony"];
    changed = true;
  }
  if (bridgeAccent.description_zh === "古筝短暂和声并扬起，随后恢复原基底。") {
    bridgeAccent.description_zh = "古筝短暂和声，随后恢复原基底。";
    changed = true;
  }
  if (changed) {
    bridgeAccent.status = "pending";
    delete bridgeAccent.verified_at;
  }
  return changed;
}

function restoreLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || "null");
    if (saved?.version === 1 && saved.reviews && typeof saved.reviews === "object") {
      reviews = saved.reviews;
      if (migrateSavedReviews()) saveLocal();
    }
  } catch { reviews = {}; }
}

function notify(message, isError = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function updateProgress() {
  const total = sourceData.events.length;
  const verified = sourceData.events.filter((event) => reviewFor(event).status === "verified").length;
  elements.reviewCount.textContent = `${verified} / ${total} 已确认`;
  elements.progressFill.style.width = `${(verified / total) * 100}%`;
}

function renderEventList() {
  const filter = elements.filter.value;
  const fragment = document.createDocumentFragment();
  let lastSection;
  let matches = 0;
  sourceData.events.forEach((event, index) => {
    const review = reviewFor(event);
    if (filter === "guzheng" ? !isGuzhengRelated(event) : filter !== "all" && review.status !== filter) return;
    if (event.section_id !== lastSection) {
      const label = document.createElement("p");
      label.className = "section-label";
      label.textContent = sectionTitle(event.section_id);
      fragment.append(label);
      lastSection = event.section_id;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = `event-item${index === activeIndex ? " active" : ""}`;
    const short = review.description_zh || event.type;
    button.innerHTML = `<span class="event-number">${String(index + 1).padStart(2, "0")}</span><span class="event-copy"><span class="event-name"></span><span class="event-time"></span></span><span class="review-mark ${review.status}" aria-label="${statusCopy(review.status)}"></span>`;
    button.querySelector(".event-name").textContent = short;
    button.querySelector(".event-time").textContent = review.end_ms == null ? `${formatTime(review.start_ms)} · 点状` : `${formatTime(review.start_ms)}–${formatTime(review.end_ms)}`;
    button.addEventListener("click", () => selectEvent(index, true));
    fragment.append(button);
    matches += 1;
  });
  elements.eventList.replaceChildren(fragment);
  if (!matches) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "没有符合条件的事件";
    elements.eventList.append(empty);
  }
}

function previewRange() {
  const review = reviewFor(sourceEvent());
  const section = sourceSection(sourceEvent().section_id);
  const songEnd = timeline.timeline_timebase.duration_ms;
  if (review.end_ms != null && review.end_ms > review.start_ms) {
    return { start: review.start_ms, end: review.end_ms, point: false };
  }
  return {
    start: Math.max(section?.start_ms || 0, review.start_ms - 1500),
    end: Math.min(section?.end_ms || songEnd, review.start_ms + 4000),
    point: true,
  };
}

function featureItem(label, value) {
  const item = document.createElement("div");
  item.className = "feature";
  const key = document.createElement("span");
  const val = document.createElement("span");
  key.className = "feature-label";
  val.className = "feature-value";
  key.textContent = label;
  val.textContent = value;
  item.append(key, val);
  return item;
}

function renderFeatures() {
  const segment = featureData.segments.find((item) => item.segment_id === sourceEvent().section_id);
  const features = segment?.perception?.features;
  if (!features) {
    const copy = document.createElement("p");
    copy.className = "no-evidence";
    copy.textContent = "这个段落没有独立的自动测量记录。";
    elements.featureList.replaceChildren(copy);
    return;
  }
  elements.featureList.replaceChildren(
    featureItem("综合响度", `${features.integrated_lufs.toFixed(1)} LUFS`),
    featureItem("动态范围", `${features.loudness_range_lu.toFixed(1)} LU`),
    featureItem("频谱质心中位数", `${Math.round(features.spectral_centroid_hz_median)} Hz`),
    featureItem("频谱变化量", features.spectral_flux_median.toFixed(4)),
    featureItem("前 / 中 / 后响度", features.loudness_profile_lufs.map((value) => value.toFixed(1)).join(" / ")),
    featureItem("人声时间覆盖", `${Math.round(features.vocal_coverage_ratio * 100)}%`),
  );
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function curveAtTime(curve, timeMs) {
  const times = curveData.sampling.sample_times_ms;
  let index = Math.floor(timeMs / curveData.sampling.hop_ms);
  index = Math.max(0, Math.min(times.length - 1, index));
  return { physical: curve.values[index], quantized: curve.quantized[index] };
}

function renderCurves() {
  if (!curveData) return;
  const width = 1000;
  const rowHeight = 54;
  const top = 15;
  const labelWidth = 72;
  const plotWidth = width - labelWidth - 12;
  const height = top + rowHeight * curveData.curves.length + 14;
  const duration = curveData.track.duration_ms;
  const colors = ["#ead79f", "#86c4d9", "#d99c70", "#9ed5b7"];
  const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  const review = reviewFor(sourceEvent());
  const activeEnd = review.end_ms ?? Math.min(duration, review.start_ms + 500);
  const activeX = labelWidth + (review.start_ms / duration) * plotWidth;
  const activeWidth = Math.max(2, ((activeEnd - review.start_ms) / duration) * plotWidth);
  svg.append(svgElement("rect", { x: activeX, y: 0, width: activeWidth, height, fill: "rgba(244,240,231,.12)" }));

  timeline.sections.filter((section) => section.start_ms < duration).forEach((section) => {
    const x = labelWidth + (section.start_ms / duration) * plotWidth;
    svg.append(svgElement("line", { x1: x, x2: x, y1: 0, y2: height, stroke: "rgba(255,255,255,.08)", "stroke-width": 1 }));
  });

  const guzhengEvents = sourceData.events.filter(isGuzhengRelated);
  elements.guzhengCount.textContent = `${guzhengEvents.length} 条古筝相关事件`;
  guzhengEvents.forEach((event) => {
    const x = labelWidth + (event.start_ms / duration) * plotWidth;
    svg.append(svgElement("line", { x1: x, x2: x, y1: 0, y2: 10, stroke: "#ffdc79", "stroke-width": 2 }));
  });

  curveData.curves.forEach((curve, curveIndex) => {
    const yTop = top + curveIndex * rowHeight;
    const baseline = yTop + rowHeight - 9;
    const label = svgElement("text", { x: 8, y: yTop + 23, fill: colors[curveIndex], "font-size": 11, "font-family": "system-ui" });
    label.textContent = curve.label_zh;
    svg.append(label);
    svg.append(svgElement("line", { x1: labelWidth, x2: width - 12, y1: baseline, y2: baseline, stroke: "rgba(255,255,255,.08)", "stroke-width": 1 }));
    let path = "";
    let drawing = false;
    curve.quantized.forEach((value, index) => {
      if (value == null) { drawing = false; return; }
      const timeMs = curveData.sampling.sample_times_ms[index];
      const x = labelWidth + (timeMs / duration) * plotWidth;
      const y = baseline - (value / 63) * (rowHeight - 16);
      path += `${drawing ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
      drawing = true;
    });
    svg.append(svgElement("path", { d: path, fill: "none", stroke: colors[curveIndex], "stroke-width": 1.4, "vector-effect": "non-scaling-stroke" }));
  });

  svg.addEventListener("click", (event) => {
    const rect = svg.getBoundingClientRect();
    const relativeX = Math.max(0, Math.min(1, (event.clientX - rect.left - (labelWidth / width) * rect.width) / ((plotWidth / width) * rect.width)));
    const timeMs = relativeX * duration;
    let nearestIndex = 0;
    let nearestDistance = Infinity;
    sourceData.events.forEach((item, index) => {
      const distance = Math.abs(item.start_ms - timeMs);
      if (distance < nearestDistance) { nearestDistance = distance; nearestIndex = index; }
    });
    selectEvent(nearestIndex, true);
  });
  elements.curveChart.replaceChildren(svg);

  const values = document.createDocumentFragment();
  curveData.curves.forEach((curve) => {
    const value = curveAtTime(curve, review.start_ms);
    const chip = document.createElement("span");
    chip.className = "curve-value";
    const key = document.createElement("b");
    const copy = document.createElement("span");
    key.textContent = curve.label_zh;
    copy.textContent = value.physical == null ? "无有效值" : `${value.physical} ${curve.unit} · q${value.quantized}`;
    chip.append(key, copy);
    values.append(chip);
  });
  elements.curveValues.replaceChildren(values);
}

function instrumentName(id) {
  return curveData?.instrument_vocabulary?.[id] || id;
}

function renderLayer() {
  const layeredEvent = curveData?.events?.find((event) => event.id === sourceEvent().id);
  const layer = layeredEvent?.texture_layer;
  if (!layer) return;
  const background = layer.background_instruments.map(instrumentName);
  const foreground = layer.foreground_instruments.map(instrumentName);
  if (layer.foreground_candidates.length) foreground.push(`${layer.foreground_candidates.map(instrumentName).join(" / ")}（候选）`);
  elements.layerRole.textContent = layer.role;
  elements.layerBackground.textContent = background.length ? background.join(" · ") : layer.role === "background_exit" ? "退出" : "未单列 / 无持续基底";
  elements.layerForeground.textContent = foreground.length ? foreground.join(" · ") : "无独立前景";
  const references = layer.background_event_ids.length ? `沿用 ${layer.background_event_ids.join("、")} 的基底。` : "";
  const additions = layer.background_additions.length ? `本事件向基底加入 ${layer.background_additions.map(instrumentName).join("、")}。` : "";
  elements.layerNote.textContent = `${references}${additions}${foreground.length && background.length ? "前景叠加在持续基底之上，不表示其他乐器退出。" : "没有把未标注的声部退出或进入补写成事实。"}`;
}

function performerNames(line) {
  return line.performers.map((entry) => timeline.performers.find((performer) => performer.id === entry.id)?.display_name || entry.id).join("、");
}

function renderLyrics() {
  const range = previewRange();
  const nearby = timeline.lines.filter((line) => Math.min(range.end + 2500, line.end_ms) - Math.max(range.start - 2500, line.start_ms) > 0);
  if (!nearby.length) {
    const copy = document.createElement("p");
    copy.className = "no-evidence";
    copy.textContent = "试听窗口附近没有歌词。";
    elements.lyricsList.replaceChildren(copy);
    return;
  }
  const fragment = document.createDocumentFragment();
  nearby.forEach((line) => {
    const row = document.createElement("div");
    row.className = "lyric-line";
    const time = document.createElement("span");
    const text = document.createElement("span");
    const performer = document.createElement("span");
    time.className = "lyric-time";
    performer.className = "lyric-performer";
    time.textContent = formatTime(line.start_ms).slice(0, -4);
    text.textContent = line.text;
    performer.textContent = performerNames(line);
    row.append(time, text, performer);
    fragment.append(row);
  });
  elements.lyricsList.replaceChildren(fragment);
}

function setInputValues(review) {
  elements.startMs.value = String(review.start_ms);
  elements.endMs.value = review.end_ms == null ? "" : String(review.end_ms);
  elements.eventType.value = review.type;
  elements.certainty.value = review.certainty || sourceEvent().certainty || "";
  elements.instruments.value = review.instruments.join(", ");
  elements.instrumentCandidates.value = review.instrument_candidates.join(", ");
  elements.foreground.value = review.foreground;
  elements.role.value = review.role;
  elements.actions.value = review.actions.join(", ");
  elements.articulation.value = review.articulation.join(", ");
  elements.register.value = review.register;
  elements.motion.value = review.motion;
  elements.timbre.value = review.timbre.join(", ");
  elements.description.value = review.description_zh;
  elements.notes.value = review.notes || "";
}

function updateTimeDisplay() {
  const review = reviewFor(sourceEvent());
  const range = previewRange();
  elements.startFormatted.textContent = formatTime(review.start_ms);
  elements.endFormatted.textContent = review.end_ms == null ? "点状事件：未设置结束时间" : formatTime(review.end_ms);
  elements.previewEndTime.textContent = formatTime(range.end);
  elements.previewNote.textContent = range.point ? "点状事件：自动从事件前 1.5 秒试听到后 4 秒（受段落边界限制）。" : "连续事件：按校对后的起止时间循环试听。";
  elements.descriptionLength.textContent = `${review.description_zh.length} 字`;
  updateScrubber();
}

function renderActive({ scroll = false } = {}) {
  const event = sourceEvent();
  const review = reviewFor(event);
  elements.eventPosition.textContent = `第 ${activeIndex + 1} / ${sourceData.events.length} 个`;
  elements.eventSection.textContent = sectionTitle(event.section_id);
  elements.eventStatus.textContent = statusCopy(review.status);
  elements.eventStatus.className = `status-label ${review.status}`;
  elements.eventTitle.textContent = `${formatTime(review.start_ms)} · ${review.type}`;
  elements.eventId.textContent = event.id;
  setInputValues(review);
  updateTimeDisplay();
  renderFeatures();
  renderLyrics();
  renderCurves();
  renderLayer();
  renderEventList();
  if (scroll) elements.eventList.querySelector(".event-item.active")?.scrollIntoView({ block: "center" });
}

function selectEvent(index, seek = false) {
  activeIndex = Math.max(0, Math.min(sourceData.events.length - 1, index));
  if (seek && elements.audio.src) elements.audio.currentTime = previewRange().start / 1000;
  renderActive({ scroll: true });
}

function readEditor() {
  const review = ensureReview();
  review.start_ms = Math.max(0, Math.round(Number(elements.startMs.value) || 0));
  const endValue = elements.endMs.value.trim();
  review.end_ms = endValue === "" ? null : Math.max(0, Math.round(Number(endValue) || 0));
  review.type = elements.eventType.value.trim();
  review.certainty = elements.certainty.value.trim();
  review.instruments = parseList(elements.instruments.value);
  review.instrument_candidates = parseList(elements.instrumentCandidates.value);
  review.foreground = elements.foreground.value.trim();
  review.role = elements.role.value.trim();
  review.actions = parseList(elements.actions.value);
  review.articulation = parseList(elements.articulation.value);
  review.register = elements.register.value.trim();
  review.motion = elements.motion.value.trim();
  review.timbre = parseList(elements.timbre.value);
  review.description_zh = elements.description.value.trim();
  review.notes = elements.notes.value.trim();
  return review;
}

function saveEditor() {
  const review = readEditor();
  review.updated_at = new Date().toISOString();
  if (review.status === "verified") {
    review.status = "pending";
    delete review.verified_at;
  }
  saveLocal();
  elements.eventStatus.textContent = statusCopy(review.status);
  elements.eventStatus.className = `status-label ${review.status}`;
  elements.eventTitle.textContent = `${formatTime(review.start_ms)} · ${review.type}`;
  updateTimeDisplay();
  renderLyrics();
  renderCurves();
  renderEventList();
  updateProgress();
}

function validateReview(review) {
  if (!review.type) return "事件类型不能为空";
  if (!review.description_zh) return "事件描述不能为空";
  if (review.end_ms != null && review.end_ms <= review.start_ms) return "结束时间必须晚于开始时间，或留空作为点状事件";
  if (review.start_ms > timeline.timeline_timebase.duration_ms || (review.end_ms ?? 0) > timeline.timeline_timebase.duration_ms) return "时间不能超过母带总时长";
  return null;
}

function setReviewStatus(status, advance = false) {
  const review = readEditor();
  const error = validateReview(review);
  if (error) { notify(error, true); return; }
  review.status = status;
  review.updated_at = new Date().toISOString();
  if (status === "verified") review.verified_at = review.updated_at;
  else delete review.verified_at;
  saveLocal();
  updateProgress();
  renderEventList();
  notify(status === "verified" ? `已确认：${sourceEvent().id}` : status === "flagged" ? `已标记需复核：${sourceEvent().id}` : `已暂存：${sourceEvent().id}`);
  if (advance && activeIndex < sourceData.events.length - 1) selectEvent(activeIndex + 1, true);
  else renderActive();
}

function restoreDraft() {
  const event = sourceEvent();
  const current = reviewFor(event);
  if (JSON.stringify(editableFrom(event)) !== JSON.stringify(Object.fromEntries(Object.keys(editableFrom(event)).map((key) => [key, current[key]]))) && !window.confirm("用最初的听音事件覆盖当前修改？")) return;
  reviews[event.id] = { ...editableFrom(event), status: "pending", notes: "", updated_at: new Date().toISOString() };
  saveLocal();
  updateProgress();
  renderActive();
  notify("已恢复当前事件的原始记录");
}

function nudgeTime(target, delta) {
  const input = target === "start" ? elements.startMs : elements.endMs;
  const fallback = target === "start" ? 0 : Number(elements.startMs.value) + 1000;
  input.value = String(Math.max(0, Math.round(Number(input.value || fallback) + delta)));
  saveEditor();
  if (elements.audio.src) elements.audio.currentTime = previewRange().start / 1000;
}

async function sha256Hex(file) {
  if (!crypto.subtle) return null;
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function loadAudioFile(file) {
  if (!file) return;
  objectVersion += 1;
  const version = objectVersion;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = URL.createObjectURL(file);
  elements.audio.src = audioUrl;
  elements.fileDot.className = "status-dot";
  elements.fileStatus.textContent = `正在校验 ${file.name}…`;
  const hash = await sha256Hex(file).catch(() => null);
  if (version !== objectVersion) return;
  const valid = hash ? hash === timeline.timeline_timebase.sha256 : file.name === timeline.timeline_timebase.asset;
  elements.fileDot.className = `status-dot ${valid ? "valid" : "invalid"}`;
  elements.fileStatus.textContent = valid ? `${file.name} · 已核对为 MSS 实验使用的 MP3 母带` : `${file.name} · 与实验记录的母带不一致`;
  notify(valid ? "母带已载入，音频不会离开这台设备" : "文件指纹不一致；可以试听，但不要据此确认事件", !valid);
  elements.audio.currentTime = previewRange().start / 1000;
}

async function playEvent(fromStart = false) {
  if (!elements.audio.src) { elements.audioFile.click(); return; }
  const range = previewRange();
  const currentMs = elements.audio.currentTime * 1000;
  if (fromStart || currentMs < range.start || currentMs >= range.end) elements.audio.currentTime = range.start / 1000;
  try { await elements.audio.play(); } catch { notify("浏览器未能开始播放，请再点一次播放", true); }
}

function togglePlayback() { if (elements.audio.paused) playEvent(false); else elements.audio.pause(); }

function updateScrubber() {
  if (!sourceData) return;
  const range = previewRange();
  const current = elements.audio.currentTime * 1000;
  const bounded = Math.max(range.start, Math.min(range.end, current || range.start));
  const duration = Math.max(1, range.end - range.start);
  elements.scrubber.value = String(Math.round(((bounded - range.start) / duration) * 1000));
  elements.playheadTime.textContent = formatTime(bounded);
}

function onTimeUpdate() {
  const range = previewRange();
  const current = elements.audio.currentTime * 1000;
  if (!elements.audio.paused && current >= range.end - 35) {
    if (elements.loopEvent.checked) { elements.audio.currentTime = range.start / 1000; elements.audio.play().catch(() => {}); }
    else { elements.audio.pause(); elements.audio.currentTime = range.end / 1000; }
  }
  updateScrubber();
}

function cleanedEvent(source, review) {
  const output = { id: source.id, section_id: source.section_id, start_ms: review.start_ms, type: review.type };
  if (review.end_ms != null) output.end_ms = review.end_ms;
  ARRAY_FIELDS.forEach((field) => { if (review[field]?.length) output[field] = [...review[field]]; });
  ["foreground", "role", "register", "motion"].forEach((field) => { if (review[field]) output[field] = review[field]; });
  output.description_zh = review.description_zh;
  output.certainty = review.certainty || source.certainty;
  output.review = { status: review.status, notes: review.notes || "", updated_at: review.updated_at || null, verified_at: review.verified_at || null };
  output.provenance = { original_source: "detailed-listening-annotations.json", stable_event_id: source.id, final_event: review.status === "verified" ? "human_reviewed" : "draft_needs_listening_review" };
  return output;
}

function exportReview() {
  let verified = 0;
  let flagged = 0;
  const events = sourceData.events.map((event) => {
    const review = reviewFor(event);
    if (review.status === "verified") verified += 1;
    if (review.status === "flagged") flagged += 1;
    return cleanedEvent(event, review);
  });
  const exported = {
    schema_version: "0.1.0",
    song_id: sourceData.song_id,
    title: sourceData.title,
    timebase: { unit: "milliseconds", audio_asset: timeline.timeline_timebase.asset, audio_sha256: timeline.timeline_timebase.sha256, duration_ms: timeline.timeline_timebase.duration_ms },
    perception_kind: "music_semantic_score_events",
    perception_notice: "这些事件向不能直接接收音频的模型提供经人工复核的符号化音乐事实，不表示模型听到了原始音频。",
    curve_reference: {
      mss_version: curveData.mss_version,
      source: "data/songs/jieyue/experiments/mss-curve-poc/outputs/mss.curves.json",
      status: "automatic_unverified",
      interpretation_policy: curveData.interpretation_policy,
    },
    source_annotation_schema_version: sourceData.schema_version,
    source: sourceData.source,
    vocabulary: sourceData.vocabulary,
    review_summary: { exported_at: new Date().toISOString(), verified_events: verified, flagged_events: flagged, pending_events: events.length - verified - flagged, total_events: events.length },
    events,
  };
  const blob = new Blob([`${JSON.stringify(exported, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "jieyue.mss-events.reviewed.json";
  link.click();
  URL.revokeObjectURL(url);
  notify(`已导出：${verified} 条确认，${flagged} 条需复核`);
}

async function importReview(file) {
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    if (imported.song_id !== sourceData.song_id || !Array.isArray(imported.events)) throw new Error("不是《借月》的 MSS 事件校对文件");
    const sources = new Map(sourceData.events.map((event) => [event.id, event]));
    const nextReviews = {};
    imported.events.forEach((event) => {
      const source = sources.get(event.id);
      if (!source || typeof event.description_zh !== "string") return;
      const editable = editableFrom({ ...source, ...event });
      nextReviews[event.id] = {
        ...editable,
        certainty: event.certainty || source.certainty,
        status: ["pending", "flagged", "verified"].includes(event.review?.status) ? event.review.status : "pending",
        notes: event.review?.notes || "",
        updated_at: event.review?.updated_at || new Date().toISOString(),
        verified_at: event.review?.verified_at || undefined,
      };
    });
    if (!Object.keys(nextReviews).length) throw new Error("文件中没有可识别的稳定事件 ID");
    reviews = nextReviews;
    saveLocal();
    updateProgress();
    renderActive();
    notify(`已载入 ${Object.keys(nextReviews).length} 个事件的校对稿`);
  } catch (error) { notify(`载入失败：${error.message}`, true); }
  finally { elements.reviewFile.value = ""; }
}

function resetReview() {
  if (Object.keys(reviews).length && !window.confirm("清除当前浏览器中的全部 MSS 事件修改和确认状态？已导出的 JSON 不受影响。")) return;
  reviews = {};
  localStorage.removeItem(storageKey());
  activeIndex = 0;
  updateProgress();
  renderActive({ scroll: true });
  notify("本地 MSS 事件校对进度已重置");
}

function onKeydown(event) {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
  if (event.code === "Space") { event.preventDefault(); togglePlayback(); }
  else if (event.key.toLowerCase() === "r") { event.preventDefault(); playEvent(true); }
  else if (event.key.toLowerCase() === "j") selectEvent(activeIndex - 1, true);
  else if (event.key.toLowerCase() === "k") selectEvent(activeIndex + 1, true);
  else if (event.key.toLowerCase() === "v") setReviewStatus("verified", true);
}

function bindEvents() {
  elements.loadAudio.addEventListener("click", () => elements.audioFile.click());
  elements.audioFile.addEventListener("change", () => loadAudioFile(elements.audioFile.files[0]));
  elements.importJson.addEventListener("click", () => elements.reviewFile.click());
  elements.reviewFile.addEventListener("change", () => importReview(elements.reviewFile.files[0]));
  elements.exportJson.addEventListener("click", exportReview);
  elements.resetReview.addEventListener("click", resetReview);
  elements.filter.addEventListener("change", renderEventList);
  elements.previous.addEventListener("click", () => selectEvent(activeIndex - 1, true));
  elements.next.addEventListener("click", () => selectEvent(activeIndex + 1, true));
  elements.replay.addEventListener("click", () => playEvent(true));
  elements.playPause.addEventListener("click", togglePlayback);
  elements.scrubber.addEventListener("input", () => {
    if (!elements.audio.src) return;
    const range = previewRange();
    elements.audio.currentTime = (range.start + (Number(elements.scrubber.value) / 1000) * (range.end - range.start)) / 1000;
  });
  document.querySelectorAll(".nudge").forEach((button) => button.addEventListener("click", () => nudgeTime(button.dataset.target, Number(button.dataset.delta))));
  [elements.startMs, elements.endMs, elements.eventType, elements.certainty, elements.instruments, elements.instrumentCandidates, elements.foreground,
    elements.role, elements.actions, elements.articulation, elements.register, elements.motion, elements.timbre, elements.description, elements.notes]
    .forEach((input) => input.addEventListener("input", saveEditor));
  elements.restoreDraft.addEventListener("click", restoreDraft);
  elements.markPending.addEventListener("click", () => setReviewStatus("pending"));
  elements.markFlagged.addEventListener("click", () => setReviewStatus("flagged"));
  elements.markVerified.addEventListener("click", () => setReviewStatus("verified", true));
  elements.audio.addEventListener("play", () => { elements.playPause.textContent = "暂停"; });
  elements.audio.addEventListener("pause", () => { elements.playPause.textContent = "播放"; });
  elements.audio.addEventListener("timeupdate", onTimeUpdate);
  document.addEventListener("keydown", onKeydown);
}

async function init() {
  try {
    const responses = await Promise.all([fetch(EVENT_URL, { cache: "no-store" }), fetch(FEATURE_URL, { cache: "no-store" }), fetch(TIMELINE_URL, { cache: "no-store" }), fetch(CURVE_URL, { cache: "no-store" })]);
    if (responses.some((response) => !response.ok)) throw new Error(`HTTP ${responses.map((response) => response.status).join(" / ")}`);
    [sourceData, featureData, timeline, curveData] = await Promise.all(responses.map((response) => response.json()));
    restoreLocal();
    bindEvents();
    updateProgress();
    renderActive();
  } catch (error) {
    const main = document.createElement("main");
    main.style.cssText = "max-width:720px;margin:80px auto;padding:24px;color:#f4f0e7;font-family:system-ui";
    const heading = document.createElement("h1");
    const guidance = document.createElement("p");
    const details = document.createElement("pre");
    heading.textContent = "无法载入 MSS 听音事件";
    guidance.textContent = "请从仓库根目录启动本地服务器，不要直接双击 HTML 文件。";
    details.textContent = String(error);
    main.append(heading, guidance, details);
    document.body.replaceChildren(main);
  }
}

init();
