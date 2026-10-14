const SUMMARY_URL = "../../data/songs/jieyue/experiments/perception/candidate_b_summaries.json";
const FEATURE_URL = "../../data/songs/jieyue/experiments/perception/candidate_a_features.json";
const TIMELINE_URL = "../../data/songs/jieyue/timeline.reference.json";
const STORAGE_PREFIX = "jieyue-summary-review";

const $ = (selector) => document.querySelector(selector);
const elements = {
  audio: $("#audio"),
  audioFile: $("#audio-file"),
  loadAudio: $("#load-audio"),
  reviewFile: $("#review-file"),
  importJson: $("#import-json"),
  exportJson: $("#export-json"),
  resetReview: $("#reset-review"),
  fileDot: $("#file-dot"),
  fileStatus: $("#file-status"),
  reviewCount: $("#review-count"),
  progressFill: $("#progress-fill"),
  filter: $("#review-filter"),
  segmentList: $("#segment-list"),
  segmentPosition: $("#segment-position"),
  segmentTime: $("#segment-time"),
  segmentStatus: $("#segment-status"),
  segmentTitle: $("#segment-title"),
  previous: $("#previous"),
  next: $("#next"),
  replay: $("#replay"),
  playPause: $("#play-pause"),
  loopSegment: $("#loop-segment"),
  scrubber: $("#scrubber"),
  playheadTime: $("#playhead-time"),
  segmentEndTime: $("#segment-end-time"),
  humanEvidence: $("#human-evidence"),
  featureList: $("#feature-list"),
  lyricsList: $("#lyrics-list"),
  summaryText: $("#summary-text"),
  summaryLength: $("#summary-length"),
  restoreDraft: $("#restore-draft"),
  notes: $("#review-notes"),
  markPending: $("#mark-pending"),
  markFlagged: $("#mark-flagged"),
  markVerified: $("#mark-verified"),
  toast: $("#toast"),
};

let summaryData;
let featureData;
let timeline;
let activeIndex = 0;
let audioUrl;
let objectVersion = 0;
let toastTimer;
let reviews = {};

function formatTime(ms) {
  const safe = Math.max(0, Number(ms) || 0);
  const minutes = Math.floor(safe / 60000);
  const seconds = Math.floor((safe % 60000) / 1000);
  const millis = Math.floor(safe % 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function activeSegment() {
  return summaryData.segments[activeIndex];
}

function featureSegment(id) {
  return featureData.segments.find((segment) => segment.segment_id === id);
}

function initialText(segment) {
  return segment.perception.summary.trim();
}

function reviewFor(segment) {
  return reviews[segment.segment_id] || {
    summary: initialText(segment),
    status: "pending",
    notes: "",
  };
}

function storageKey() {
  return `${STORAGE_PREFIX}:${summaryData.schema_version}:${summaryData.song_id}:${summaryData.generated_from_audio_sha256}`;
}

function saveLocal() {
  localStorage.setItem(storageKey(), JSON.stringify({ version: 1, reviews }));
}

function restoreLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || "null");
    if (saved?.version === 1 && saved.reviews && typeof saved.reviews === "object") reviews = saved.reviews;
  } catch {
    reviews = {};
  }
}

function ensureReview(segment = activeSegment()) {
  if (!reviews[segment.segment_id]) reviews[segment.segment_id] = { ...reviewFor(segment) };
  return reviews[segment.segment_id];
}

function notify(message, isError = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function statusCopy(status) {
  return ({ pending: "待校对", flagged: "需复核", verified: "已确认" })[status] || "待校对";
}

function updateProgress() {
  const total = summaryData.segments.length;
  const verified = summaryData.segments.filter((segment) => reviewFor(segment).status === "verified").length;
  elements.reviewCount.textContent = `${verified} / ${total} 已确认`;
  elements.progressFill.style.width = `${(verified / total) * 100}%`;
}

function renderSegmentList() {
  const filter = elements.filter.value;
  const fragment = document.createDocumentFragment();
  let matches = 0;
  summaryData.segments.forEach((segment, index) => {
    const review = reviewFor(segment);
    if (filter !== "all" && review.status !== filter) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `segment-item${index === activeIndex ? " active" : ""}`;
    button.innerHTML = `
      <span class="segment-number">${String(index + 1).padStart(2, "0")}</span>
      <span class="segment-copy"><span class="segment-name"></span><span class="segment-duration"></span></span>
      <span class="review-mark ${review.status}" aria-label="${statusCopy(review.status)}"></span>`;
    button.querySelector(".segment-name").textContent = segment.title;
    button.querySelector(".segment-duration").textContent = `${formatTime(segment.start_ms)}–${formatTime(segment.end_ms)}`;
    button.addEventListener("click", () => selectSegment(index, true));
    fragment.append(button);
    matches += 1;
  });
  elements.segmentList.replaceChildren(fragment);
  if (!matches) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "没有符合条件的段落";
    elements.segmentList.append(empty);
  }
}

function evidenceItem(label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value || "—";
  wrapper.append(term, description);
  return wrapper;
}

function uniquePerformers(segment, role) {
  const names = [];
  segment.lyrics.forEach((line) => {
    line.performers.filter((person) => person.role === role).forEach((person) => {
      if (!names.includes(person.name)) names.push(person.name);
    });
  });
  return names;
}

function overlappingInstruments(segment) {
  const names = [];
  timeline.instrument_events.forEach((event) => {
    const overlap = Math.max(0, Math.min(segment.end_ms, event.end_ms) - Math.max(segment.start_ms, event.start_ms));
    const threshold = Math.max(1000, (segment.end_ms - segment.start_ms) * 0.1);
    if (overlap < threshold) return;
    event.instruments.filter(Boolean).forEach((instrument) => {
      if (!names.includes(instrument)) names.push(instrument);
    });
  });
  return names;
}

function renderHumanEvidence(segment) {
  const leads = uniquePerformers(segment, "lead");
  const backing = uniquePerformers(segment, "backing");
  const instruments = overlappingInstruments(segment);
  elements.humanEvidence.replaceChildren(
    evidenceItem("主唱", leads.join("、") || "本段无歌词"),
    evidenceItem("和声", backing.join("、") || "未单独标注"),
    evidenceItem("乐器粗标", instruments.join("、") || "现有资料未提供独立条目"),
  );
}

function featureItem(label, value) {
  const item = document.createElement("div");
  item.className = "feature";
  const labelElement = document.createElement("span");
  const valueElement = document.createElement("span");
  labelElement.className = "feature-label";
  valueElement.className = "feature-value";
  labelElement.textContent = label;
  valueElement.textContent = value;
  item.append(labelElement, valueElement);
  return item;
}

function renderFeatures(segment) {
  const features = featureSegment(segment.segment_id).perception.features;
  elements.featureList.replaceChildren(
    featureItem("综合响度", `${features.integrated_lufs.toFixed(1)} LUFS`),
    featureItem("动态范围", `${features.loudness_range_lu.toFixed(1)} LU`),
    featureItem("频谱质心中位数", `${Math.round(features.spectral_centroid_hz_median)} Hz`),
    featureItem("频谱变化量", features.spectral_flux_median.toFixed(4)),
    featureItem("前 / 中 / 后响度", features.loudness_profile_lufs.map((value) => value.toFixed(1)).join(" / ")),
    featureItem("人声时间覆盖", `${Math.round(features.vocal_coverage_ratio * 100)}%`),
  );
}

function performerCopy(line) {
  const leads = line.performers.filter((person) => person.role === "lead").map((person) => person.name);
  const backing = line.performers.filter((person) => person.role === "backing").map((person) => person.name);
  return backing.length ? `${leads.join("、")}｜和声：${backing.join("、")}` : leads.join("、");
}

function renderLyrics(segment) {
  if (!segment.lyrics.length) {
    const copy = document.createElement("p");
    copy.className = "instrumental-copy";
    copy.textContent = "本段没有歌词，是纯器乐段落。";
    elements.lyricsList.replaceChildren(copy);
    return;
  }
  const fragment = document.createDocumentFragment();
  segment.lyrics.forEach((line) => {
    const row = document.createElement("div");
    row.className = "lyric-line";
    const time = document.createElement("span");
    const text = document.createElement("span");
    const performer = document.createElement("span");
    time.className = "lyric-time";
    performer.className = "lyric-performer";
    time.textContent = formatTime(line.start_ms).slice(0, -4);
    text.textContent = line.text;
    performer.textContent = performerCopy(line);
    row.append(time, text, performer);
    fragment.append(row);
  });
  elements.lyricsList.replaceChildren(fragment);
}

function renderActive({ scroll = false } = {}) {
  const segment = activeSegment();
  const review = reviewFor(segment);
  elements.segmentPosition.textContent = `第 ${activeIndex + 1} / ${summaryData.segments.length} 段`;
  elements.segmentTime.textContent = `${formatTime(segment.start_ms)}–${formatTime(segment.end_ms)}`;
  elements.segmentEndTime.textContent = formatTime(segment.end_ms);
  elements.segmentTitle.textContent = segment.title;
  elements.segmentStatus.textContent = statusCopy(review.status);
  elements.segmentStatus.className = `status-label ${review.status}`;
  elements.summaryText.value = review.summary;
  elements.notes.value = review.notes || "";
  elements.summaryLength.textContent = `${review.summary.length} 字`;
  renderHumanEvidence(segment);
  renderFeatures(segment);
  renderLyrics(segment);
  renderSegmentList();
  updateScrubber();
  if (scroll) elements.segmentList.querySelector(".segment-item.active")?.scrollIntoView({ block: "center" });
}

function selectSegment(index, seek = false) {
  activeIndex = Math.max(0, Math.min(summaryData.segments.length - 1, index));
  if (seek && elements.audio.src) elements.audio.currentTime = activeSegment().start_ms / 1000;
  renderActive({ scroll: true });
}

function saveEditor() {
  const review = ensureReview();
  review.summary = elements.summaryText.value.trim();
  review.notes = elements.notes.value.trim();
  review.updated_at = new Date().toISOString();
  if (review.status === "verified") {
    review.status = "pending";
    delete review.verified_at;
  }
  saveLocal();
  elements.summaryLength.textContent = `${review.summary.length} 字`;
  elements.segmentStatus.textContent = statusCopy(review.status);
  elements.segmentStatus.className = `status-label ${review.status}`;
  renderSegmentList();
  updateProgress();
}

function setReviewStatus(status, advance = false) {
  const segment = activeSegment();
  const review = ensureReview(segment);
  review.summary = elements.summaryText.value.trim();
  review.notes = elements.notes.value.trim();
  if (!review.summary) {
    notify("摘要不能为空", true);
    elements.summaryText.focus();
    return;
  }
  review.status = status;
  review.updated_at = new Date().toISOString();
  if (status === "verified") review.verified_at = review.updated_at;
  else delete review.verified_at;
  saveLocal();
  updateProgress();
  renderSegmentList();
  notify(status === "verified" ? `已确认：${segment.title}` : status === "flagged" ? `已标记需复核：${segment.title}` : `已暂存：${segment.title}`);
  if (advance && activeIndex < summaryData.segments.length - 1) selectSegment(activeIndex + 1, true);
  else renderActive();
}

function restoreDraft() {
  const original = initialText(activeSegment());
  if (elements.summaryText.value.trim() !== original && !window.confirm("用最初的自动草稿覆盖当前段落的修改？")) return;
  elements.summaryText.value = original;
  saveEditor();
  notify("已恢复当前段落的最初草稿");
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
  const valid = hash ? hash === summaryData.generated_from_audio_sha256 : file.name === timeline.timeline_timebase.asset;
  elements.fileDot.className = `status-dot ${valid ? "valid" : "invalid"}`;
  elements.fileStatus.textContent = valid
    ? `${file.name} · 已核对为实验使用的 MP3 母带`
    : `${file.name} · 与实验记录的母带不一致`;
  notify(valid ? "母带已载入，音频不会离开这台设备" : "文件指纹不一致；可以试听，但不要据此确认摘要", !valid);
  elements.audio.currentTime = activeSegment().start_ms / 1000;
}

async function playSegment(fromStart = false) {
  if (!elements.audio.src) {
    elements.audioFile.click();
    return;
  }
  const segment = activeSegment();
  if (fromStart || elements.audio.currentTime * 1000 < segment.start_ms || elements.audio.currentTime * 1000 >= segment.end_ms) {
    elements.audio.currentTime = segment.start_ms / 1000;
  }
  try {
    await elements.audio.play();
  } catch {
    notify("浏览器未能开始播放，请再点一次播放", true);
  }
}

function togglePlayback() {
  if (elements.audio.paused) playSegment(false);
  else elements.audio.pause();
}

function updateScrubber() {
  if (!summaryData) return;
  const segment = activeSegment();
  const currentMs = elements.audio.currentTime * 1000;
  const bounded = Math.max(segment.start_ms, Math.min(segment.end_ms, currentMs || segment.start_ms));
  const progress = (bounded - segment.start_ms) / (segment.end_ms - segment.start_ms);
  elements.scrubber.value = String(Math.round(progress * 1000));
  elements.playheadTime.textContent = formatTime(bounded);
}

function onTimeUpdate() {
  const segment = activeSegment();
  const currentMs = elements.audio.currentTime * 1000;
  if (!elements.audio.paused && currentMs >= segment.end_ms - 35) {
    if (elements.loopSegment.checked) {
      elements.audio.currentTime = segment.start_ms / 1000;
      elements.audio.play().catch(() => {});
    } else {
      elements.audio.pause();
      elements.audio.currentTime = segment.end_ms / 1000;
    }
  }
  updateScrubber();
}

function exportReview() {
  let verified = 0;
  let flagged = 0;
  const segments = summaryData.segments.map((segment) => {
    const review = reviewFor(segment);
    if (review.status === "verified") verified += 1;
    if (review.status === "flagged") flagged += 1;
    return {
      segment_id: segment.segment_id,
      title: segment.title,
      start_ms: segment.start_ms,
      end_ms: segment.end_ms,
      summary: review.summary,
      original_draft: initialText(segment),
      review: {
        status: review.status,
        notes: review.notes || "",
        updated_at: review.updated_at || null,
        verified_at: review.verified_at || null,
      },
      provenance: {
        lyrics_and_performers: "human_timeline",
        instruments: "human_annotation_coarse",
        loudness_and_spectral_evidence: "automatic_measurement",
        final_summary: review.status === "verified" ? "human_reviewed" : "draft_needs_listening_review",
      },
    };
  });
  const exported = {
    schema_version: "0.1.0",
    song_id: summaryData.song_id,
    generated_from_audio_sha256: summaryData.generated_from_audio_sha256,
    perception_kind: "pre_generated_music_summary",
    perception_notice: "摘要用于向不能直接接收音频的模型提供音乐事实，不表示模型听到了原始音频。",
    review_summary: {
      exported_at: new Date().toISOString(),
      verified_segments: verified,
      flagged_segments: flagged,
      pending_segments: segments.length - verified - flagged,
      total_segments: segments.length,
    },
    segments,
  };
  const blob = new Blob([`${JSON.stringify(exported, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "jieyue.music-summaries.reviewed.json";
  link.click();
  URL.revokeObjectURL(url);
  notify(`已导出：${verified} 段确认，${flagged} 段需复核`);
}

async function importReview(file) {
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    if (imported.song_id !== summaryData.song_id || !Array.isArray(imported.segments)) throw new Error("不是《借月》的摘要校对文件");
    const known = new Set(summaryData.segments.map((segment) => segment.segment_id));
    const nextReviews = {};
    imported.segments.forEach((segment) => {
      if (!known.has(segment.segment_id) || typeof segment.summary !== "string") return;
      nextReviews[segment.segment_id] = {
        summary: segment.summary,
        status: ["pending", "flagged", "verified"].includes(segment.review?.status) ? segment.review.status : "pending",
        notes: segment.review?.notes || "",
        updated_at: segment.review?.updated_at || new Date().toISOString(),
        verified_at: segment.review?.verified_at || undefined,
      };
    });
    if (!Object.keys(nextReviews).length) throw new Error("文件中没有可识别的段落");
    reviews = nextReviews;
    saveLocal();
    updateProgress();
    renderActive();
    notify(`已载入 ${Object.keys(nextReviews).length} 个段落的校对稿`);
  } catch (error) {
    notify(`载入失败：${error.message}`, true);
  } finally {
    elements.reviewFile.value = "";
  }
}

function resetReview() {
  if (Object.keys(reviews).length && !window.confirm("清除当前浏览器中的全部摘要修改和确认状态？已导出的 JSON 不受影响。")) return;
  reviews = {};
  localStorage.removeItem(storageKey());
  activeIndex = 0;
  updateProgress();
  renderActive({ scroll: true });
  notify("本地摘要校对进度已重置");
}

function onKeydown(event) {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
  if (event.code === "Space") {
    event.preventDefault();
    togglePlayback();
  } else if (event.key.toLowerCase() === "r") {
    event.preventDefault();
    playSegment(true);
  } else if (event.key.toLowerCase() === "j") {
    selectSegment(activeIndex - 1, true);
  } else if (event.key.toLowerCase() === "k") {
    selectSegment(activeIndex + 1, true);
  } else if (event.key.toLowerCase() === "v") {
    setReviewStatus("verified", true);
  }
}

function bindEvents() {
  elements.loadAudio.addEventListener("click", () => elements.audioFile.click());
  elements.audioFile.addEventListener("change", () => loadAudioFile(elements.audioFile.files[0]));
  elements.importJson.addEventListener("click", () => elements.reviewFile.click());
  elements.reviewFile.addEventListener("change", () => importReview(elements.reviewFile.files[0]));
  elements.exportJson.addEventListener("click", exportReview);
  elements.resetReview.addEventListener("click", resetReview);
  elements.filter.addEventListener("change", renderSegmentList);
  elements.previous.addEventListener("click", () => selectSegment(activeIndex - 1, true));
  elements.next.addEventListener("click", () => selectSegment(activeIndex + 1, true));
  elements.replay.addEventListener("click", () => playSegment(true));
  elements.playPause.addEventListener("click", togglePlayback);
  elements.scrubber.addEventListener("input", () => {
    if (!elements.audio.src) return;
    const segment = activeSegment();
    const progress = Number(elements.scrubber.value) / 1000;
    elements.audio.currentTime = (segment.start_ms + progress * (segment.end_ms - segment.start_ms)) / 1000;
  });
  elements.summaryText.addEventListener("input", saveEditor);
  elements.notes.addEventListener("input", saveEditor);
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
    const responses = await Promise.all([
      fetch(SUMMARY_URL, { cache: "no-store" }),
      fetch(FEATURE_URL, { cache: "no-store" }),
      fetch(TIMELINE_URL, { cache: "no-store" }),
    ]);
    if (responses.some((response) => !response.ok)) throw new Error(`HTTP ${responses.map((response) => response.status).join(" / ")}`);
    [summaryData, featureData, timeline] = await Promise.all(responses.map((response) => response.json()));
    restoreLocal();
    bindEvents();
    updateProgress();
    renderActive();
  } catch (error) {
    const main = document.createElement("main");
    main.style.cssText = "max-width:720px;margin:80px auto;padding:24px;color:#f3efe6;font-family:system-ui";
    const heading = document.createElement("h1");
    const guidance = document.createElement("p");
    const details = document.createElement("pre");
    heading.textContent = "无法载入摘要实验数据";
    guidance.textContent = "请从仓库根目录启动本地服务器，不要直接双击 HTML 文件。";
    details.textContent = String(error);
    main.append(heading, guidance, details);
    document.body.replaceChildren(main);
  }
}

init();
