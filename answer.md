# AutoPrompt Annotator 5.0 — журнал реализации

## 1. Что сделано (в порядке появления)

- [x] Скелет проекта (директории, `requirements.txt`, `__init__.py`, `external.py` мок).
- [x] `core/data_router.py` — определение типа, метаданные через **ffprobe** (главный путь) с fallback в cv2; кэш с TTL.
- [x] `core/prompt_checker.py` — локальная проверка Q&A.
- [x] `core/time_overlay.py` — async FFmpeg drawtext, NVENC опционально.
- [x] `models/model_registry.py` + Pydantic `ModelConfig` + примеры `Video-XL-2.yml`, `CLIP-ViT.yml`.
- [x] `gigachat/{client,prompts}.py` — обёртки над моком `external.gigachat_request`.
- [x] `annotation/` — bbox + polygon экспорт в YOLO/COCO/VOC; **загрузка обратно** с диска.
- [x] `optimization/{prompt_generator,coop_trainer}.py` + шаблоны (заглушки).
- [x] `benchmark/{local_metrics,comparator}.py` — accuracy + macro F1 + GigaChat-отчёт.
- [x] `core/session_store.py` — JSON-сессии, **project-aware**.
- [x] `guides/help_data.py` — словарь подсказок.
- [x] `app.py` — FastAPI, **все 21 эндпоинт** + `/projects/*`, `/image/shapes/*`, `/projects/{name}/rescan`, `DELETE /files/{id}`.
- [x] Vue 3 фронтенд (CDN/локальный билд), тёмная тема, табы в шапке.
- [x] **Проекты**: изоляция `storage/projects/<name>/{uploads,annotations,sessions,datasets,exports}`.
- [x] **Drag & resize bboxes**, **drag вершин полигонов**, **per-file сохранение разметки**.
- [x] **Авто-отображение существующей разметки** при открытии изображения.
- [x] **Подгрузка файлов с диска** (rescan) — переживает рестарт сервера.
- [x] **Переименование классов** в слоях + bulk-rename + dropdown ранее использованных классов.
- [x] **Галерея слева** на вкладке «Разметка», навигация ←/→.
- [x] Поддержка `APP_ROOT_PATH` для прокси (JupyterHub) + относительные пути на фронте.

---

## 2. Архитектура хранения

```
storage/
└── projects/
    └── <project_name>/
        ├── uploads/       исходные файлы (img/video/text)
        ├── annotations/   bbox + polygon экспорт (.txt YOLO, .json COCO, .xml VOC, classes.txt)
        ├── datasets/      финализированные .jsonl с Q&A
        ├── sessions/      открытые сессии разметки <session_id>.json
        ├── exports/       видео с вшитым таймкодом
        └── coop_outputs/  результаты обучения CoOp/CoCoOp (зарезервировано)
```

- `_uploaded_files: dict[int, {path, project}]` — реестр в памяти. Ключ — file_id.
- При рестарте сервера реестр пуст → используйте кнопку **«⟳ С диска»** или эндпоинт `POST /projects/{name}/rescan` — он подцепит всё, что лежит в `<project>/uploads/`, и заново зарегистрирует.

---

## 3. Бэкенд API (изменения и новые эндпоинты)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/projects` | Список проектов и счётчик файлов в каждом. |
| POST | `/projects` | `{name}` — создать проект. |
| DELETE | `/projects/{name}` | Удалить проект целиком (с диска и реестра). |
| GET | `/projects/{name}/files` | Файлы, **уже зарегистрированные** в памяти. |
| POST | `/projects/{name}/rescan` | Сканирует `<project>/uploads/` и регистрирует новые. |
| POST | `/upload` | Принимает multipart **или** JSON с путями. Опц. `project`. |
| GET | `/files/{id}` | Отдаёт файл по file_id. |
| DELETE | `/files/{id}` | Удаляет файл из реестра + с диска (если в managed-uploads). |
| POST | `/image/shapes/save` | Унифицированный сейв bbox+polygon в YOLO/COCO/VOC. |
| GET | `/image/shapes/{id}?project=...` | **Читает существующую разметку** обратно (priority: COCO > VOC > YOLO). |

Координаты в API — **в пикселях оригинального изображения** (image-natural), не в координатах canvas.

---

## 4. Подключение реальных компонентов вместо заглушек

### 4.1. GigaChat — `external.py`

Сейчас `external.gigachat_request(prompt, system_prompt, timeout)` — **мок**, возвращает синтетические ответы по подстроке системного промпта. Замените файл реальным клиентом, **сохранив сигнатуру**:

```python
# external.py
import asyncio
import os
import ssl
import httpx

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_AUTH = os.environ["GIGACHAT_AUTH_KEY"]   # base64(Client ID:Client Secret)
GIGACHAT_SCOPE = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_CERT_BUNDLE = os.environ.get("GIGACHAT_CERT_BUNDLE", "russian_trusted_root_ca.crt")

_token_cache = {"value": None, "expires_at": 0.0}

async def _get_token() -> str:
    import time, uuid
    if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["value"]
    async with httpx.AsyncClient(verify=GIGACHAT_CERT_BUNDLE, timeout=30) as cli:
        r = await cli.post(
            GIGACHAT_AUTH_URL,
            headers={
                "Authorization": f"Basic {GIGACHAT_AUTH}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"scope": GIGACHAT_SCOPE},
        )
        r.raise_for_status()
        body = r.json()
        _token_cache["value"] = body["access_token"]
        _token_cache["expires_at"] = body["expires_at"] / 1000
        return _token_cache["value"]

async def gigachat_request(prompt: str, system_prompt: str, timeout: float = 30.0) -> str:
    token = await _get_token()
    async with httpx.AsyncClient(verify=GIGACHAT_CERT_BUNDLE, timeout=timeout) as cli:
        r = await cli.post(
            GIGACHAT_API_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
```

**Шаги:**
1. Получите Client ID/Secret в [Developers GigaChat](https://developers.sber.ru/portal/products/gigachat-api).
2. Скачайте корневой сертификат Минцифры РФ (обычно `russian_trusted_root_ca.crt`).
3. Установите ENV: `GIGACHAT_AUTH_KEY=<base64(client_id:client_secret)>`, `GIGACHAT_CERT_BUNDLE=/path/to/ca.crt`, опц. `GIGACHAT_SCOPE=GIGACHAT_API_PERS|GIGACHAT_API_CORP`.
4. Запустите сервис — наши обёртки в `gigachat/client.py` сами вызывают `external.gigachat_request` без изменений.
5. Для отладки запросов проверяйте `gigachat/prompts.py` — это все system_prompt-ы.

### 4.2. CoOp / CoCoOp — `optimization/templates/*.py`

Сейчас `coop_video_llm.py` и `cocoop_clip.py` — **stubs**, имитируют 4–5 эпох (sleep + лог) и пишут фейковый `prompt_vectors.bin`.

Чтобы поставить реальное обучение:

1. Установите PyTorch + CLIP/Open-CLIP:
   ```bash
   pip install torch torchvision open-clip-torch
   ```

2. Замените содержимое `optimization/templates/cocoop_clip.py` (или сделайте новый файл) на реализацию из официального репо:
   - **CoOp**: https://github.com/KaiyangZhou/CoOp — каноничная PyTorch-реализация под MMCV/Dassl. Файл `trainers/coop.py`.
   - **CoCoOp**: тот же репо, `trainers/cocoop.py`.
   - Plug-in вариант (без Dassl): https://github.com/Maxsxie/CoOp-CoCoOP

3. Шаблон должен принимать те же placeholder-ы, что и stub:
   ```
   __DATASET_PATH__   путь к JSONL датасету ({"q":..., "a":..., "file_path":...})
   __OUTPUT_DIR__     куда писать train.log, prompt_vectors.bin, metrics.json
   __NUM_VECTORS__    сколько обучаемых токенов M (обычно 16)
   __CONTEXT_INIT__   "a photo of a" или другая строка инициализации
   __CLASS_TOKEN_POSITION__  end | front | middle
   __NET_DEPTH__      глубина Meta-Net (только CoCoOp)
   ```
   Подстановка делается в `optimization/prompt_generator.py` (str.replace).

4. Реализация должна на выходе сгенерировать:
   - `prompt_vectors.bin` или `.pt` — тензор обученных контекстных эмбеддингов;
   - `metrics.json` — `{"final_loss": ..., "final_accuracy": ..., "epochs": N}`;
   - регулярно писать прогресс в stdout (захватывается в `train.log`).

5. `optimization/coop_trainer.py` запускает скрипт через `asyncio.create_subprocess_exec(sys.executable, script_path, ...)` — управление процессом, статусы и логи уже работают **по-настоящему**, менять их не нужно.

6. `apply_learned_prompt(model_config, prompt_vectors_path)` — сейчас stub, который только пишет в лог. Чтобы реально применять веса:
   - Загрузите `prompt_vectors.bin` через `torch.load`;
   - Зарегистрируйте контекстный модуль в инференс-pipeline вашей модели;
   - Для CLIP — замените текстовые эмбеддинги обученными контекстными векторами + class token;
   - Для VLM — добавьте обучаемые токены в начало текстового промпта.

### 4.3. Видео-метаданные

`core/data_router.py::get_video_metadata` сейчас:
1. Пробует `ffprobe` (рекомендуется) — даёт duration, fps, bitrate, video/audio codec.
2. Fallback на `cv2.VideoCapture` (без audio_codec).
3. Если оба не доступны — возвращает пустые поля + `probe_error`.

В закрытом контуре часто проще установить только FFmpeg (без OpenCV), чем тащить numpy/cv2. **FFmpeg обязателен** для экспорта видео с таймкодом (см. ТЗ §15).

---

## 5. Документация по CoOp / CoCoOp

### 5.1. Что это и зачем

**Soft prompting** — вместо ручного подбора текстового промпта (`"a photo of a {class}"`) обучаем небольшое количество **векторов** в эмбеддинг-пространстве токенов, которые подставляются вместо/вокруг class-токена. Веса базовой модели (CLIP, VLM) **не трогаются** — учим только промпт. Это адаптация под домен за минуты вместо часов fine-tuning.

| Метод | Идея | Когда использовать |
|-------|------|---------------------|
| **CoOp** (Context Optimization) | Контекст `[V]_1 [V]_2 ... [V]_M [CLASS]` — M обучаемых векторов общих для всех классов. | Если домен фиксирован, классов немного, и качество важнее обобщения. Базовая статья: Zhou et al., IJCV 2022. |
| **CoCoOp** (Conditional CoOp) | Тот же контекст, но **сдвиг** `h_θ(x)` для каждого изображения добавляется к векторам. `h_θ` — маленький MLP над эмбеддингом картинки. | Если хотите лучше обобщать на **новые классы**, не виденные при обучении. CVPR 2022. |

Источники:
- arXiv: https://arxiv.org/abs/2203.05557 (CoCoOp)
- Официальный репо: https://github.com/KaiyangZhou/CoOp

### 5.2. Параметры в нашем UI

| UI | Поле YAML | Назначение |
|----|-----------|-----------|
| `coop_type` | — | `coop` или `cocoop` (выбор алгоритма). |
| `coop_num_vectors` | `coop_default_num_vectors` | M — длина обучаемого контекста. CoOp работает с 4–16; для классификации обычно 16. |
| `coop_context_init` | `coop_context_init` | Слова, эмбеддинги которых будут стартовыми для M векторов. Хорошая инициализация → быстрая сходимость. Для CLIP — `"a photo of a"`. |
| `class_token_position` | `class_token_position` | Где стоит токен `[CLASS]`: `end` (по умолчанию), `front` или `middle`. |
| `coop_net_depth` | `coop_net_depth` | Глубина Meta-Net в CoCoOp (1–4). Для CoOp игнорируется. |

### 5.3. Жизненный цикл в этом сервисе

```
Сессия разметки → finalize → datasets/<name>.jsonl
                                       ↓
                 POST /coop/train (model, dataset, params)
                                       ↓
            optimization/prompt_generator.generate_coop_script
            подставляет placeholders в шаблон → train.py в run-папке
                                       ↓
            asyncio.create_subprocess_exec(python, train.py)
                                       ↓
            run-папка: train.log + run.lock + prompt_vectors.bin + metrics.json
                                       ↓
                   GET /coop/status/{run_id} ← polling из UI
                                       ↓
                  apply_learned_prompt → инференс с обучаемым промптом
```

### 5.4. Требования к датасету

JSONL, по строке на пример:
```json
{"file_path": "storage/projects/X/uploads/img1.jpg", "question": "Что на фото?", "answer": "кот"}
```

Поля `file_path`, `question`, `answer`, `additional` (опц., с timestamp для видео).

**Минимум примеров на класс:** см. `min_examples_for_soft_prompt` в YAML модели (по умолчанию 30). Для VLM с большим количеством классов — лучше 50+.

### 5.5. Типичные ошибки

- **`coop_supported: false` в YAML** → бэкенд откажет в `/coop/train` с понятным сообщением.
- **Пустой датасет** → CoOp обучится, но ничему не научится. Сначала разметьте ≥30 примеров на класс.
- **Несбалансированные классы** → результат будет смещён к большинству. Добавляйте baseline accuracy в `metrics.json` для контроля.
- **NumPy 2 + старый OpenCV** → `_ARRAY_API not found`. У нас обработано: ffprobe → fallback. Но реальный CoOp требует PyTorch — следите за совместимостью CUDA/torch/numpy.

---

## 6. Запуск

```bash
# Минимально (без cv2):
pip install fastapi "uvicorn[standard]" pydantic pyyaml aiofiles python-multipart httpx Pillow

# Полный набор по ТЗ:
pip install -r requirements.txt

# Локально:
uvicorn app:app --host 0.0.0.0 --port 5000

# За прокси (JupyterHub / nginx):
APP_ROOT_PATH=/user/<user>/proxy/5000 \
  uvicorn app:app --host 0.0.0.0 --port 5000
```

Открыть http://localhost:5000 (или ваш проксированный URL).

---

## 7. Карта файлов (актуальная)

```
app.py                              FastAPI: 21 endpoint ТЗ + projects + shapes/load + rescan
external.py                         мок gigachat_request (заменить на реальный)
requirements.txt                    зависимости
answer.md                           этот документ

core/data_router.py                 ffprobe + fallback cv2 + кэш
core/prompt_checker.py              локальные правила Q&A
core/time_overlay.py                FFmpeg drawtext + NVENC
core/session_store.py               JSON-сессии, project-aware
core/project_store.py               CRUD проектов

models/model_registry.py            Pydantic ModelConfig + YAML cache
models/yaml_example.yaml            пример конфига
models/configs/{Video-XL-2,CLIP-ViT}.yml

annotation/{base,video,image,text,image_bbox}_annotator.py
annotation/image_bbox_annotator.py  save_shape_annotation + load_shape_annotation
                                     (YOLO + COCO + VOC, bbox + polygon)

gigachat/{client,prompts}.py        обёртки над external.gigachat_request

benchmark/{local_metrics,comparator}.py

optimization/{prompt_generator,coop_trainer}.py
optimization/templates/{coop_video_llm,cocoop_clip}.py    # ЗАГЛУШКИ — заменить настоящим обучением

guides/help_data.py

static/index.html                   точка входа Vue
static/style.css                    тёмная тема
static/script.js                    Vue 3 SPA
static/vue.global.prod.js           Vue из CDN или локально

storage/projects/<name>/...         изолированные данные проекта
```

---

## 8. Известные ограничения

- `_uploaded_files` — in-memory, теряется при рестарте сервера → используйте `POST /projects/{name}/rescan`.
- Координаты разметки — в пикселях оригинала; при изменении размера окна не пересчитываются (рендер сам масштабирует).
- Drag/resize работает на canvas-handles 8 px — на очень мелких bbox может быть тесно. Зум пока не реализован.
- CoOp — заглушка; реальное обучение требует PyTorch + GPU.
- GigaChat — мок; для прода замените `external.py` (см. §4.1).
