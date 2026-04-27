// AutoPrompt Annotator 5.0 — vanilla JS frontend
// Tries to keep things small but functional: file upload, model selection,
// streaming annotation sessions, bbox drawing, video timestamp overlay,
// CoOp polling, benchmark, help mode, and a minimal tour.

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  os: "linux",
  files: [],            // [{file_id, type, metadata, path}]
  selectedFileId: null,
  modelName: null,
  sessionId: null,
  currentFile: null,    // {file_id, type, metadata}
  boxes: [],            // [{class, x1,y1,x2,y2}]
  drawing: null,        // {x1,y1}
  videoOverlayOn: false,
  coopRunId: null,
};

async function api(path, opts = {}) {
  const init = { headers: {}, ...opts };
  if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(data.detail || data.message || text || res.statusText);
  return data;
}

// ---------- OS detection + upload UI ----------
async function detectOS() {
  const { os } = await api("/get_os_type");
  state.os = os;
  $("#upload-hint").textContent = os === "windows"
    ? "Windows: drag&drop или выбор файлов"
    : "Linux: введите пути (по одному на строку)";
  $("#upload-windows").classList.toggle("hidden", os !== "windows");
  // On Linux we still allow drag&drop, just keep both visible:
  if (os === "linux") {
    $("#upload-linux").classList.remove("hidden");
    $("#upload-windows").classList.remove("hidden");
  } else {
    $("#upload-linux").classList.add("hidden");
  }
}

function appendUploaded(meta) {
  state.files.push(meta);
  const li = document.createElement("li");
  li.dataset.fileId = meta.file_id;
  li.innerHTML = `<span>[${meta.type}] ${meta.path.split(/[\\/]/).pop()}</span><span>#${meta.file_id}</span>`;
  li.onclick = () => selectFile(meta.file_id);
  $("#file-list").appendChild(li);
}

async function uploadFiles(fileList) {
  const fd = new FormData();
  for (const f of fileList) fd.append("files", f);
  const data = await api("/upload", { method: "POST", body: fd });
  data.metadata.forEach(appendUploaded);
}

async function uploadPaths() {
  const paths = $("#paths-input").value.split("\n").map(s => s.trim()).filter(Boolean);
  if (!paths.length) return;
  const data = await api("/upload", { method: "POST", body: { paths } });
  data.metadata.forEach(appendUploaded);
  $("#paths-input").value = "";
}

function selectFile(fileId) {
  state.selectedFileId = fileId;
  $$("#file-list li").forEach(li => li.classList.toggle("selected", +li.dataset.fileId === fileId));
  const meta = state.files.find(f => f.file_id === fileId);
  if (meta) showFile(meta);
}

function showFile(meta) {
  state.currentFile = meta;
  const v = $("#video-player"), iw = $("#image-wrap"), tv = $("#text-view");
  v.classList.add("hidden"); iw.classList.add("hidden"); tv.classList.add("hidden");
  $("#video-tools").classList.add("hidden");
  $("#bbox-tools").classList.add("hidden");

  if (meta.type === "video") {
    v.src = `/files/${meta.file_id}`;
    v.classList.remove("hidden");
    $("#video-tools").classList.remove("hidden");
  } else if (meta.type === "image") {
    const img = $("#image-view");
    img.onload = () => {
      const canvas = $("#bbox-canvas");
      canvas.width = img.clientWidth;
      canvas.height = img.clientHeight;
      drawBoxes();
    };
    img.src = `/files/${meta.file_id}`;
    iw.classList.remove("hidden");
    $("#bbox-tools").classList.remove("hidden");
    state.boxes = [];
  } else if (meta.type === "text") {
    fetch(`/files/${meta.file_id}`).then(r => r.text()).then(t => {
      tv.textContent = t;
      tv.classList.remove("hidden");
    });
  }
}

// ---------- bbox drawing ----------
function drawBoxes() {
  const canvas = $("#bbox-canvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 2; ctx.font = "13px sans-serif";
  for (const b of state.boxes) {
    ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1);
    ctx.fillStyle = "#ef4444"; ctx.fillText(b.class, b.x1 + 2, b.y1 + 14);
  }
  if (state.drawing) {
    ctx.strokeStyle = "#3b82f6";
    ctx.strokeRect(state.drawing.x1, state.drawing.y1,
      state.drawing.x2 - state.drawing.x1, state.drawing.y2 - state.drawing.y1);
  }
}

function setupBboxCanvas() {
  const c = $("#bbox-canvas");
  c.addEventListener("mousedown", (e) => {
    const r = c.getBoundingClientRect();
    state.drawing = { x1: e.clientX - r.left, y1: e.clientY - r.top, x2: 0, y2: 0 };
  });
  c.addEventListener("mousemove", (e) => {
    if (!state.drawing) return;
    const r = c.getBoundingClientRect();
    state.drawing.x2 = e.clientX - r.left;
    state.drawing.y2 = e.clientY - r.top;
    drawBoxes();
  });
  c.addEventListener("mouseup", () => {
    if (!state.drawing) return;
    const cls = $("#bbox-class").value || "object";
    state.boxes.push({ class: cls, ...state.drawing });
    state.drawing = null;
    drawBoxes();
  });
}

async function saveBboxes() {
  if (!state.currentFile) return;
  const img = $("#image-view");
  const sx = img.naturalWidth / img.clientWidth;
  const sy = img.naturalHeight / img.clientHeight;
  const boxes = state.boxes.map(b => ({
    class: b.class,
    x1: Math.round(b.x1 * sx), y1: Math.round(b.y1 * sy),
    x2: Math.round(b.x2 * sx), y2: Math.round(b.y2 * sy),
  }));
  const data = await api("/image/bbox/save", {
    method: "POST",
    body: { file_id: state.currentFile.file_id, format: $("#bbox-format").value, boxes },
  });
  alert("Сохранено: " + data.annotation_file);
}

// ---------- video timestamp ----------
function videoTimestamp(ts) {
  const h = Math.floor(ts / 3600).toString().padStart(2, "0");
  const m = Math.floor((ts % 3600) / 60).toString().padStart(2, "0");
  const s = Math.floor(ts % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function setupVideoTimestamp() {
  $("#timestamp-btn").onclick = () => {
    const v = $("#video-player");
    alert("Текущий таймкод: " + videoTimestamp(v.currentTime));
  };
  $("#export-video-btn").onclick = async () => {
    if (!state.currentFile || state.currentFile.type !== "video") return;
    const bitrate = prompt("Битрейт (например 2M, пусто = по умолчанию)", "");
    const useGpu = confirm("Использовать GPU (NVENC, только Linux)?");
    try {
      const r = await api("/video/burn_timestamp", {
        method: "POST",
        body: {
          file_id: state.currentFile.file_id,
          bitrate: bitrate || null,
          use_gpu: useGpu,
        },
      });
      alert("Готово: " + r.exported_url);
    } catch (e) { alert("Ошибка: " + e.message); }
  };
}

// ---------- models ----------
async function loadModels() {
  const list = await api("/models/list");
  const sel = $("#model-select");
  sel.innerHTML = "";
  for (const name of list) {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name; sel.appendChild(opt);
  }
  sel.onchange = () => state.modelName = sel.value;
  state.modelName = sel.value;
}

async function generateConfig() {
  const ident = $("#model-id-input").value.trim();
  if (!ident) return;
  const r = await api("/models/generate_config", { method: "POST", body: { model_identifier: ident } });
  if (r.error) {
    $("#generated-yaml").value = `# error: ${r.error}\n# fallback prompt:\n# ${r.fallback_prompt}\n\n${r.example_yaml || ""}`;
  } else {
    $("#generated-yaml").value = r.yaml;
  }
}

async function saveConfig() {
  const name = $("#save-name").value.trim();
  const yamlText = $("#generated-yaml").value;
  if (!name || !yamlText) return alert("Укажите имя и YAML");
  await api("/models/save_config", { method: "POST", body: { name, yaml: yamlText } });
  await loadModels();
  alert("Сохранено: " + name);
}

// ---------- session ----------
async function startSession() {
  const datasetName = $("#dataset-name").value.trim() || "dataset";
  const fileIds = state.files.map(f => f.file_id);
  if (!fileIds.length) return alert("Сначала загрузите файлы");
  const r = await api("/annotate/start", {
    method: "POST",
    body: { dataset_name: datasetName, model_name: state.modelName, file_ids: fileIds },
  });
  state.sessionId = r.session_id;
  $("#finalize-session-btn").classList.remove("hidden");
  selectFile(fileIds[0]);
  $("#session-progress").textContent = `Сессия ${state.sessionId.slice(0, 8)}, прогресс 0/${fileIds.length}`;
}

async function checkPrompt() {
  const r = await api("/check_prompt_giga", {
    method: "POST",
    body: {
      question: $("#question").value,
      answer: $("#answer").value,
      model_name: state.modelName,
    },
  });
  const el = $("#check-result");
  el.className = r.valid ? "ok" : "bad";
  el.textContent = (r.valid ? "OK" : "Замечания: ") + " " + (r.message || "")
    + (r.suggestions?.length ? " — " + r.suggestions.join("; ") : "");
}

async function improvePrompt() {
  const r = await api("/improve_prompt_giga", {
    method: "POST",
    body: { question: $("#question").value, model_name: state.modelName },
  });
  $("#question").value = r.improved_question;
}

async function submitAnnotation(e) {
  e.preventDefault();
  if (!state.sessionId) return alert("Сначала начните сессию");
  const body = {
    session_id: state.sessionId,
    question: $("#question").value,
    answer: $("#answer").value,
  };
  if (state.currentFile?.type === "video") {
    body.timestamp = $("#video-player").currentTime;
  }
  const r = await api("/save_annotation", { method: "POST", body });
  $("#session-progress").textContent = `Сессия ${state.sessionId.slice(0, 8)}, прогресс ${r.progress}`;
  $("#question").value = ""; $("#answer").value = "";
  try {
    const next = await api("/annotate/next", { method: "POST", body: { session_id: state.sessionId } });
    const meta = state.files.find(f => f.file_id === next.file_id);
    if (meta) selectFile(meta.file_id);
  } catch {
    alert("Все файлы размечены — нажмите «Завершить»");
  }
}

async function finalizeSession() {
  if (!state.sessionId) return;
  const r = await api("/annotate/finalize", { method: "POST", body: { session_id: state.sessionId } });
  alert("Датасет сохранён: " + r.dataset_path);
  state.sessionId = null;
  $("#finalize-session-btn").classList.add("hidden");
}

// ---------- coop ----------
async function trainCoop() {
  if (!state.modelName) return alert("Сначала выберите модель");
  const datasetName = $("#dataset-name").value.trim() || "dataset";
  const r = await api("/coop/train", {
    method: "POST",
    body: {
      model_name: state.modelName,
      dataset_name: datasetName,
      coop_type: $("#coop-type").value,
      num_vectors: +$("#coop-num-vectors").value,
      context_init: $("#coop-context-init").value,
      class_token_position: "end",
      net_depth: 3,
    },
  });
  state.coopRunId = r.run_id;
  $("#coop-log").textContent = "started: " + r.run_id;
  pollCoop();
}

async function pollCoop() {
  if (!state.coopRunId) return;
  try {
    const r = await api("/coop/status/" + state.coopRunId);
    $("#coop-log").textContent = `[${r.status}]\n${r.log}`;
    if (r.status === "running") setTimeout(pollCoop, 1500);
  } catch (e) {
    $("#coop-log").textContent = "ошибка: " + e.message;
  }
}

// ---------- benchmark ----------
async function runBenchmark() {
  const split = (s) => s.split("\n").map(x => x.trim()).filter(Boolean);
  const r = await api("/benchmark/compare", {
    method: "POST",
    body: {
      model_name: state.modelName,
      questions: split($("#bench-questions").value),
      answers_before: split($("#bench-before").value),
      answers_after: split($("#bench-after").value),
    },
  });
  $("#bench-result").textContent = JSON.stringify(r, null, 2);
}

// ---------- help mode + tour ----------
function setupHelp() {
  $("#help-btn").onclick = () => document.body.classList.toggle("help-mode");
  document.body.addEventListener("click", async (e) => {
    if (!document.body.classList.contains("help-mode")) return;
    e.preventDefault(); e.stopPropagation();
    let target = e.target;
    let selector = "";
    while (target && target !== document.body) {
      if (target.id) { selector = "#" + target.id; break; }
      target = target.parentElement;
    }
    if (!selector) return;
    try {
      const data = await api("/help/" + encodeURIComponent(selector));
      const tip = $("#help-tooltip");
      tip.classList.remove("hidden");
      tip.style.left = (e.clientX + 12) + "px";
      tip.style.top = (e.clientY + 12) + "px";
      tip.innerHTML = `<b>${data.title}</b><br>${data.description}<br><i>${data.example || ""}</i>`;
    } catch (err) { /* ignore */ }
  }, true);
  document.body.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.body.classList.remove("help-mode");
      $("#help-tooltip").classList.add("hidden");
    }
  });
}

const TOUR_STEPS = [
  { sel: "#upload-area", text: "Сначала загрузите файлы." },
  { sel: "#model-select", text: "Выберите модель из списка или сгенерируйте новую." },
  { sel: "#start-session-btn", text: "Запустите сессию разметки." },
  { sel: "#annotate-form", text: "Размечайте Q&A. GigaChat поможет проверить и улучшить вопрос." },
  { sel: "#coop-train-btn", text: "Когда датасет готов — запустите CoOp/CoCoOp." },
  { sel: "#benchmark-btn", text: "Сравните качество модели до и после оптимизации." },
];

function startTour() {
  let i = 0;
  const overlay = $("#tour-overlay");
  function show() {
    if (i >= TOUR_STEPS.length) { overlay.classList.add("hidden"); return; }
    const step = TOUR_STEPS[i];
    const el = $(step.sel);
    overlay.innerHTML = `<div class="tour-card">
      <h3>Шаг ${i + 1}/${TOUR_STEPS.length}</h3>
      <p>${step.text}</p>
      <p style="color:#6b7280; font-size:11px;">Элемент: ${step.sel}</p>
      <button id="tour-next">${i === TOUR_STEPS.length - 1 ? "Готово" : "Далее"}</button>
    </div>`;
    overlay.classList.remove("hidden");
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    $("#tour-next").onclick = () => { i++; show(); };
  }
  show();
}

// ---------- bootstrap ----------
window.addEventListener("DOMContentLoaded", async () => {
  setupBboxCanvas();
  setupVideoTimestamp();
  setupHelp();

  $("#file-input").addEventListener("change", (e) => uploadFiles(e.target.files));
  $("#dropzone").addEventListener("dragover", e => e.preventDefault());
  $("#dropzone").addEventListener("drop", e => {
    e.preventDefault();
    if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
  });
  $("#upload-paths-btn").onclick = uploadPaths;

  $("#generate-config-btn").onclick = generateConfig;
  $("#save-config-btn").onclick = saveConfig;

  $("#start-session-btn").onclick = startSession;
  $("#finalize-session-btn").onclick = finalizeSession;

  $("#check-prompt-btn").onclick = checkPrompt;
  $("#improve-prompt-btn").onclick = improvePrompt;
  $("#annotate-form").addEventListener("submit", submitAnnotation);

  $("#bbox-save-btn").onclick = saveBboxes;
  $("#bbox-clear-btn").onclick = () => { state.boxes = []; drawBoxes(); };

  $("#coop-train-btn").onclick = trainCoop;
  $("#benchmark-btn").onclick = runBenchmark;
  $("#tour-btn").onclick = startTour;

  await detectOS();
  await loadModels();

  // Restore session if any
  try {
    const r = await api("/annotate/current");
    if (r.session && confirm("Найдена незавершённая сессия. Продолжить?")) {
      state.sessionId = r.session.session_id;
      $("#finalize-session-btn").classList.remove("hidden");
      $("#session-progress").textContent = "Восстановлена сессия " + state.sessionId.slice(0, 8);
    }
  } catch {}
});
