# Прогресс реализации AutoPrompt Annotator 5.0

ТЗ из `TZ.md` разбито на 14 блоков и реализовано в одном сеансе.

## Резюме решений по объёму
- **GigaChat** — мок в `external.py`. Заглушка распознаёт системные промпты (генерация YAML, проверка/улучшение промпта, бенчмарк, оценка min_examples) и возвращает правдоподобные синтетические ответы. Для прода замените файл на свой клиент с той же сигнатурой `async def gigachat_request(prompt, system_prompt, timeout=30) -> str`.
- **CoOp / CoCoOp** — заглушки шаблонов (`optimization/templates/coop_video_llm.py`, `cocoop_clip.py`): имитируют 4–5 эпох обучения, генерируют фейковые `prompt_vectors.bin` и `metrics.json`. Управление обучением (subprocess, статусы, логи, exit code) — реальное.
- **Всё остальное** — рабочая реализация: data_router, prompt_checker, FFmpeg overlay, model_registry, аннотаторы, экспорт bbox в YOLO/COCO/VOC, сессии, бенчмарк, все эндпоинты, фронтенд.

## Чек-лист

- [x] **Блок 1.** Скелет: каталоги (`core/`, `models/configs/`, `annotation/`, `optimization/templates/`, `gigachat/`, `benchmark/`, `guides/`, `static/`, `storage/{uploads,exports,datasets,annotations,sessions,coop_outputs}/`), `requirements.txt` (по §18 + `aiofiles`), `__init__.py`, мок `external.py`.
- [x] **Блок 2.** `core/data_router.py` — `detect_file`, `get_video_metadata` (cv2), `get_image_metadata` (PIL), `get_text_metadata`, кеш с TTL 30 дней, фоновая `cache_purge_loop` (запускается из `app.startup`).
- [x] **Блок 3.** `core/prompt_checker.py` — `check_prompt_local` с правилами для yesno/classification/free_text.
- [x] **Блок 4.** `core/time_overlay.py` — `add_timestamp_to_frame` (cv2), `burn_timestamp_to_video` (async FFmpeg `drawtext` с поддержкой start/end/bitrate/codec/NVENC), `check_ffmpeg_available`.
- [x] **Блок 5.** `models/model_registry.py` (Pydantic `ModelConfig` строго по §17.4, кеш TTL 1 ч), `models/yaml_example.yaml`, два готовых конфига (`Video-XL-2.yml`, `CLIP-ViT.yml`).
- [x] **Блок 6.** `gigachat/prompts.py` (5 системных промптов) и `gigachat/client.py` (4 async обёртки + `_safe_json`).
- [x] **Блок 7.** `annotation/{base,video,image,text,image_bbox}_annotator.py`. `save_bbox_annotation` поддерживает YOLO (нормализованные координаты + `classes.txt`), COCO (полный JSON), Pascal VOC XML.
- [x] **Блок 8.** `optimization/prompt_generator.py` (подстановка `__NAME__` плейсхолдеров) и `coop_trainer.py` (`run_coop_training`, `get_coop_status`, `apply_learned_prompt`). Шаблоны имитируют обучение и пишут реальный лог.
- [x] **Блок 9.** `benchmark/local_metrics.py` (accuracy, macro F1 без sklearn) и `benchmark/comparator.py`.
- [x] **Блок 10.** `core/session_store.py` — `create_session`, `get_session`, `get_active_session`, `save_annotation_to_session`, `advance_session`, `progress_string`, `finalize_session` (датасет в `storage/datasets/<name>.jsonl`).
- [x] **Блок 11.** `guides/help_data.py` — словарь `HELP_TEXTS` на 10 ключевых элементов UI.
- [x] **Блок 12.** `app.py` — FastAPI приложение, **все 21 эндпоинт** из §14: `/get_os_type`, `/upload`, `/files/{id}`, `/annotate/{start,current,next,finalize}`, `/save_annotation`, `/check_prompt_giga`, `/improve_prompt_giga`, `/models/{list,generate_config,save_config,soft_prompt_guide,min_examples}`, `/image/bbox/save`, `/video/burn_timestamp`, `/coop/{train,status}`, `/benchmark/compare`, `/help/{selector}`. На startup проверяется FFmpeg и стартует фоновая чистка кеша.
- [x] **Блок 13.** `static/{index.html,style.css,script.js}` — единая страница с тремя панелями. JS управляет: OS-адаптивной загрузкой (Windows: drag&drop + input multiple, Linux: textarea с путями), потоковой сессией с восстановлением, рисованием bbox на canvas, наложением таймкода, экспортом видео, GigaChat-кнопками, polling-ом статуса CoOp, бенчмарком, режимом помощи (клик по элементу → tooltip с описанием) и пошаговым туром.
- [x] **Блок 14.** Smoke-тест: все Python-файлы валидны (`ast.parse`); чистый импорт `app.py` без warnings (27 routes); TestClient проверка эндпоинтов `/get_os_type`, `/models/list`, `/models/soft_prompt_guide`, `/models/generate_config`, `/help/...`, `/check_prompt_giga`, `/benchmark/compare` — все возвращают HTTP 200 с ожидаемой структурой.

## Запуск

```bash
pip install -r requirements.txt   # на Python 3.13 numpy 1.26.4 потребует компиляции;
                                  # для smoke-теста достаточно: fastapi uvicorn pydantic pyyaml aiofiles python-multipart httpx
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
# открыть http://localhost:5000
```

## Известные ограничения / следующие шаги
- `requirements.txt` следует ТЗ дословно — на Python 3.13 numpy 1.26.4 не имеет wheel и собирается из исходников. Для актуальных версий замените `numpy==1.26.4` на `numpy>=1.26,<3` или используйте Python 3.12 как указано в §15.
- `audio_codec` в метаданных видео всегда `None` (cv2 не читает аудио-стрим). Если нужно — поднять зависимость `pymediainfo` или парсить `ffprobe -print_format json`.
- CoOp-шаблоны — заглушки. Для реального обучения подмените содержимое `optimization/templates/*.py` на код из `https://github.com/KaiyangZhou/CoOp` (см. §16).
- Реестр загруженных файлов (`_uploaded_files`) живёт в памяти и сбрасывается при перезапуске. Для прода — вынести в SQLite.
- `external.py` = мок. Замените на реальный клиент GigaChat (сертификаты Минцифры, OAuth, etc.).

## Карта файлов

```
app.py                              FastAPI, 21 endpoint
external.py                         мок gigachat_request
requirements.txt                    как в §18 + aiofiles
answer.md                           этот файл
core/{data_router,prompt_checker,time_overlay,session_store}.py
models/model_registry.py            Pydantic + YAML + кеш
models/yaml_example.yaml
models/configs/{Video-XL-2,CLIP-ViT}.yml
annotation/{base,video,image,text,image_bbox}_annotator.py
gigachat/{client,prompts}.py
benchmark/{local_metrics,comparator}.py
optimization/{prompt_generator,coop_trainer}.py
optimization/templates/{coop_video_llm,cocoop_clip}.py    # заглушки
guides/help_data.py
static/{index.html,style.css,script.js}
storage/{uploads,exports,datasets,annotations,sessions,coop_outputs}/
```
