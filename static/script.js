// AutoPrompt Annotator 5.0 — Vue 3 frontend (no build, CDN global build).

const { createApp, reactive, ref, computed, onMounted, onUnmounted, nextTick, watch } = Vue;

const MAX_IMAGES = 20;
const MAX_VIDEOS = 10;

const TABS = [
  { id: "projects",  num: 1, title: "Проекты" },
  { id: "files",     num: 2, title: "Файлы" },
  { id: "models",    num: 3, title: "Модели" },
  { id: "annotate",  num: 4, title: "Разметка" },
  { id: "coop",      num: 5, title: "CoOp / CoCoOp" },
  { id: "benchmark", num: 6, title: "Бенчмарк" },
];

const TOUR_STEPS = [
  { tab: "projects",  text: "Создайте проект — каждый со своими файлами и аннотациями." },
  { tab: "files",     text: "Загрузите изображения/видео в активный проект (до 20 фото и 10 видео)." },
  { tab: "models",    text: "Выберите модель из списка или сгенерируйте YAML через GigaChat." },
  { tab: "annotate",  text: "Размечайте: bbox для детекции, полигон для сегментации, Q&A для VQA." },
  { tab: "coop",      text: "Запустите CoOp/CoCoOp обучение поверх размеченного датасета." },
  { tab: "benchmark", text: "Сравните ответы модели до и после оптимизации." },
];

const PALETTE = ["#ef4444", "#22c55e", "#3b82f6", "#eab308", "#a855f7", "#ec4899", "#14b8a6", "#f97316"];

// ---------- API helper ----------
async function api(path, opts = {}) {
  const init = { headers: {}, ...opts };
  if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = data.detail || data.message || text || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

const fmtTimestamp = (ts) => {
  const h = Math.floor(ts / 3600).toString().padStart(2, "0");
  const m = Math.floor((ts % 3600) / 60).toString().padStart(2, "0");
  const s = Math.floor(ts % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
};
const baseName = (p) => (p || "").replace(/\\/g, "/").split("/").pop();
const colorFor = (idx) => PALETTE[idx % PALETTE.length];

// ---------- root component ----------
const App = {
  setup() {
    const activeTab = ref("projects");
    const os = ref("linux");
    const errorMsg = ref("");
    const noticeMsg = ref("");

    // projects
    const projects = reactive([]);
    const activeProject = ref(localStorage.getItem("active_project") || "default");
    const newProjectName = ref("");
    watch(activeProject, (v) => v && localStorage.setItem("active_project", v));

    // files
    const files = reactive([]);
    const selectedFileId = ref(null);
    const dragOver = ref(false);
    const pathsInput = ref("");
    const fileInput = ref(null);

    // models
    const models = reactive([]);
    const selectedModel = ref(null);
    const modelGuide = ref("");
    const modelMinExamples = ref(null);
    const modelIdInput = ref("");
    const generatedYaml = ref("");
    const saveName = ref("");

    // session / annotation
    const datasetName = ref("dataset");
    const sessionId = ref(null);
    const sessionProgress = ref("");
    const question = ref("");
    const answer = ref("");
    const checkResult = ref(null);

    // shapes (bbox + polygon)
    const shapes = reactive([]);   // [{kind:'bbox'|'polygon', class, x1,y1,x2,y2 OR points:[]}]
    const tool = ref("bbox");      // 'bbox' | 'polygon'
    const drawing = ref(null);     // bbox draft
    const polyDraft = reactive([]); // polygon draft points
    const polyHover = ref(null);   // current mouse position for polygon
    const shapeClass = ref("object");
    const exportFormat = ref("yolo");
    const canvasRef = ref(null);
    const imageRef = ref(null);

    // video
    const videoRef = ref(null);
    const videoTime = ref(0);

    // coop
    const coopType = ref("coop");
    const coopNumVectors = ref(16);
    const coopContextInit = ref("a photo of a");
    const coopRunId = ref(null);
    const coopLog = ref("(пока пусто)");
    let coopTimer = null;

    // benchmark
    const benchQuestions = ref("");
    const benchBefore = ref("");
    const benchAfter = ref("");
    const benchResult = ref("(нет данных)");

    // help / tour
    const helpMode = ref(false);
    const helpTooltip = ref(null);
    const tourIndex = ref(-1);

    const textContent = ref("");

    // ----- computed -----
    const imageCount = computed(() => files.filter(f => f.type === "image").length);
    const videoCount = computed(() => files.filter(f => f.type === "video").length);
    const selectedFile = computed(() =>
      selectedFileId.value != null
        ? files.find(f => f.file_id === selectedFileId.value) : null
    );
    const fileURL = (id) => `/files/${id}`;

    function setError(msg)  { errorMsg.value = msg; setTimeout(() => errorMsg.value = "", 6000); }
    function setNotice(msg) { noticeMsg.value = msg; setTimeout(() => noticeMsg.value = "", 4000); }

    function checkLimits(toUploadList) {
      let img = imageCount.value, vid = videoCount.value;
      for (const f of toUploadList) {
        const ext = (f.name || "").toLowerCase().split(".").pop();
        if (["jpg","jpeg","png","bmp","webp","gif","tif","tiff"].includes(ext)) img++;
        else if (["mp4","avi","mov","mkv","webm","m4v"].includes(ext)) vid++;
      }
      if (img > MAX_IMAGES) return `Превышен лимит изображений (${img}/${MAX_IMAGES}).`;
      if (vid > MAX_VIDEOS) return `Превышен лимит видео (${vid}/${MAX_VIDEOS}).`;
      return null;
    }
    function checkLimitsByPaths(paths) {
      let img = imageCount.value, vid = videoCount.value;
      for (const p of paths) {
        const ext = p.toLowerCase().split(".").pop();
        if (["jpg","jpeg","png","bmp","webp","gif","tif","tiff"].includes(ext)) img++;
        else if (["mp4","avi","mov","mkv","webm","m4v"].includes(ext)) vid++;
      }
      if (img > MAX_IMAGES) return `Превышен лимит изображений (${img}/${MAX_IMAGES}).`;
      if (vid > MAX_VIDEOS) return `Превышен лимит видео (${vid}/${MAX_VIDEOS}).`;
      return null;
    }

    // ----- API -----
    async function detectOS() {
      try { const r = await api("/get_os_type"); os.value = r.os; }
      catch (e) { setError("Не удалось определить ОС: " + e.message); }
    }

    async function loadProjects() {
      try {
        const list = await api("/projects");
        projects.splice(0, projects.length, ...list);
        if (!projects.find(p => p.name === activeProject.value) && projects.length) {
          activeProject.value = projects[0].name;
        }
      } catch (e) { setError("Список проектов: " + e.message); }
    }

    async function createProject() {
      const name = newProjectName.value.trim();
      if (!name) return;
      try {
        const r = await api("/projects", { method: "POST", body: { name } });
        await loadProjects();
        activeProject.value = r.name;
        newProjectName.value = "";
        setNotice("Создан проект: " + r.name);
        // clear current file list when switching
        files.splice(0, files.length);
        selectedFileId.value = null;
      } catch (e) { setError(e.message); }
    }

    async function deleteProject(name) {
      if (!confirm(`Удалить проект «${name}» со всеми файлами и аннотациями?`)) return;
      try {
        await api(`/projects/${encodeURIComponent(name)}`, { method: "DELETE" });
        await loadProjects();
        if (activeProject.value === name) {
          activeProject.value = projects[0]?.name || "default";
          files.splice(0, files.length);
          selectedFileId.value = null;
        }
        setNotice("Проект удалён");
      } catch (e) { setError(e.message); }
    }

    async function selectProject(name) {
      activeProject.value = name;
      files.splice(0, files.length);
      selectedFileId.value = null;
      shapes.splice(0, shapes.length);
      polyDraft.splice(0, polyDraft.length);
      // load existing files for this project
      try {
        const r = await api(`/projects/${encodeURIComponent(name)}/files`);
        for (const f of r.files) files.push(f);
      } catch {}
    }
    watch(activeProject, (v, old) => { if (v && v !== old) selectProject(v); });

    async function loadModels() {
      try {
        const list = await api("/models/list");
        models.splice(0, models.length, ...list);
        if (list.length && !selectedModel.value) selectedModel.value = list[0];
      } catch (e) { setError("Список моделей: " + e.message); }
    }

    async function loadModelInfo() {
      if (!selectedModel.value) return;
      try {
        const g = await api(`/models/soft_prompt_guide/${encodeURIComponent(selectedModel.value)}`);
        modelGuide.value = g.guide || "";
        const m = await api(`/models/min_examples/${encodeURIComponent(selectedModel.value)}`);
        modelMinExamples.value = m.min_examples;
      } catch { modelGuide.value = ""; modelMinExamples.value = null; }
    }
    watch(selectedModel, loadModelInfo);

    // ----- upload -----
    async function uploadFiles(fileList) {
      const list = Array.from(fileList || []);
      if (!list.length) return;
      const err = checkLimits(list);
      if (err) { setError(err); return; }
      const fd = new FormData();
      for (const f of list) fd.append("files", f);
      if (activeProject.value) fd.append("project", activeProject.value);
      try {
        const data = await api("/upload", { method: "POST", body: fd });
        for (const m of data.metadata) files.push(m);
        setNotice(`Загружено: ${data.metadata.length}`);
      } catch (e) { setError("Загрузка не удалась: " + e.message); }
    }

    async function uploadPaths() {
      const paths = pathsInput.value.split("\n").map(s => s.trim()).filter(Boolean);
      if (!paths.length) return;
      const err = checkLimitsByPaths(paths);
      if (err) { setError(err); return; }
      try {
        const data = await api("/upload", {
          method: "POST",
          body: { paths, project: activeProject.value },
        });
        for (const m of data.metadata) files.push(m);
        pathsInput.value = "";
        setNotice(`Загружено: ${data.metadata.length}`);
      } catch (e) { setError("Загрузка не удалась: " + e.message); }
    }

    function pickFiles() { fileInput.value?.click(); }
    function onFileInputChange(e) { uploadFiles(e.target.files); e.target.value = ""; }
    function onDrop(e) {
      e.preventDefault(); dragOver.value = false;
      if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
    }
    function onDragOver(e) { e.preventDefault(); dragOver.value = true; }
    function onDragLeave() { dragOver.value = false; }

    async function removeFile(fileId, opts = {}) {
      if (!opts.skipConfirm && !confirm("Удалить файл из списка и с диска?")) return;
      try { await api(`/files/${fileId}`, { method: "DELETE" }); }
      catch (e) { console.warn("DELETE /files/" + fileId + ": " + e.message); }
      const idx = files.findIndex(f => f.file_id === fileId);
      if (idx !== -1) files.splice(idx, 1);
      if (selectedFileId.value === fileId) {
        selectedFileId.value = null;
        textContent.value = "";
        shapes.splice(0, shapes.length);
      }
      setNotice("Файл удалён");
    }
    async function clearAllFiles() {
      if (!files.length) return;
      if (!confirm(`Удалить все ${files.length} файлов с диска?`)) return;
      const ids = files.map(f => f.file_id);
      for (const id of ids) await removeFile(id, { skipConfirm: true });
    }

    function selectFile(fileId) {
      selectedFileId.value = fileId;
      activeTab.value = "annotate";
      shapes.splice(0, shapes.length);
      drawing.value = null;
      polyDraft.splice(0, polyDraft.length);
      checkResult.value = null;
      const f = files.find(x => x.file_id === fileId);
      if (f?.type === "text") {
        fetch(fileURL(fileId)).then(r => r.text()).then(t => textContent.value = t);
      } else { textContent.value = ""; }
      nextTick(syncCanvasSize);
    }

    // ----- canvas drawing -----
    function syncCanvasSize() {
      const img = imageRef.value, canvas = canvasRef.value;
      if (!img || !canvas) return;
      if (img.complete && img.naturalWidth) {
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;
        drawAll();
      }
    }

    function drawShape(ctx, s, idx, isHover = false) {
      const color = colorFor(idx);
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = isHover ? 3 : 2;
      ctx.setLineDash([]);
      if (s.kind === "bbox") {
        ctx.strokeRect(s.x1, s.y1, s.x2 - s.x1, s.y2 - s.y1);
        const w = ctx.measureText(s.class).width + 8;
        ctx.fillRect(s.x1, s.y1 - 18, w, 18);
        ctx.fillStyle = "white";
        ctx.fillText(s.class, s.x1 + 4, s.y1 - 4);
      } else if (s.kind === "polygon") {
        if (!s.points?.length) return;
        ctx.beginPath();
        ctx.moveTo(s.points[0][0], s.points[0][1]);
        for (let i = 1; i < s.points.length; i++) ctx.lineTo(s.points[i][0], s.points[i][1]);
        ctx.closePath();
        ctx.stroke();
        ctx.save();
        ctx.globalAlpha = 0.18;
        ctx.fill();
        ctx.restore();
        // class label at first point
        const [x, y] = s.points[0];
        const w = ctx.measureText(s.class).width + 8;
        ctx.fillRect(x, y - 18, w, 18);
        ctx.fillStyle = "white";
        ctx.fillText(s.class, x + 4, y - 4);
      }
    }

    function drawAll(hoverIdx = -1) {
      const canvas = canvasRef.value;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.font = "13px sans-serif";
      shapes.forEach((s, i) => drawShape(ctx, s, i, i === hoverIdx));
      // bbox draft
      if (drawing.value) {
        const d = drawing.value;
        ctx.strokeStyle = "#3b82f6";
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(d.x1, d.y1, d.x2 - d.x1, d.y2 - d.y1);
        ctx.setLineDash([]);
      }
      // polygon draft
      if (polyDraft.length) {
        ctx.strokeStyle = "#3b82f6";
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(polyDraft[0][0], polyDraft[0][1]);
        for (let i = 1; i < polyDraft.length; i++) ctx.lineTo(polyDraft[i][0], polyDraft[i][1]);
        if (polyHover.value) ctx.lineTo(polyHover.value[0], polyHover.value[1]);
        ctx.stroke();
        ctx.setLineDash([]);
        // dots
        ctx.fillStyle = "#3b82f6";
        for (const [x, y] of polyDraft) {
          ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
        }
      }
    }

    function onCanvasMouseDown(e) {
      if (tool.value !== "bbox") return;
      const r = canvasRef.value.getBoundingClientRect();
      drawing.value = { x1: e.clientX - r.left, y1: e.clientY - r.top, x2: 0, y2: 0 };
    }
    function onCanvasMouseMove(e) {
      const r = canvasRef.value.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (tool.value === "bbox" && drawing.value) {
        drawing.value.x2 = x; drawing.value.y2 = y;
        drawAll();
      } else if (tool.value === "polygon" && polyDraft.length) {
        polyHover.value = [x, y];
        drawAll();
      }
    }
    function onCanvasMouseUp() {
      if (tool.value !== "bbox" || !drawing.value) return;
      const d = drawing.value;
      if (Math.abs(d.x2 - d.x1) > 4 && Math.abs(d.y2 - d.y1) > 4) {
        shapes.push({
          kind: "bbox",
          class: shapeClass.value || "object",
          x1: d.x1, y1: d.y1, x2: d.x2, y2: d.y2,
        });
      }
      drawing.value = null;
      drawAll();
    }
    function onCanvasClick(e) {
      if (tool.value !== "polygon") return;
      const r = canvasRef.value.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      // close on click near first point
      if (polyDraft.length >= 3) {
        const [fx, fy] = polyDraft[0];
        if (Math.hypot(x - fx, y - fy) < 10) {
          finishPolygon();
          return;
        }
      }
      polyDraft.push([x, y]);
      drawAll();
    }
    function onCanvasDblClick() {
      if (tool.value === "polygon") finishPolygon();
    }

    function finishPolygon() {
      if (polyDraft.length < 3) {
        polyDraft.splice(0, polyDraft.length);
        polyHover.value = null;
        drawAll();
        return;
      }
      shapes.push({
        kind: "polygon",
        class: shapeClass.value || "object",
        points: polyDraft.map(p => [...p]),
      });
      polyDraft.splice(0, polyDraft.length);
      polyHover.value = null;
      drawAll();
    }

    function cancelPolygon() {
      polyDraft.splice(0, polyDraft.length);
      polyHover.value = null;
      drawAll();
    }

    function removeShape(idx) {
      shapes.splice(idx, 1);
      drawAll();
    }
    function clearShapes() {
      if (!shapes.length) return;
      if (!confirm(`Удалить все ${shapes.length} слоёв?`)) return;
      shapes.splice(0, shapes.length);
      drawAll();
    }
    function highlightShape(idx) { drawAll(idx); }
    function unhighlight() { drawAll(); }

    async function saveShapes() {
      if (!selectedFile.value || !shapes.length) return setError("Нет слоёв для сохранения.");
      const img = imageRef.value;
      const sx = img.naturalWidth / img.clientWidth;
      const sy = img.naturalHeight / img.clientHeight;
      const exportShapes = shapes.map(s => {
        if (s.kind === "polygon") {
          return { class: s.class, points: s.points.map(([x, y]) => [Math.round(x * sx), Math.round(y * sy)]) };
        }
        return {
          class: s.class,
          x1: Math.round(s.x1 * sx), y1: Math.round(s.y1 * sy),
          x2: Math.round(s.x2 * sx), y2: Math.round(s.y2 * sy),
        };
      });
      try {
        const r = await api("/image/shapes/save", {
          method: "POST",
          body: {
            file_id: selectedFile.value.file_id,
            format: exportFormat.value,
            shapes: exportShapes,
            project: activeProject.value,
          },
        });
        setNotice(`Сохранено: ${r.annotation_file} (${r.count})`);
      } catch (e) { setError(e.message); }
    }

    // ----- video -----
    function videoCurrentTime() { return videoRef.value?.currentTime || 0; }
    function insertTimestamp() {
      if (!videoRef.value) return;
      videoTime.value = videoRef.value.currentTime;
      setNotice("Текущий таймкод: " + fmtTimestamp(videoRef.value.currentTime));
    }
    async function exportVideoTimestamp() {
      if (!selectedFile.value) return;
      const bitrate = prompt("Битрейт (например, 2M, пусто = по умолчанию)", "");
      const useGpu = confirm("Использовать GPU (NVENC, только Linux)?");
      try {
        const r = await api("/video/burn_timestamp", {
          method: "POST",
          body: {
            file_id: selectedFile.value.file_id,
            bitrate: bitrate || null, use_gpu: useGpu,
            project: activeProject.value,
          },
        });
        setNotice("Готово, файл #" + r.file_id);
        window.open(r.exported_url, "_blank");
      } catch (e) { setError(e.message); }
    }

    // ----- model config -----
    async function generateConfig() {
      if (!modelIdInput.value.trim()) return;
      try {
        const r = await api("/models/generate_config", {
          method: "POST", body: { model_identifier: modelIdInput.value.trim() },
        });
        if (r.error) {
          generatedYaml.value = `# error: ${r.error}\n# fallback prompt:\n# ${r.fallback_prompt}\n\n${r.example_yaml || ""}`;
          setError(r.error);
        } else {
          generatedYaml.value = r.yaml;
          setNotice("Конфиг сгенерирован.");
        }
      } catch (e) { setError(e.message); }
    }
    async function saveConfig() {
      if (!saveName.value.trim() || !generatedYaml.value.trim()) return setError("Укажите имя и YAML.");
      try {
        await api("/models/save_config", {
          method: "POST", body: { name: saveName.value.trim(), yaml: generatedYaml.value },
        });
        await loadModels();
        selectedModel.value = saveName.value.trim();
        setNotice("Сохранено: " + saveName.value);
      } catch (e) { setError(e.message); }
    }

    // ----- session -----
    async function startSession() {
      if (!files.length) return setError("Сначала загрузите файлы.");
      if (!selectedModel.value) return setError("Выберите модель.");
      try {
        const r = await api("/annotate/start", {
          method: "POST",
          body: {
            dataset_name: datasetName.value || "dataset",
            model_name: selectedModel.value,
            file_ids: files.map(f => f.file_id),
            project: activeProject.value,
          },
        });
        sessionId.value = r.session_id;
        sessionProgress.value = `0/${files.length}`;
        if (files.length) selectFile(files[0].file_id);
        setNotice("Сессия начата.");
      } catch (e) { setError(e.message); }
    }
    async function checkPrompt() {
      if (!selectedModel.value) return setError("Выберите модель.");
      try {
        const r = await api("/check_prompt_giga", {
          method: "POST",
          body: { question: question.value, answer: answer.value, model_name: selectedModel.value },
        });
        checkResult.value = r;
      } catch (e) { setError(e.message); }
    }
    async function improvePrompt() {
      if (!selectedModel.value) return setError("Выберите модель.");
      try {
        const r = await api("/improve_prompt_giga", {
          method: "POST",
          body: { question: question.value, model_name: selectedModel.value },
        });
        question.value = r.improved_question;
      } catch (e) { setError(e.message); }
    }
    async function submitAnnotation(e) {
      e.preventDefault();
      if (!sessionId.value) return setError("Сначала начните сессию.");
      const body = {
        session_id: sessionId.value,
        question: question.value,
        answer: answer.value,
      };
      if (selectedFile.value?.type === "video") body.timestamp = videoCurrentTime();
      try {
        const r = await api("/save_annotation", { method: "POST", body });
        sessionProgress.value = r.progress;
        question.value = ""; answer.value = "";
        try {
          const next = await api("/annotate/next", { method: "POST", body: { session_id: sessionId.value } });
          if (next.file_id != null) selectFile(next.file_id);
        } catch {
          setNotice("Все файлы размечены — нажмите «Завершить».");
        }
      } catch (err) { setError(err.message); }
    }
    async function finalizeSession() {
      if (!sessionId.value) return;
      try {
        const r = await api("/annotate/finalize", { method: "POST", body: { session_id: sessionId.value } });
        setNotice("Датасет: " + r.dataset_path);
        sessionId.value = null;
        sessionProgress.value = "";
      } catch (e) { setError(e.message); }
    }

    // ----- coop -----
    async function trainCoop() {
      if (!selectedModel.value) return setError("Выберите модель.");
      try {
        const r = await api("/coop/train", {
          method: "POST",
          body: {
            model_name: selectedModel.value,
            dataset_name: datasetName.value || "dataset",
            coop_type: coopType.value,
            num_vectors: +coopNumVectors.value,
            context_init: coopContextInit.value,
            class_token_position: "end",
            net_depth: 3,
          },
        });
        coopRunId.value = r.run_id;
        coopLog.value = `Запущено: ${r.run_id}\noutput_dir: ${r.output_dir}\n`;
        if (coopTimer) clearTimeout(coopTimer);
        pollCoop();
      } catch (e) { setError(e.message); }
    }
    async function pollCoop() {
      if (!coopRunId.value) return;
      try {
        const r = await api(`/coop/status/${coopRunId.value}`);
        coopLog.value = `[${r.status}]\n${r.log}`;
        if (r.status === "running") coopTimer = setTimeout(pollCoop, 1500);
      } catch (e) { coopLog.value = "ошибка: " + e.message; }
    }

    // ----- benchmark -----
    async function runBenchmark() {
      const split = (s) => s.split("\n").map(x => x.trim()).filter(Boolean);
      try {
        const r = await api("/benchmark/compare", {
          method: "POST",
          body: {
            model_name: selectedModel.value,
            questions: split(benchQuestions.value),
            answers_before: split(benchBefore.value),
            answers_after: split(benchAfter.value),
          },
        });
        benchResult.value = JSON.stringify(r, null, 2);
      } catch (e) { setError(e.message); }
    }

    // ----- help / tour -----
    function toggleHelpMode() {
      helpMode.value = !helpMode.value;
      if (!helpMode.value) helpTooltip.value = null;
    }
    async function showHelpFor(selector, e) {
      if (!helpMode.value) return;
      e.preventDefault(); e.stopPropagation();
      try {
        const data = await api("/help/" + encodeURIComponent(selector));
        helpTooltip.value = { ...data, x: e.clientX + 14, y: e.clientY + 14 };
      } catch {}
    }
    function startTour() { tourIndex.value = 0; activeTab.value = TOUR_STEPS[0].tab; }
    function nextTour() {
      tourIndex.value++;
      if (tourIndex.value >= TOUR_STEPS.length) tourIndex.value = -1;
      else activeTab.value = TOUR_STEPS[tourIndex.value].tab;
    }
    function closeTour() { tourIndex.value = -1; }

    // ----- lifecycle -----
    onMounted(async () => {
      await detectOS();
      await loadProjects();
      await selectProject(activeProject.value);
      await loadModels();
      await loadModelInfo();
      try {
        const r = await api(`/annotate/current?project=${encodeURIComponent(activeProject.value)}`);
        if (r.session && confirm("Найдена незавершённая сессия. Продолжить?")) {
          sessionId.value = r.session.session_id;
          datasetName.value = r.session.dataset_name;
          sessionProgress.value = `${(r.session.annotations || []).length}/${(r.session.files || []).length}`;
        }
      } catch {}
      window.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          helpMode.value = false; helpTooltip.value = null; tourIndex.value = -1;
          if (tool.value === "polygon") cancelPolygon();
        }
      });
    });
    onUnmounted(() => { if (coopTimer) clearTimeout(coopTimer); });

    function onImageLoad() { syncCanvasSize(); }

    return {
      // constants
      TABS, TOUR_STEPS, MAX_IMAGES, MAX_VIDEOS, baseName, fmtTimestamp, fileURL, colorFor,
      // state
      activeTab, os, errorMsg, noticeMsg,
      projects, activeProject, newProjectName,
      files, selectedFile, selectedFileId, dragOver, pathsInput, fileInput,
      models, selectedModel, modelGuide, modelMinExamples,
      modelIdInput, generatedYaml, saveName,
      datasetName, sessionId, sessionProgress, question, answer, checkResult,
      shapes, tool, shapeClass, exportFormat, polyDraft,
      canvasRef, imageRef,
      videoRef, videoTime,
      coopType, coopNumVectors, coopContextInit, coopRunId, coopLog,
      benchQuestions, benchBefore, benchAfter, benchResult,
      helpMode, helpTooltip, tourIndex,
      textContent,
      // computed
      imageCount, videoCount,
      // methods
      createProject, deleteProject, selectProject,
      pickFiles, onFileInputChange, onDrop, onDragOver, onDragLeave,
      uploadPaths, removeFile, clearAllFiles, selectFile,
      onCanvasMouseDown, onCanvasMouseMove, onCanvasMouseUp,
      onCanvasClick, onCanvasDblClick, finishPolygon, cancelPolygon,
      removeShape, clearShapes, highlightShape, unhighlight, saveShapes,
      insertTimestamp, exportVideoTimestamp,
      generateConfig, saveConfig,
      startSession, checkPrompt, improvePrompt, submitAnnotation, finalizeSession,
      trainCoop, runBenchmark,
      toggleHelpMode, showHelpFor, startTour, nextTour, closeTour,
      onImageLoad,
      tourStep: computed(() => tourIndex.value >= 0 ? TOUR_STEPS[tourIndex.value] : null),
    };
  },

  template: /* html */ `
  <div class="app" :class="{ 'help-mode': helpMode }">
    <header>
      <div class="header-top">
        <div class="brand"><h1>AutoPrompt Annotator<span class="v">5.0</span></h1></div>
        <div class="status-line">
          <span class="chip">ОС: <strong>{{ os }}</strong></span>
          <span class="chip ok">Проект: <strong>{{ activeProject || '—' }}</strong></span>
          <span class="chip" :class="{ ok: selectedModel }">Модель: <strong>{{ selectedModel || '—' }}</strong></span>
          <span class="chip" :class="{ ok: sessionId }">Сессия: <strong>{{ sessionId ? sessionId.slice(0,8) : 'нет' }}</strong></span>
          <span v-if="sessionProgress" class="chip">{{ sessionProgress }}</span>
        </div>
        <div class="header-actions">
          <button class="ghost" id="tour-btn" @click="startTour">Тур</button>
          <button class="ghost" id="help-btn" @click="toggleHelpMode">{{ helpMode ? '✕' : '?' }}</button>
        </div>
      </div>
      <nav class="tabs">
        <button v-for="t in TABS" :key="t.id" class="tab"
                :class="{ active: activeTab === t.id }" @click="activeTab = t.id">
          <span class="num">{{ t.num }}</span>{{ t.title }}
        </button>
      </nav>
    </header>

    <main>
      <div v-if="errorMsg" class="error-banner">⚠ {{ errorMsg }}</div>
      <div v-if="noticeMsg" class="notice">{{ noticeMsg }}</div>

      <!-- ====== PROJECTS ====== -->
      <div v-show="activeTab === 'projects'">
        <div class="grid cols-2">
          <div class="card">
            <h2>Создать проект</h2>
            <p class="hint">Каждый проект изолирован: свои <code>uploads/</code>,
              <code>annotations/</code>, <code>sessions/</code>, <code>datasets/</code>.</p>
            <label>Имя проекта:</label>
            <div class="row">
              <input v-model="newProjectName" class="grow" placeholder="кошки_2024"
                     @keyup.enter="createProject">
              <button @click="createProject" class="success">Создать</button>
            </div>
            <p class="hint">Допустимо: буквы (RU/EN), цифры, пробел, дефис, подчёркивание.</p>
          </div>

          <div class="card">
            <h2>Существующие проекты <span class="badge-pill">{{ projects.length }}</span></h2>
            <ul class="project-list">
              <li v-for="p in projects" :key="p.name"
                  class="project-row"
                  :class="{ active: p.name === activeProject }">
                <div class="project-info">
                  <strong>{{ p.name }}</strong>
                  <span class="muted small">{{ p.files }} файлов в uploads/</span>
                </div>
                <div class="row">
                  <button class="secondary" @click="activeProject = p.name"
                          :disabled="p.name === activeProject">
                    {{ p.name === activeProject ? 'Активен' : 'Сделать активным' }}
                  </button>
                  <button class="danger" @click="deleteProject(p.name)" title="Удалить проект">×</button>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- ====== FILES ====== -->
      <div v-show="activeTab === 'files'">
        <div class="grid cols-2">
          <div class="card">
            <h2>Загрузка в проект «{{ activeProject }}»</h2>
            <p class="hint" v-if="os === 'windows'">Windows: drag&drop или кликните область.</p>
            <p class="hint" v-else>Linux: drag&drop работает; также можно ввести абсолютные пути.</p>

            <div id="upload-area" class="dropzone" :class="{ dragover: dragOver }"
                 @click="pickFiles" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
                 @click.capture="showHelpFor('#upload-area', $event)">
              <div class="big">⬆</div>
              <div>Перетащите файлы или кликните</div>
              <div class="muted small">видео, изображения, текст</div>
              <input type="file" ref="fileInput" multiple
                     accept="image/*,video/*,.txt,.md,.json,.csv,.log"
                     @change="onFileInputChange">
            </div>

            <div v-if="os === 'linux'" style="margin-top: 12px;">
              <label>Пути (по одному на строку):</label>
              <textarea v-model="pathsInput" rows="3"
                        placeholder="/home/user/data/img.jpg"></textarea>
              <button @click="uploadPaths">Загрузить пути</button>
            </div>

            <div class="limits">
              <div class="limit-bar"
                   :class="{ warn: imageCount >= MAX_IMAGES * 0.8, full: imageCount >= MAX_IMAGES }">
                <div class="label">Изображения</div>
                <div class="num">{{ imageCount }} / {{ MAX_IMAGES }}</div>
                <div class="progress"><div :style="{ width: (imageCount / MAX_IMAGES * 100) + '%' }"></div></div>
              </div>
              <div class="limit-bar"
                   :class="{ warn: videoCount >= MAX_VIDEOS * 0.8, full: videoCount >= MAX_VIDEOS }">
                <div class="label">Видео</div>
                <div class="num">{{ videoCount }} / {{ MAX_VIDEOS }}</div>
                <div class="progress"><div :style="{ width: (videoCount / MAX_VIDEOS * 100) + '%' }"></div></div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="row between" style="margin-bottom: 8px;">
              <h2 style="margin: 0;">Файлы проекта <span class="badge-pill">{{ files.length }}</span></h2>
              <button v-if="files.length" class="ghost" @click="clearAllFiles">Очистить всё</button>
            </div>
            <p class="hint">Кнопка <b>×</b> удаляет файл с диска.</p>
            <div v-if="!files.length" class="muted" style="text-align:center; padding: 30px;">
              Ещё ничего не загружено
            </div>
            <ul class="file-list">
              <li v-for="f in files" :key="f.file_id" class="file-card"
                  :class="{ selected: selectedFileId === f.file_id }"
                  @click="selectFile(f.file_id)">
                <div class="badge">{{ f.type }}</div>
                <button class="remove" @click.stop="removeFile(f.file_id)" title="Удалить">×</button>
                <div class="thumb">
                  <img v-if="f.type === 'image'" :src="fileURL(f.file_id)" alt="">
                  <video v-else-if="f.type === 'video'" :src="fileURL(f.file_id)" muted preload="metadata"></video>
                  <span v-else class="placeholder">📄</span>
                </div>
                <div class="meta">{{ baseName(f.path) }}</div>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- ====== MODELS ====== -->
      <div v-show="activeTab === 'models'">
        <div class="grid cols-2">
          <div class="card">
            <h2>Существующая</h2>
            <label>Из <code>models/configs/</code>:</label>
            <select v-model="selectedModel" id="model-select"
                    @click.capture="showHelpFor('#model-select', $event)">
              <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
            </select>
            <div class="row">
              <span class="hint">Минимум примеров:</span>
              <span class="badge-pill">{{ modelMinExamples ?? '—' }}</span>
            </div>
            <label>Soft prompt guide:</label>
            <pre class="log">{{ modelGuide || '(нет данных)' }}</pre>
          </div>
          <div class="card">
            <h2>Сгенерировать через GigaChat</h2>
            <input v-model="modelIdInput" placeholder="например, Qwen2-VL-7B">
            <button @click="generateConfig">Сгенерировать конфиг</button>
            <textarea v-model="generatedYaml" rows="9" placeholder="YAML появится здесь"></textarea>
            <div class="row">
              <input v-model="saveName" class="grow" placeholder="имя_модели">
              <button @click="saveConfig" class="success">Сохранить</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ====== ANNOTATE ====== -->
      <div v-show="activeTab === 'annotate'">
        <div class="card">
          <div class="row between">
            <div class="row" style="flex: 1;">
              <label style="margin: 0;">Датасет:</label>
              <input v-model="datasetName" style="width: 200px; margin: 0;">
            </div>
            <button v-if="!sessionId" @click="startSession">Начать разметку</button>
            <button v-if="sessionId" @click="finalizeSession" class="secondary">Завершить</button>
          </div>
        </div>

        <div class="grid annotate">
          <div class="card">
            <h2>Просмотр {{ selectedFile ? '— ' + baseName(selectedFile.path) : '' }}</h2>
            <div class="viewer" id="viewer">
              <template v-if="selectedFile">
                <video v-if="selectedFile.type === 'video'" ref="videoRef"
                       :key="selectedFile.file_id" :src="fileURL(selectedFile.file_id)" controls></video>
                <div v-else-if="selectedFile.type === 'image'" class="image-wrap">
                  <img ref="imageRef" :key="selectedFile.file_id"
                       :src="fileURL(selectedFile.file_id)" @load="onImageLoad" alt="">
                  <canvas id="bbox-canvas" ref="canvasRef"
                          :class="{ poly: tool === 'polygon' }"
                          @mousedown="onCanvasMouseDown"
                          @mousemove="onCanvasMouseMove"
                          @mouseup="onCanvasMouseUp"
                          @mouseleave="onCanvasMouseUp"
                          @click="onCanvasClick"
                          @dblclick="onCanvasDblClick"></canvas>
                </div>
                <pre v-else-if="selectedFile.type === 'text'" class="text">{{ textContent }}</pre>
                <div v-else class="empty">Неизвестный тип файла.</div>
              </template>
              <div v-else class="empty">
                <div class="icon">📂</div>Выберите файл на вкладке «Файлы».
              </div>
            </div>

            <div v-if="selectedFile?.type === 'video'" class="tool-row">
              <button id="timestamp-btn" @click="insertTimestamp">Вставить время</button>
              <button id="export-video-btn" @click="exportVideoTimestamp">Экспорт с таймкодом</button>
              <span class="label">{{ fmtTimestamp(videoTime) }}</span>
            </div>

            <div v-if="selectedFile?.type === 'image'" class="tool-row">
              <span class="label">Инструмент:</span>
              <select v-model="tool" style="flex: 0 1 130px;">
                <option value="bbox">📦 BBox</option>
                <option value="polygon">⬡ Полигон (сегментация)</option>
              </select>
              <span class="label">Класс:</span>
              <input v-model="shapeClass" style="flex: 0 1 120px;">
              <span class="label">Формат:</span>
              <select v-model="exportFormat" style="flex: 0 1 110px;">
                <option value="yolo">YOLO</option>
                <option value="coco">COCO</option>
                <option value="voc">Pascal VOC</option>
              </select>
              <button @click="saveShapes" class="success">Сохранить ({{ shapes.length }})</button>
              <button v-if="tool === 'polygon' && polyDraft.length"
                      @click="finishPolygon" class="secondary">Закрыть полигон</button>
              <button v-if="tool === 'polygon' && polyDraft.length"
                      @click="cancelPolygon" class="ghost">Отмена</button>
            </div>
            <p v-if="selectedFile?.type === 'image' && tool === 'polygon'" class="hint">
              Кликайте, чтобы добавлять точки. Двойной клик или клик по первой точке — закрыть полигон. ESC — отменить.
            </p>
          </div>

          <div class="card">
            <h2>Слои <span class="badge-pill">{{ shapes.length }}</span></h2>
            <p v-if="!shapes.length" class="hint">Нарисуйте bbox или полигон на изображении.</p>
            <ul class="layer-list">
              <li v-for="(s, i) in shapes" :key="i" class="layer-row"
                  @mouseenter="highlightShape(i)" @mouseleave="unhighlight()">
                <span class="layer-color" :style="{ background: colorFor(i) }"></span>
                <span class="layer-info">
                  <strong>{{ s.kind === 'polygon' ? '⬡' : '□' }} {{ s.class }}</strong>
                  <span class="muted small">
                    {{ s.kind === 'polygon' ? s.points.length + ' точек' :
                       Math.round(Math.abs(s.x2-s.x1)) + '×' + Math.round(Math.abs(s.y2-s.y1)) }}
                  </span>
                </span>
                <button class="danger small-btn" @click="removeShape(i)" title="Удалить слой">×</button>
              </li>
            </ul>
            <button v-if="shapes.length" @click="clearShapes" class="ghost"
                    style="width: 100%; margin-top: 10px;">Удалить все слои</button>

            <h2 style="margin-top: 18px;">Q&A</h2>
            <form id="annotate-form" @submit="submitAnnotation">
              <textarea v-model="question" rows="2" placeholder="Вопрос"></textarea>
              <textarea v-model="answer" rows="2" placeholder="Ответ"></textarea>
              <div class="row">
                <button type="button" class="secondary" @click="checkPrompt">Проверить</button>
                <button type="button" class="secondary" @click="improvePrompt">Улучшить</button>
              </div>
              <div v-if="checkResult" class="check-result"
                   :class="{ ok: checkResult.valid, bad: !checkResult.valid }">
                <strong>{{ checkResult.valid ? '✓ ОК' : '⚠ Замечания' }}</strong>
                <div v-if="checkResult.message">{{ checkResult.message }}</div>
              </div>
              <button type="submit" class="success" style="width: 100%;" :disabled="!sessionId">
                Сохранить и далее →
              </button>
            </form>
          </div>
        </div>
      </div>

      <!-- ====== COOP ====== -->
      <div v-show="activeTab === 'coop'">
        <div class="grid cols-2">
          <div class="card">
            <h2>Параметры</h2>
            <label>Тип:</label>
            <select v-model="coopType">
              <option value="coop">CoOp</option>
              <option value="cocoop">CoCoOp</option>
            </select>
            <label>num_vectors:</label>
            <input type="number" v-model.number="coopNumVectors" min="1" max="64">
            <label>context_init:</label>
            <input v-model="coopContextInit">
            <button id="coop-train-btn" @click="trainCoop">Запустить</button>
            <p v-if="coopRunId" class="hint">run_id: <code>{{ coopRunId }}</code></p>
          </div>
          <div class="card">
            <h2>Лог</h2>
            <pre class="log">{{ coopLog }}</pre>
          </div>
        </div>
      </div>

      <!-- ====== BENCHMARK ====== -->
      <div v-show="activeTab === 'benchmark'">
        <div class="grid cols-2">
          <div class="card">
            <h2>Входные данные</h2>
            <textarea v-model="benchQuestions" rows="4" placeholder="вопросы"></textarea>
            <textarea v-model="benchBefore" rows="4" placeholder="ответы ДО"></textarea>
            <textarea v-model="benchAfter" rows="4" placeholder="ответы ПОСЛЕ"></textarea>
            <button id="benchmark-btn" @click="runBenchmark">Сравнить</button>
          </div>
          <div class="card">
            <h2>Результат</h2>
            <pre class="log">{{ benchResult }}</pre>
          </div>
        </div>
      </div>
    </main>

    <div v-if="helpTooltip" id="help-tooltip"
         :style="{ left: helpTooltip.x + 'px', top: helpTooltip.y + 'px' }">
      <b>{{ helpTooltip.title }}</b><br>{{ helpTooltip.description }}
      <div v-if="helpTooltip.example" class="muted small" style="margin-top: 6px;"><i>{{ helpTooltip.example }}</i></div>
    </div>

    <div v-if="tourStep" class="modal-overlay" @click.self="closeTour">
      <div class="modal">
        <h3>Шаг {{ tourIndex + 1 }} из {{ TOUR_STEPS.length }}</h3>
        <p>{{ tourStep.text }}</p>
        <p class="muted small">Вкладка: <code>{{ tourStep.tab }}</code></p>
        <div class="row" style="margin-top: 16px; justify-content: flex-end;">
          <button class="secondary" @click="closeTour">Закрыть</button>
          <button @click="nextTour">{{ tourIndex === TOUR_STEPS.length - 1 ? 'Готово' : 'Далее →' }}</button>
        </div>
      </div>
    </div>
  </div>
  `,
};

createApp(App).mount("#app");
