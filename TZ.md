# ТЕХНИЧЕСКОЕ ЗАДАНИЕ (ПОЛНАЯ ВЕРСИЯ)
## AutoPrompt Annotator 5.0

### 1. НАЗНАЧЕНИЕ СИСТЕМЫ

Разработать локальный веб‑сервис для полного цикла подготовки данных и оптимизации мультимодальных моделей (видео, изображения, текст) с использованием:
- **Soft Prompting** (ручная разметка + проверка через GigaChat);
- **Context Optimization (CoOp)** и **Conditional Context Optimization (CoCoOp)** – автоматическая настройка обучаемых контекстных векторов.

Система помогает пользователю:
- загружать файлы (адаптивно к ОС: Linux/WSL – поля ввода путей, Windows – drag&drop + стандартные диалоги);
- выбирать модель (автоматически генерировать YAML‑конфиг через GigaChat или создавать вручную);
- размечать данные в потоковом режиме с проверкой и улучшением промптов через GigaChat;
- добавлять **таймкод на кадры видео** (предпросмотр через canvas + экспорт видео с «вшитым» временем через FFmpeg);
- размечать изображения прямоугольными областями с экспортом в форматы YOLO, COCO, Pascal VOC;
- автоматически генерировать и запускать обучение **CoOp/CoCoOp** для дообучения промптов;
- сохранять прогресс разметки в сессиях;
- выполнять **бенчмарк модели** до и после оптимизации (GigaChat + локальные метрики точности);
- использовать встроенную справочную систему с туториалом.

**Система не выполняет полного обучения модели, только адаптацию входных промптов.** Все данные хранятся в файловой системе. Работает в закрытом контуре Linux (возможно также в облаке) с доступом к GigaChat API через существующий клиент.

---

### 2. ТЕХНОЛОГИЧЕСКИЙ СТЕК

- **Бэкенд**: FastAPI (асинхронный).
- **Фронтенд**: HTML5 + CSS3 + Vanilla JavaScript (без внешних фреймворков).
- **GigaChat клиент**: существующая функция `gigachat_request(prompt, system_prompt, timeout=30)` – используется без изменений.
- **Обработка медиа**: OpenCV, Pillow, FFmpeg (должен быть установлен в системе и доступен в PATH).
- **Конфигурация моделей и методов оптимизации**: YAML, валидация через Pydantic.
- **Кеширование метаданных**: in‑memory словарь с автоматической очисткой записей старше 1 месяца.
- **Сохранение сессий**: JSON-файлы в `storage/sessions/`.
- **Определение ОС**: `platform.system()`.

---

### 3. СТРУКТУРА ПРОЕКТА

```
annotator/
├── app.py                      # FastAPI приложение
├── core/
│   ├── data_router.py          # определение типа файла, метаданные, кэш
│   ├── prompt_checker.py       # локальная проверка промпта (базовые правила)
│   └── time_overlay.py         # наложение текста на видео (FFmpeg)
├── models/
│   ├── model_registry.py       # работа с YAML (Pydantic, кэш)
│   ├── configs/                # YAML файлы моделей
│   └── yaml_example.yaml       # пример YAML для ручного заполнения
├── annotation/
│   ├── base.py                 # абстрактный аннотатор
│   ├── video_annotator.py
│   ├── image_annotator.py
│   ├── text_annotator.py
│   └── image_bbox_annotator.py # разметка прямоугольниками
├── optimization/
│   ├── coop_trainer.py         # генерация и запуск обучения CoOp/CoCoOp
│   ├── prompt_generator.py     # создание конфигов и скриптов
│   └── templates/              # шаблоны скриптов для разных моделей
├── gigachat/
│   ├── client.py               # обёртка, вызывающая существующий gigachat_request
│   └── prompts.py              # системные промпты (константы)
├── benchmark/
│   ├── comparator.py           # сравнение через GigaChat
│   └── local_metrics.py        # локальные метрики (yesno, classification)
├── guides/
│   └── help_data.py            # словарь подсказок для UI
├── static/
│   ├── index.html
│   ├── style.css
│   └── script.js
└── storage/
    ├── uploads/                # загруженные оригиналы
    ├── exports/                # экспортированные видео с таймкодом
    ├── datasets/               # готовые датасеты (JSONL)
    ├── annotations/            # YOLO/COCO/VOC аннотации для изображений
    ├── sessions/               # файлы прогресса разметки
    └── coop_outputs/           # результаты обучения CoOp/CoCoOp (векторы, модели)
```

---

### 4. МОДУЛЬ ОПРЕДЕЛЕНИЯ ТИПА ФАЙЛА И МЕТАДАННЫХ (`core/data_router.py`)

Реализовать функции:

```python
def detect_file(file_path: str) -> tuple[str, dict]:
    """
    Определяет тип файла: 'video', 'image', 'text'.
    Возвращает тип и словарь метаданных.
    """

def get_video_metadata(file_path: str) -> dict:
    """
    Возвращает: duration (float), width (int), height (int), bitrate (int),
               fps (float), video_codec (str), audio_codec (str или None).
    """

def get_image_metadata(file_path: str) -> dict:
    """Возвращает: width, height, format (str), size_kb (int)."""

def get_text_metadata(file_path: str) -> dict:
    """Возвращает: chars (int), words (int), lines (int)."""
```

**Кеширование:**  
- Результаты вызовов `get_*_metadata` сохраняются в словаре `metadata_cache` с ключом = абсолютный путь к файлу.  
- Каждая запись имеет временную метку. Раз в час запускается фоновая очистка: удаляются записи старше 1 месяца.  
- При перезапуске сервиса кеш сбрасывается.

---

### 5. МОДУЛЬ РАБОТЫ С МОДЕЛЯМИ (`models/model_registry.py`)

#### 5.1. YAML-конфиг модели

Обязательные поля:

```yaml
name: str
type: "composite" | "monolithic"
components:            # обязательно, если type == composite
  - name: str
    type: "visual_encoder" | "llm" | "other"
    source: str        # HuggingFace ID или путь
modalities: list[str]  # "video", "image", "text"
input_format: str      # шаблон, например "<video> {question}"
output_type: "free_text" | "yesno" | "classification"
min_examples_for_soft_prompt: int   # по умолчанию 30
recommended_annotation_style: str   # "qa_pairs" и т.п.
soft_prompt_guide: str  # многострочная инструкция с примерами кода

# 🆕 Ключи для CoOp/CoCoOp (необязательные; если отсутствуют – CoOp не используется)
coop_supported: bool
coop_default_num_vectors: int       # сколько обучаемых токенов, например 16
coop_context_init: str              # например, "a photo of a"
class_token_position: "end" | "front" | "middle"
coop_net_depth: int                 # глубина Meta-Net для CoCoOp (например, 3)
```

#### 5.2. Функции

```python
from pydantic import BaseModel, ValidationError
from typing import Literal, List, Optional

class ModelConfig(BaseModel):
    name: str
    type: Literal["composite","monolithic"]
    components: Optional[List[dict]] = None
    modalities: List[str]
    input_format: str
    output_type: str
    min_examples_for_soft_prompt: int = 30
    recommended_annotation_style: str
    soft_prompt_guide: str
    coop_supported: Optional[bool] = False
    coop_default_num_vectors: Optional[int] = 16
    coop_context_init: Optional[str] = "a photo of a"
    class_token_position: Optional[str] = "end"
    coop_net_depth: Optional[int] = 3

def load_model_config(model_name: str) -> ModelConfig:
    """Загружает YAML, валидирует, кеширует результат (in‑memory, очистка через 1 час)."""

def list_available_models() -> List[str]:
    """Возвращает имена файлов .yml в models/configs/ (без расширения)."""

def save_model_config(model_name: str, yaml_content: str) -> None:
    """Сохраняет YAML после валидации. Перезаписывает существующий."""

def generate_model_config_via_gigachat(model_identifier: str) -> dict:
    """
    Отправляет запрос к GigaChat. Возвращает:
    - при успехе: {"yaml": "<сгенерированный YAML>"}
    - при ошибке: {"error": "текст ошибки", "fallback_prompt": "промпт для ручной генерации", "example_yaml": "пример YAML"}
    """
```

#### 5.3. Генерация конфига через GigaChat (и повторные попытки)

- В UI кнопка «Сгенерировать конфиг» вызывает `generate_model_config_via_gigachat`.  
- Если получен `error`, показывается сообщение об ошибке, поле `fallback_prompt` (копируется в буфер обмена) и пример YAML.  
- Кнопка «Сгенерировать снова» активна всегда – можно нажимать неограниченное число раз.  
- При успешной генерации отображается YAML и кнопка «Сохранить».

---

### 6. МОДУЛЬ АННОТАЦИИ И РАЗМЕТКИ (`annotation/`)

#### 6.1. Базовый аннотатор (`annotation/base.py`)

```python
from abc import ABC, abstractmethod

class BaseAnnotator(ABC):
    @abstractmethod
    def load_file(self, file_path: str) -> None:
        pass

    @abstractmethod
    def get_display_data(self) -> dict:
        """Возвращает данные для отображения в UI (URL видео, base64 картинки, текст)."""
        pass

    @abstractmethod
    def save_annotation(self, question: str, answer: str, additional: dict = None) -> None:
        """Сохраняет одну пару Q&A в текущую сессию."""
        pass
```

#### 6.2. Аннотатор видео (`annotation/video_annotator.py`)

Наследует `BaseAnnotator`.  
- Поддерживает видеоплеер с навигацией.  
- Позволяет вставлять таймкод на текущий кадр (через canvas на фронтенде).  
- При сохранении аннотации добавляет поле `timestamp` (время в секундах) в `additional`.

#### 6.3. Аннотатор изображений (`annotation/image_annotator.py`)

Наследует `BaseAnnotator`.  
- Отображает изображение с зумом.  
- Позволяет рисовать прямоугольники (bbox) – делегирует в `image_bbox_annotator.py`.

#### 6.4. Аннотатор текста (`annotation/text_annotator.py`)

Наследует `BaseAnnotator`.  
- Отображает текст в моноширинном блоке.  
- Сохраняет Q&A пары без дополнительных данных.

#### 6.5. Разметка прямоугольниками (`annotation/image_bbox_annotator.py`)

**Функциональность:**
- На загруженном изображении пользователь рисует прямоугольники (мышью: клик – начало, отпускание – конец).  
- Каждому прямоугольнику присваивается **класс** (текстовое поле или выпадающий список).  
- Поддерживается редактирование: перемещение, изменение размера, удаление, смена класса.  

**Форматы экспорта:**
При сохранении разметки система создаёт файл в `storage/annotations/` с именем, совпадающим с именем исходного изображения (без расширения), и соответствующим расширением:
- **YOLO**: `<filename>.txt` – каждая строка: `class_id x_center y_center width height` (нормализованные 0..1). Дополнительно создаётся `classes.txt` со списком имён классов.
- **COCO JSON**: `<filename>.json` – в формате COCO.
- **Pascal VOC XML**: `<filename>.xml` – в формате PASCAL VOC.

Пользователь выбирает формат(ы) перед сохранением.

**Функция:**
```python
def save_bbox_annotation(image_path: str, boxes: List[dict], format: str) -> str:
    """
    boxes: [{"class": str, "x1": int, "y1": int, "x2": int, "y2": int}, ...]
    Возвращает путь к сохранённому файлу аннотации.
    """
```

---

### 7. МОДУЛЬ РАБОТЫ С ВИДЕО И ТАЙМКОДАМИ (`core/time_overlay.py`)

#### 7.1. Предпросмотр с наложением времени (фронтенд)

При просмотре видео в интерфейсе кнопка **«Вставить время»** накладывает текущий таймкод (HH:MM:SS) на видеоплеер через canvas.  
Блок с текстом можно перетаскивать мышью и изменять размер (колёсико мыши). Это изменение не сохраняется в исходном видео – только для визуальной оценки.

#### 7.2. Экспорт видео с «вшитым» таймкодом (бэкенд)

Кнопка **«Экспортировать видео с таймкодом»** открывает диалоговое окно:
- выбор диапазона времени (начало, конец) или всего видео;
- выбор **кодека** и **битрейта**:
  - сохранить исходный битрейт (по умолчанию);
  - уменьшить битрейт (пользователь вводит значение, например `2M`, `1M`, `500k`);
  - использовать аппаратное ускорение (GPU, если доступно) – флажок *«Использовать GPU (NVENC)»* (только для Linux).

Бэкенд вызывает **FFmpeg** с фильтром `drawtext`. Команда строится так:
- для каждого кадра подставляется текущее время (учитывается FPS исходного видео).
- Пример:  
  `ffmpeg -i input.mp4 -vf "drawtext=text='%{pts\\:hms}':x=10:y=10:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.7" -b:v <bitrate> -c:v <codec> output.mp4`

Новый файл сохраняется в `storage/exports/<original_name>_timestamped.mp4`. Пользователю возвращается ссылка для скачивания.

**Асинхронный вызов FFmpeg:** использовать `asyncio.create_subprocess_exec` с чтением stdout/stderr.  
**GPU-кодирование:** если флаг `use_gpu` установлен и система Linux с NVIDIA, в команду добавляется `-c:v h264_nvenc`, иначе `-c:v libx264`.

#### 7.3. Сохранение таймкода в аннотации

При сохранении пары (вопрос, ответ) для видео в поле `additional` автоматически добавляется ключ `timestamp` с текущим временем в секундах (float).

---

### 8. МОДУЛЬ ОПТИМИЗАЦИИ CoOp / CoCoOp (`optimization/`)

#### 8.1. Генерация скрипта обучения (`optimization/prompt_generator.py`)

```python
def generate_coop_script(model_config: ModelConfig, dataset_path: str, output_dir: str) -> str:
    """
    Генерирует Python‑скрипт для обучения CoOp/CoCoOp.
    Использует шаблон из optimization/templates/.
    Возвращает путь к сгенерированному скрипту.
    """
```

#### 8.2. Запуск обучения (`optimization/coop_trainer.py`)

```python
async def run_coop_training(
    model_config: ModelConfig,
    dataset_path: str,
    output_dir: str,
    coop_type: Literal["coop", "cocoop"],
    num_vectors: int,
    context_init: str,
    class_token_position: str,
    net_depth: int = 3,
) -> dict:
    """
    Запускает асинхронный процесс обучения (через subprocess).
    Возвращает {"status": "running", "log_file": "...", "output_dir": "..."}.
    """
```

#### 8.3. Получение статуса и логов

```python
def get_coop_status(output_dir: str) -> dict:
    """
    Проверяет статус обучения (running, completed, failed).
    Возвращает также последние строки лога.
    """
```

#### 8.4. Применение обученных промптов

```python
def apply_learned_prompt(model_config: ModelConfig, prompt_vectors_path: str) -> None:
    """
    Загружает обученные векторы и подготавливает модель к инференсу.
    Модель при этом не перезаписывается – векторы сохраняются отдельно.
    """
```

#### 8.5. Шаблоны скриптов

В папке `optimization/templates/` хранятся готовые шаблоны для разных типов моделей (например, `coop_video_llm.py`, `cocoop_clip.py`). Шаблоны содержат метки для подстановки `{dataset_path}`, `{num_vectors}`, `{context_init}` и т.д.

---

### 9. МОДУЛЬ GigaChat (`gigachat/`)

Используется существующая асинхронная функция:
```python
async def gigachat_request(prompt: str, system_prompt: str, timeout: float = 30.0) -> str:
    # Реализация уже существует, не изменять
```

В `gigachat/prompts.py` задаются системные промпты в виде строк-констант:
- `SYSTEM_PROMPT_GENERATE_CONFIG`
- `SYSTEM_PROMPT_CHECK_PROMPT`
- `SYSTEM_PROMPT_IMPROVE_PROMPT`
- `SYSTEM_PROMPT_BENCHMARK`
- `SYSTEM_PROMPT_ESTIMATE_MIN_EXAMPLES`

Каждый промпт содержит описание задачи, формат вывода (JSON, YAML), примеры и требование вернуть только нужную информацию.

Функции-обёртки в `gigachat/client.py`:

```python
async def check_prompt_with_giga(question: str, answer: str, model_config: ModelConfig) -> dict:
    """Возвращает {"valid": bool, "message": str, "suggestions": List[str]}"""

async def improve_prompt_with_giga(question: str, model_config: ModelConfig) -> str:
    """Возвращает улучшенный вопрос"""

async def generate_model_config(description: str) -> dict:
    """Возвращает {"yaml": str} или {"error": ..., "fallback_prompt": ...}"""

async def benchmark_models(questions: List[str], answers_before: List[str],
                           answers_after: List[str], model_config: ModelConfig) -> str:
    """Возвращает текстовый анализ"""
```

---

### 10. МОДУЛЬ БЕНЧМАРКА И ЛОКАЛЬНЫХ МЕТРИК (`benchmark/`)

#### 10.1. Локальные метрики (`benchmark/local_metrics.py`)

- Если модель в конфиге имеет `output_type: "yesno"`, вычисляется **точность (accuracy)** – совпадение ответов с эталонными (регистронезависимо, обрезка пробелов).
- Если `output_type: "classification"`, вычисляется **accuracy** и **F1‑score (macro)**.
- Результат возвращается в виде `dict` с ключами `accuracy`, `f1_score` (если применимо).

#### 10.2. Сравнение через GigaChat (`benchmark/comparator.py`)

```python
async def compare_models(questions: List[str],
                         answers_before: List[str],
                         answers_after: List[str],
                         model_config: ModelConfig) -> dict:
    """
    Отправляет запрос к GigaChat (SYSTEM_PROMPT_BENCHMARK).
    Возвращает:
    {
        "gigachat_report": str,
        "local_metrics": {"accuracy": float, ...}
    }
    """
```

---

### 11. ПОТОКОВАЯ РАЗМЕТКА И СЕССИИ

- При старте разметки сервер создаёт `session_id` (UUID) и сохраняет начальное состояние в `storage/sessions/<session_id>.json`:

```json
{
  "session_id": "uuid",
  "dataset_name": "my_dataset",
  "model_name": "Video-XL-2",
  "files": [{"id": 1, "path": "...", "type": "video", "annotated": false}],
  "current_index": 0,
  "annotations": []
}
```

- При каждом «Сохранить и далее» обновляется `current_index`, добавляется запись в `annotations`.  
- По окончании (когда `current_index == len(files)-1` и пользователь нажал «Завершить») весь датасет сохраняется в `storage/datasets/<dataset_name>.jsonl`, сессия удаляется.  
- При перезагрузке страницы фронтенд запрашивает `/session/current`. Если активная сессия есть – предлагает продолжить.

---

### 12. АДАПТАЦИЯ ИНТЕРФЕЙСА ПОД ОПЕРАЦИОННУЮ СИСТЕМУ

Фронтенд при загрузке отправляет GET `/get_os_type`. Бэкенд возвращает `{"os": "linux"}` или `{"os": "windows"}`.

- **Windows**:  
  - Загрузка файлов: область drag‑and‑drop + кнопка «Открыть файлы» (input type=file multiple).  
  - Загрузка папок: кнопка «Выбрать папку» (input type=file webkitdirectory).

- **Linux**:  
  - Загрузка файлов: текстовое поле для ввода пути (или нескольких путей через пробел) + кнопка «Загрузить».  
  - Загрузка папок: текстовое поле для пути к папке + кнопка «Загрузить рекурсивно».  
  - Дополнительно: drag‑and‑drop также поддерживается (не удаляется, но поля ввода остаются).

---

### 13. ВСПЛЫВАЮЩИЕ ПОДСКАЗКИ И ТУТОРИАЛ

- В `guides/help_data.py` определён словарь `HELP_TEXTS`, где ключ – CSS‑селектор (или ID) элемента интерфейса, значение – словарь с полями `title`, `description`, `example`.  
- Кнопка «?» в правом нижнем углу активирует режим помощи: при клике на любой элемент UI открывается модальное окно с подсказкой.  
- Пункт меню «Тур» запускает пошаговое обучение (Intro.js или собственная реализация) – последовательно подсвечиваются основные элементы с пояснениями.

---

### 14. API БЭКЕНДА (FastAPI) – ПОЛНЫЙ СПИСОК

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/get_os_type` | → `{"os": "linux"}` или `{"os": "windows"}` |
| POST | `/upload` | multipart (Windows) или JSON `{"paths": [...]}` (Linux). Сохраняет файлы, возвращает `{"file_ids": [int], "metadata": [...]}` |
| GET | `/files/{file_id}` | Отдаёт файл (видео/изображение/текст) |
| POST | `/annotate/start` | `{"dataset_name": str, "model_name": str, "file_ids": [int]}` → `{"session_id": str}` |
| GET | `/annotate/current` | → `{"session": {...}}` или `null` |
| POST | `/annotate/next` | `{"session_id": str}` → `{"file_id": int, "type": str, "metadata": {...}}` |
| POST | `/save_annotation` | `{"session_id": str, "question": str, "answer": str, "timestamp": float (optional)}` → `{"progress": "3/10"}` |
| POST | `/check_prompt_giga` | `{"question": str, "answer": str, "model_name": str}` → `{"valid": bool, "message": str, "suggestions": list}` |
| POST | `/improve_prompt_giga` | `{"question": str, "model_name": str}` → `{"improved_question": str}` |
| GET | `/models/list` | → `["model1", "model2"]` |
| POST | `/models/generate_config` | `{"model_identifier": str}` → результат генерации |
| POST | `/models/save_config` | `{"name": str, "yaml": str}` → `{"status": "ok"}` |
| GET | `/models/soft_prompt_guide/{model_name}` | → `{"guide": str}` |
| GET | `/models/min_examples/{model_name}` | → `{"min_examples": int}` |
| POST | `/image/bbox/save` | `{"file_id": int, "format": "yolo"|"coco"|"voc", "boxes": [...]}` → `{"annotation_file": str}` |
| POST | `/video/burn_timestamp` | `{"file_id": int, "start": float, "end": float, "bitrate": str, "use_gpu": bool, "codec": str}` → `{"exported_url": str}` |
| POST | `/coop/train` | `{"model_name": str, "dataset_name": str, "coop_type": "coop"|"cocoop", "num_vectors": int, "context_init": str, "class_token_position": str, "net_depth": int}` → `{"run_id": str}` |
| GET | `/coop/status/{run_id}` | → `{"status": str, "log": str, "output_dir": str}` |
| POST | `/benchmark/compare` | `{"model_name": str, "questions": [str], "answers_before": [str], "answers_after": [str]}` → `{"gigachat_report": str, "local_metrics": {...}}` |
| GET | `/help/{element_selector}` | → `{"title": str, "description": str, "example": str}` |

---

### 15. ТРЕБОВАНИЯ К ОКРУЖЕНИЮ И ЗАПУСКУ

- Python 3.12  
- CUDA 12+ (не обязательно, но используется для аппаратного ускорения FFmpeg)  
- FFmpeg в PATH (проверяется при старте: `ffmpeg -version`)  
- Существующий GigaChat клиент (импортируется как `from external import gigachat_request`)  
- Переменные окружения: не требуются, все настройки через код.

**Запуск:**
```bash
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

---

### 16. ИСТОЧНИКИ И ВДОХНОВЕНИЕ ДЛЯ CoOp/CoCoOp

При разработке модуля CoOp/CoCoOp необходимо опираться на:
- **Основная статья CoOp:** Zhou et al., "Conditional Prompt Learning for Vision-Language Models", CVPR 2022 / IJCV 2022.  
  arXiv: `https://arxiv.org/abs/2203.05557`
- **Официальный GitHub репозиторий (CoOp):** `https://github.com/KaiyangZhou/CoOp`
- **Расширенный репозиторий (CoOp + CoCoOp):** `https://github.com/Maxsxie/CoOp-CoCoOP`

---

### 17. ЗАГОТОВКИ (STUBS) ДЛЯ ГЕНЕРАЦИИ КОДА

Ниже приведены **имена всех функций и классов** с точными сигнатурами. Каждый модуль должен быть реализован строго в соответствии с этими заготовками.

#### 17.1. `core/data_router.py`
```python
def detect_file(file_path: str) -> tuple[str, dict]: ...
def get_video_metadata(file_path: str) -> dict: ...
def get_image_metadata(file_path: str) -> dict: ...
def get_text_metadata(file_path: str) -> dict: ...
```

#### 17.2. `core/prompt_checker.py`
```python
def check_prompt_local(question: str, answer: str, expected_output_type: str) -> dict: ...
```

#### 17.3. `core/time_overlay.py`
```python
def add_timestamp_to_frame(frame: np.ndarray, timestamp_str: str, position: tuple, font_scale: float) -> np.ndarray: ...
```

#### 17.4. `models/model_registry.py`
```python
from pydantic import BaseModel
from typing import Literal, List, Optional

class ModelConfig(BaseModel):
    name: str
    type: Literal["composite","monolithic"]
    components: Optional[List[dict]] = None
    modalities: List[str]
    input_format: str
    output_type: str
    min_examples_for_soft_prompt: int = 30
    recommended_annotation_style: str
    soft_prompt_guide: str
    coop_supported: Optional[bool] = False
    coop_default_num_vectors: Optional[int] = 16
    coop_context_init: Optional[str] = "a photo of a"
    class_token_position: Optional[str] = "end"
    coop_net_depth: Optional[int] = 3

def load_model_config(model_name: str) -> ModelConfig: ...
def list_available_models() -> List[str]: ...
def save_model_config(model_name: str, yaml_content: str) -> None: ...
def generate_model_config_via_gigachat(model_identifier: str) -> dict: ...
```

#### 17.5. `annotation/base.py`
```python
from abc import ABC, abstractmethod

class BaseAnnotator(ABC):
    @abstractmethod
    def load_file(self, file_path: str) -> None: ...
    @abstractmethod
    def get_display_data(self) -> dict: ...
    @abstractmethod
    def save_annotation(self, question: str, answer: str, additional: dict = None) -> None: ...
```

#### 17.6. `annotation/image_bbox_annotator.py`
```python
def save_bbox_annotation(image_path: str, boxes: List[dict], format: str) -> str: ...
```

#### 17.7. `optimization/prompt_generator.py`
```python
def generate_coop_script(model_config: ModelConfig, dataset_path: str, output_dir: str) -> str: ...
```

#### 17.8. `optimization/coop_trainer.py`
```python
async def run_coop_training(model_config: ModelConfig, dataset_path: str, output_dir: str,
                            coop_type: str, num_vectors: int, context_init: str,
                            class_token_position: str, net_depth: int) -> dict: ...
def get_coop_status(output_dir: str) -> dict: ...
def apply_learned_prompt(model_config: ModelConfig, prompt_vectors_path: str) -> None: ...
```

#### 17.9. `gigachat/client.py`
```python
async def check_prompt_with_giga(question: str, answer: str, model_config: ModelConfig) -> dict: ...
async def improve_prompt_with_giga(question: str, model_config: ModelConfig) -> str: ...
async def generate_model_config(description: str) -> dict: ...
async def benchmark_models(questions: List[str], answers_before: List[str],
                           answers_after: List[str], model_config: ModelConfig) -> str: ...
```

#### 17.10. `benchmark/comparator.py`
```python
async def compare_models(questions: List[str], answers_before: List[str],
                         answers_after: List[str], model_config: ModelConfig) -> dict: ...
```

#### 17.11. `app.py`
```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/upload") ...
@app.post("/annotate/start") ...
@app.post("/save_annotation") ...
@app.post("/check_prompt_giga") ...
@app.post("/improve_prompt_giga") ...
@app.post("/models/generate_config") ...
@app.post("/models/save_config") ...
@app.post("/coop/train") ...
@app.get("/coop/status/{run_id}") ...
@app.post("/benchmark/compare") ...
```

---

### 18. ФАЙЛ `requirements.txt`

```
fastapi==0.136.1
uvicorn[standard]==0.24.0
opencv-python==4.9.0.80
Pillow==12.2.0
aiohttp==3.13.5
httpx==0.25.0
pyyaml==6.0.1
python-multipart==0.0.26
numpy==1.26.4
pydantic==2.13.3
```