const TIMELINE_URL = "../../data/songs/jieyue/timeline.draft.json";
const STORAGE_PREFIX = "jieyue-timeline-review";
const PLAYBACK_PADDING_MS = 450;
const MIN_LINE_MS = 50;

const $ = (selector) => document.querySelector(selector);
const elements = {
  audio: $("#audio"),
  audioFile: $("#audio-file"),
  loadAudio: $("#load-audio"),
  exportJson: $("#export-json"),
  resetReview: $("#reset-review"),
  fileDot: $("#file-dot"),
  fileStatus: $("#file-status"),
  reviewCount: $("#review-count"),
  progressFill: $("#progress-fill"),
  search: $("#search-lines"),
  filter: $("#review-filter"),
  lineList: $("#line-list"),
  linePosition: $("#line-position"),
  sectionName: $("#section-name"),
  performerName: $("#performer-name"),
  previousLine: $("#previous-line"),
  currentLine: $("#current-line"),
  nextLine: $("#next-line"),
  waveform: $("#waveform"),
  windowStart: $("#window-start"),
  windowEnd: $("#window-end"),
  playheadTime: $("#playhead-time"),
  scrubber: $("#scrubber"),
  previous: $("#previous"),
  next: $("#next"),
  replay: $("#replay"),
  playPause: $("#play-pause"),
  startMs: $("#start-ms"),
  endMs: $("#end-ms"),
  startDisplay: $("#start-display"),
  endDisplay: $("#end-display"),
  notes: $("#review-notes"),
  markFlagged: $("#mark-flagged"),
  markVerified: $("#mark-verified"),
  evidence: $("#alignment-evidence"),
  toast: $("#toast"),
};

let timeline;
let activeIndex = 0;
let audioUrl;
let audioBuffer;
let lineStopTimer;
let toastTimer;
let objectVersion = 0;
let localReviews = {};

function formatTime(ms) {
  const safe = Math.max(0, Number(ms) || 0);
  const minutes = Math.floor(safe / 60000);
  const seconds = Math.floor((safe % 60000) / 1000);
  const millis = Math.floor(safe % 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function activeLine() {
  return timeline.lines[activeIndex];
}

function reviewFor(line) {
  return localReviews[line.id] || { status: "pending", notes: "" };
}

function storageKey() {
  return `${STORAGE_PREFIX}:${timeline.song_id}:${timeline.timeline_timebase.sha256}`;
}

function saveLocal() {
  localStorage.setItem(storageKey(), JSON.stringify({ version: 1, reviews: localReviews }));
}

function restoreLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || "null");
    if (saved?.version === 1 && saved.reviews && typeof saved.reviews === "object") {
      localReviews = saved.reviews;
    }
  } catch {
    localReviews = {};
  }
}

function getTimes(line) {
  const review = reviewFor(line);
  return {
    start: Number.isFinite(review.start_ms) ? review.start_ms : line.start_ms,
    end: Number.isFinite(review.end_ms) ? review.end_ms : line.end_ms,
  };
}

function performerText(line) {
  const lookup = new Map(timeline.performers.map((person) => [person.id, person.display_name]));
  return line.performers.map((person) => lookup.get(person.id) || person.id).join("、");
}

function sectionText(line) {
  return timeline.sections.find((section) => section.id === line.section_id)?.title || line.section_id;
}

function notify(message, isError = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2600);
}

function updateProgress() {
  const verified = timeline.lines.filter((line) => reviewFor(line).status === "verified").length;
  elements.reviewCount.textContent = `${verified} / ${timeline.lines.length} 已确认`;
  elements.progressFill.style.width = `${(verified / timeline.lines.length) * 100}%`;
}

function renderLineList() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const filter = elements.filter.value;
  const fragment = document.createDocumentFragment();
  let lastSection;
  let matches = 0;

  timeline.lines.forEach((line, index) => {
    const review = reviewFor(line);
    const singer = performerText(line);
    const textMatch = `${line.text} ${singer}`.toLocaleLowerCase().includes(query);
    const filterMatch = filter === "all"
      || (filter === "pending" && review.status === "pending")
      || (filter === "flagged" && review.status === "flagged")
      || (filter === "verified" && review.status === "verified");
    if (!textMatch || !filterMatch) return;

    if (line.section_id !== lastSection) {
      const label = document.createElement("div");
      label.className = "section-label";
      label.textContent = sectionText(line);
      fragment.append(label);
      lastSection = line.section_id;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = `line-item${index === activeIndex ? " active" : ""}`;
    button.dataset.index = String(index);
    button.innerHTML = `
      <span class="line-number">${String(index + 1).padStart(2, "0")}</span>
      <span class="line-copy"><span class="line-text"></span><span class="line-singer"></span></span>
      <span class="review-mark ${review.status}" aria-label="${review.status}"></span>`;
    button.querySelector(".line-text").textContent = line.text;
    button.querySelector(".line-singer").textContent = singer;
    button.addEventListener("click", () => selectLine(index, true));
    fragment.append(button);
    matches += 1;
  });

  elements.lineList.replaceChildren(fragment);
  if (!matches) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "没有符合条件的歌词";
    elements.lineList.append(empty);
  }
}

function evidenceItem(label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value;
  wrapper.append(term, description);
  return wrapper;
}

function renderEvidence(line) {
  const data = line.alignment;
  elements.evidence.replaceChildren(
    evidenceItem("候选方法", data.method),
    evidenceItem("置信度", String(data.confidence ?? "—")),
    evidenceItem("覆盖率", String(data.coverage ?? "—")),
    evidenceItem("ASR 概率", String(data.asr_probability ?? "—")),
    evidenceItem("匹配音节", `${data.matched_syllables ?? "—"} / ${data.expected_syllables ?? "—"}`),
    evidenceItem("自动标记", data.review_flags?.join(" · ") || "无"),
  );
}

function renderActiveLine({ scroll = false } = {}) {
  const line = activeLine();
  const review = reviewFor(line);
  const { start, end } = getTimes(line);
  elements.linePosition.textContent = `第 ${activeIndex + 1} / ${timeline.lines.length} 句`;
  elements.sectionName.textContent = sectionText(line);
  elements.performerName.textContent = performerText(line);
  elements.previousLine.textContent = timeline.lines[activeIndex - 1]?.text || "";
  elements.currentLine.textContent = line.text;
  elements.nextLine.textContent = timeline.lines[activeIndex + 1]?.text || "";
  elements.startMs.value = String(start);
  elements.endMs.value = String(end);
  elements.startDisplay.value = formatTime(start);
  elements.endDisplay.value = formatTime(end);
  elements.notes.value = review.notes || "";
  elements.markFlagged.textContent = review.status === "flagged" ? "已标记需复核" : "标记需复核";
  elements.markVerified.textContent = review.status === "verified" ? "已确认 · 到下一句" : "确认并到下一句";
  renderEvidence(line);
  renderLineList();
  drawWaveform();

  if (scroll) {
    elements.lineList.querySelector(".line-item.active")?.scrollIntoView({ block: "center" });
  }
}

function selectLine(index, seek = false) {
  activeIndex = Math.max(0, Math.min(timeline.lines.length - 1, index));
  stopAtLineEnd();
  if (seek && elements.audio.src) {
    elements.audio.currentTime = Math.max(0, (getTimes(activeLine()).start - PLAYBACK_PADDING_MS) / 1000);
  }
  renderActiveLine({ scroll: true });
}

function ensureReview(line) {
  if (!localReviews[line.id]) localReviews[line.id] = { status: "pending", notes: "" };
  return localReviews[line.id];
}

function validateTimes(line, start, end) {
  const duration = timeline.timeline_timebase.duration_ms;
  const safeStart = Math.max(0, Math.min(Math.round(start), duration - MIN_LINE_MS));
  const safeEnd = Math.max(safeStart + MIN_LINE_MS, Math.min(Math.round(end), duration));
  return { start: safeStart, end: safeEnd };
}

function setTimes(start, end) {
  const line = activeLine();
  const valid = validateTimes(line, start, end);
  const review = ensureReview(line);
  review.start_ms = valid.start;
  review.end_ms = valid.end;
  review.updated_at = new Date().toISOString();
  if (review.status === "verified") {
    review.status = "pending";
    delete review.verified_at;
  }
  saveLocal();
  renderActiveLine();
}

function nudge(boundary, delta) {
  const { start, end } = getTimes(activeLine());
  if (boundary === "start") setTimes(start + delta, end);
  else setTimes(start, end + delta);
}

function setReviewStatus(status, advance = false) {
  const line = activeLine();
  const review = ensureReview(line);
  const { start, end } = getTimes(line);
  review.status = status;
  review.start_ms = start;
  review.end_ms = end;
  review.notes = elements.notes.value.trim();
  review.updated_at = new Date().toISOString();
  if (status === "verified") review.verified_at = review.updated_at;
  else delete review.verified_at;
  saveLocal();
  updateProgress();
  renderLineList();
  notify(status === "verified" ? `已确认 ${line.id}` : `已标记 ${line.id} 需复核`);
  if (advance && activeIndex < timeline.lines.length - 1) selectLine(activeIndex + 1, true);
  else renderActiveLine();
}

function saveNotes() {
  const review = ensureReview(activeLine());
  review.notes = elements.notes.value.trim();
  review.updated_at = new Date().toISOString();
  saveLocal();
}

function stopAtLineEnd() {
  clearTimeout(lineStopTimer);
  lineStopTimer = undefined;
}

async function replayLine() {
  if (!elements.audio.src) {
    elements.audioFile.click();
    return;
  }
  const { start, end } = getTimes(activeLine());
  const playbackStart = Math.max(0, start - PLAYBACK_PADDING_MS);
  const playbackEnd = Math.min(timeline.timeline_timebase.duration_ms, end + PLAYBACK_PADDING_MS);
  stopAtLineEnd();
  elements.audio.currentTime = playbackStart / 1000;
  try {
    await elements.audio.play();
    const duration = Math.max(100, playbackEnd - playbackStart);
    lineStopTimer = setTimeout(() => elements.audio.pause(), duration + 80);
  } catch {
    notify("浏览器未能开始播放，请再点一次播放", true);
  }
}

async function togglePlayback() {
  if (!elements.audio.src) {
    elements.audioFile.click();
    return;
  }
  stopAtLineEnd();
  if (elements.audio.paused) {
    try {
      await elements.audio.play();
    } catch {
      notify("浏览器未能开始播放，请再点一次播放", true);
    }
  }
  else elements.audio.pause();
}

async function sha256Hex(file) {
  if (!crypto.subtle) return null;
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function decodeWaveform(file) {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    audioBuffer = await context.decodeAudioData(await file.arrayBuffer());
    await context.close();
    drawWaveform();
  } catch {
    audioBuffer = undefined;
    drawWaveform();
    notify("母带可播放，但浏览器未能解码波形", true);
  }
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
  audioBuffer = undefined;
  drawWaveform();

  const [hash] = await Promise.all([
    sha256Hex(file).catch(() => null),
    decodeWaveform(file),
  ]);
  if (version !== objectVersion) return;
  const expected = timeline.timeline_timebase.sha256;
  const valid = hash ? hash === expected : file.name === timeline.timeline_timebase.asset;
  elements.fileDot.className = `status-dot ${valid ? "valid" : "invalid"}`;
  elements.fileStatus.textContent = valid
    ? `${file.name} · 已核对为时间轴母带`
    : `${file.name} · 与时间轴记录的母带不一致`;
  if (!valid) notify("文件指纹不一致；可以试听，但不要据此确认时间轴", true);
  else notify("母带已载入，音频不会离开这台设备");
  selectLine(activeIndex, true);
}

function drawWaveform() {
  const canvas = elements.waveform;
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const { start, end } = timeline ? getTimes(activeLine()) : { start: 0, end: 1000 };
  const pad = Math.max(1800, (end - start) * 0.35);
  const windowStart = Math.max(0, start - pad);
  const windowEnd = Math.min(timeline?.timeline_timebase.duration_ms || end + pad, end + pad);
  elements.windowStart.textContent = formatTime(windowStart);
  elements.windowEnd.textContent = formatTime(windowEnd);

  context.clearRect(0, 0, width, height);
  context.fillStyle = "#0a0c10";
  context.fillRect(0, 0, width, height);

  const xFor = (ms) => ((ms - windowStart) / (windowEnd - windowStart)) * width;
  const startX = xFor(start);
  const endX = xFor(end);
  context.fillStyle = "rgba(242, 219, 159, 0.09)";
  context.fillRect(startX, 0, Math.max(1, endX - startX), height);

  if (audioBuffer) {
    const channel = audioBuffer.getChannelData(0);
    const sampleStart = Math.max(0, Math.floor((windowStart / 1000) * audioBuffer.sampleRate));
    const sampleEnd = Math.min(channel.length, Math.ceil((windowEnd / 1000) * audioBuffer.sampleRate));
    const samplesPerPixel = Math.max(1, Math.floor((sampleEnd - sampleStart) / width));
    context.strokeStyle = "rgba(143, 183, 200, 0.78)";
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x < width; x += 1) {
      const from = sampleStart + x * samplesPerPixel;
      const to = Math.min(sampleEnd, from + samplesPerPixel);
      let min = 1;
      let max = -1;
      for (let i = from; i < to; i += 1) {
        const value = channel[i];
        if (value < min) min = value;
        if (value > max) max = value;
      }
      context.moveTo(x + 0.5, (1 + min) * height / 2);
      context.lineTo(x + 0.5, (1 + max) * height / 2);
    }
    context.stroke();
  } else {
    context.fillStyle = "rgba(162, 158, 150, 0.7)";
    context.font = "12px system-ui";
    context.textAlign = "center";
    context.fillText("选择母带后显示当前句附近的波形", width / 2, height / 2 + 4);
  }

  context.strokeStyle = "#f2db9f";
  context.lineWidth = 1.5;
  context.beginPath();
  context.moveTo(startX, 0);
  context.lineTo(startX, height);
  context.moveTo(endX, 0);
  context.lineTo(endX, height);
  context.stroke();

  const currentMs = elements.audio.currentTime * 1000;
  if (currentMs >= windowStart && currentMs <= windowEnd) {
    const playX = xFor(currentMs);
    context.strokeStyle = "#ffffff";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(playX, 0);
    context.lineTo(playX, height);
    context.stroke();
  }
  canvas.dataset.windowStart = String(windowStart);
  canvas.dataset.windowEnd = String(windowEnd);
}

function exportTimeline() {
  const exported = JSON.parse(JSON.stringify(timeline));
  let verified = 0;
  let flagged = 0;
  exported.lines = exported.lines.map((line) => {
    const review = reviewFor(line);
    const times = getTimes(line);
    if (review.status === "verified") verified += 1;
    if (review.status === "flagged") flagged += 1;
    return {
      ...line,
      start_ms: times.start,
      end_ms: times.end,
      alignment: {
        ...line.alignment,
        status: review.status === "verified" ? "manually_verified" : line.alignment.status,
      },
      manual_review: {
        status: review.status,
        notes: review.notes || "",
        candidate_start_ms: line.start_ms,
        candidate_end_ms: line.end_ms,
        adjusted: times.start !== line.start_ms || times.end !== line.end_ms,
        verified_at: review.verified_at || null,
        updated_at: review.updated_at || null,
      },
    };
  });
  exported.alignment = {
    ...exported.alignment,
    status: verified === exported.lines.length ? "manually_verified" : "manual_review_in_progress",
    manual_review_required: verified !== exported.lines.length,
    review_summary: {
      exported_at: new Date().toISOString(),
      verified_lines: verified,
      flagged_lines: flagged,
      pending_lines: exported.lines.length - verified - flagged,
      total_lines: exported.lines.length,
    },
  };
  exported.sections = exported.sections.map((section) => {
    const sectionLines = exported.lines.filter((line) => line.section_id === section.id);
    return {
      ...section,
      start_ms: Math.min(...sectionLines.map((line) => line.start_ms)),
      end_ms: Math.max(...sectionLines.map((line) => line.end_ms)),
    };
  });

  const blob = new Blob([`${JSON.stringify(exported, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "timeline.reviewed.json";
  link.click();
  URL.revokeObjectURL(url);
  notify(`已导出：${verified} 句确认，${flagged} 句需复核`);
}

function resetReview() {
  const hasProgress = Object.keys(localReviews).length > 0;
  if (hasProgress && !window.confirm("清除这首母带保存在当前浏览器中的全部校对进度？已导出的 JSON 不受影响。")) return;
  localReviews = {};
  localStorage.removeItem(storageKey());
  activeIndex = 0;
  updateProgress();
  renderActiveLine({ scroll: true });
  notify("本地校对进度已重置");
}

function onTimeUpdate() {
  const currentMs = elements.audio.currentTime * 1000;
  elements.playheadTime.textContent = formatTime(currentMs);
  const durationMs = elements.audio.duration * 1000 || timeline.timeline_timebase.duration_ms;
  elements.scrubber.value = String(Math.round((currentMs / durationMs) * 1000));
  drawWaveform();
}

function onKeydown(event) {
  const tag = event.target.tagName;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
  if (event.code === "Space") {
    event.preventDefault();
    togglePlayback();
  } else if (event.key.toLowerCase() === "r") {
    event.preventDefault();
    replayLine();
  } else if (event.key.toLowerCase() === "j") {
    selectLine(activeIndex - 1, true);
  } else if (event.key.toLowerCase() === "k") {
    selectLine(activeIndex + 1, true);
  } else if (event.key.toLowerCase() === "v") {
    setReviewStatus("verified", true);
  } else if ((event.metaKey || event.ctrlKey) && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    nudge("start", event.key === "ArrowLeft" ? -50 : 50);
  } else if (event.shiftKey && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    nudge("end", event.key === "ArrowLeft" ? -50 : 50);
  }
}

function bindEvents() {
  elements.loadAudio.addEventListener("click", () => elements.audioFile.click());
  elements.audioFile.addEventListener("change", () => loadAudioFile(elements.audioFile.files[0]));
  elements.exportJson.addEventListener("click", exportTimeline);
  elements.resetReview.addEventListener("click", resetReview);
  elements.search.addEventListener("input", renderLineList);
  elements.filter.addEventListener("change", renderLineList);
  elements.previous.addEventListener("click", () => selectLine(activeIndex - 1, true));
  elements.next.addEventListener("click", () => selectLine(activeIndex + 1, true));
  elements.replay.addEventListener("click", replayLine);
  elements.playPause.addEventListener("click", togglePlayback);
  elements.markFlagged.addEventListener("click", () => setReviewStatus("flagged"));
  elements.markVerified.addEventListener("click", () => setReviewStatus("verified", true));
  elements.notes.addEventListener("change", saveNotes);
  elements.startMs.addEventListener("change", () => setTimes(Number(elements.startMs.value), getTimes(activeLine()).end));
  elements.endMs.addEventListener("change", () => setTimes(getTimes(activeLine()).start, Number(elements.endMs.value)));
  document.querySelectorAll(".nudge-row button").forEach((button) => {
    button.addEventListener("click", () => nudge(button.parentElement.dataset.boundary, Number(button.dataset.delta)));
  });
  elements.audio.addEventListener("play", () => { elements.playPause.textContent = "暂停"; });
  elements.audio.addEventListener("pause", () => { elements.playPause.textContent = "播放"; });
  elements.audio.addEventListener("timeupdate", onTimeUpdate);
  elements.scrubber.addEventListener("input", () => {
    stopAtLineEnd();
    const duration = elements.audio.duration || timeline.timeline_timebase.duration_ms / 1000;
    elements.audio.currentTime = (Number(elements.scrubber.value) / 1000) * duration;
  });
  elements.waveform.addEventListener("click", (event) => {
    if (!elements.audio.src) return;
    const rect = elements.waveform.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const start = Number(elements.waveform.dataset.windowStart);
    const end = Number(elements.waveform.dataset.windowEnd);
    elements.audio.currentTime = (start + ratio * (end - start)) / 1000;
  });
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", drawWaveform);
}

async function init() {
  try {
    const response = await fetch(TIMELINE_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    timeline = await response.json();
    restoreLocal();
    bindEvents();
    updateProgress();
    renderActiveLine();
  } catch (error) {
    const main = document.createElement("main");
    main.style.cssText = "max-width:720px;margin:80px auto;padding:24px;color:#f4f0e7;font-family:system-ui";
    const heading = document.createElement("h1");
    const guidance = document.createElement("p");
    const details = document.createElement("pre");
    heading.textContent = "无法载入时间轴";
    guidance.textContent = "请从仓库根目录启动本地服务器，不要直接双击 HTML 文件。";
    details.textContent = String(error);
    main.append(heading, guidance, details);
    document.body.replaceChildren(main);
  }
}

init();
