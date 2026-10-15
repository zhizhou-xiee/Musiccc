const player = document.querySelector("#mv-player");
const playbackStatus = document.querySelector("#playback-status");
const mediaError = document.querySelector("#media-error");
const chapterList = document.querySelector("#chapter-list");
const creditList = document.querySelector("#credit-list");
const performerList = document.querySelector("#performer-list");
const performerCount = document.querySelector("#performer-count");
const mvDuration = document.querySelector("#mv-duration");

let chapters = [];

const formatTime = (milliseconds) => {
  const totalSeconds = Math.round(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};

const setStatus = (text) => {
  playbackStatus.textContent = text;
};

const renderCredits = (credits, versionName) => {
  const rows = [{ label: "版本", names: [versionName] }, ...credits];
  creditList.replaceChildren(
    ...rows.map(({ label, names }) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = names.join("、");
      row.append(term, description);
      return row;
    }),
  );
};

const renderPerformers = (performers) => {
  performerCount.textContent = String(performers.length);
  performerList.replaceChildren(
    ...performers.map((performer, index) => {
      const item = document.createElement("li");
      const number = document.createElement("span");
      const name = document.createElement("span");
      number.className = "performer-index";
      number.textContent = String(index + 1).padStart(2, "0");
      name.textContent = performer.display_name;
      item.dataset.performerId = performer.id;
      item.append(number, name);
      return item;
    }),
  );
};

const seekToChapter = (chapter) => {
  const seek = () => {
    player.currentTime = chapter.start_ms / 1000;
    player.focus({ preventScroll: true });
    document.querySelector(".player-shell")?.scrollIntoView({ behavior: "smooth", block: "center" });
    setStatus(`已跳到：${chapter.title}`);
  };

  if (player.readyState >= HTMLMediaElement.HAVE_METADATA) {
    seek();
  } else {
    player.addEventListener("loadedmetadata", seek, { once: true });
    player.load();
  }
};

const renderChapters = (sectionData) => {
  chapters = sectionData;
  chapterList.replaceChildren(
    ...chapters.map((chapter) => {
      const button = document.createElement("button");
      const time = document.createElement("span");
      const title = document.createElement("span");
      button.className = "chapter-button";
      button.type = "button";
      button.dataset.chapterId = chapter.id;
      button.setAttribute("aria-label", `跳到 ${formatTime(chapter.start_ms)} ${chapter.title}`);
      time.className = "chapter-time";
      time.textContent = formatTime(chapter.start_ms);
      title.className = "chapter-title";
      title.textContent = chapter.title;
      button.append(time, title);
      button.addEventListener("click", () => seekToChapter(chapter));
      return button;
    }),
  );
};

const updateCurrentChapter = () => {
  const currentMs = player.currentTime * 1000;
  const active = chapters.find(
    (chapter) => currentMs >= chapter.start_ms && currentMs < chapter.end_ms,
  );
  document.querySelectorAll(".chapter-button").forEach((button) => {
    const isCurrent = button.dataset.chapterId === active?.id;
    if (isCurrent) {
      button.setAttribute("aria-current", "true");
    } else {
      button.removeAttribute("aria-current");
    }
  });
};

const wirePlayerEvents = () => {
  player.addEventListener("play", () => setStatus("正在播放"));
  player.addEventListener("pause", () => {
    if (!player.ended) setStatus("已暂停");
  });
  player.addEventListener("waiting", () => setStatus("正在缓冲…"));
  player.addEventListener("stalled", () => setStatus("网络较慢，正在继续加载…"));
  player.addEventListener("seeking", () => setStatus("正在跳转…"));
  player.addEventListener("seeked", () => setStatus(player.paused ? "已定位" : "正在播放"));
  player.addEventListener("ended", () => setStatus("播放完毕"));
  player.addEventListener("timeupdate", updateCurrentChapter);
  player.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(player.duration)) mvDuration.textContent = formatTime(player.duration * 1000);
  });
  player.addEventListener("error", () => {
    mediaError.hidden = false;
    setStatus("加载失败");
  });
};

const loadSong = async () => {
  const response = await fetch("/music/data/song.json");
  if (!response.ok) throw new Error(`Song data returned ${response.status}`);
  const data = await response.json();

  document.title = `${data.song.title}｜音乐展厅`;
  mvDuration.textContent = formatTime(data.media.video_duration_ms);
  if (data.media.video_url && player.getAttribute("src") !== data.media.video_url) {
    player.src = data.media.video_url;
  }
  if (data.media.poster_url) player.poster = data.media.poster_url;
  renderCredits(data.credits, data.song.version_name);
  renderPerformers(data.performers);
  renderChapters(data.sections);
};

wirePlayerEvents();
loadSong().catch((error) => {
  console.error("Unable to load song data", error);
  document.querySelectorAll(".loading-copy").forEach((element) => {
    element.textContent = "资料暂时没有加载成功。";
  });
});
