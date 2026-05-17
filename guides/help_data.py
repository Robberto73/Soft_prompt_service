"""UI help texts. Keys = CSS selectors / element IDs."""

HELP_TEXTS: dict[str, dict] = {
    "#upload-area": {
        "title": "Загрузка файлов",
        "description": "Выберите файлы (видео, изображения, текст) для разметки. "
        "На Windows доступен drag&drop, на Linux — поле для путей.",
        "example": "Перетащите test.mp4 или введите /home/user/data/img.jpg",
    },
    "#model-select": {
        "title": "Выбор модели",
        "description": "Список моделей загружается из models/configs/. "
        "Можно сгенерировать новый YAML через GigaChat.",
        "example": "Video-XL-2 / CLIP-ViT",
    },
    "#annotate-form": {
        "title": "Форма разметки",
        "description": "Введите вопрос и ответ для текущего файла. "
        "GigaChat может проверить и улучшить формулировку.",
        "example": "Q: Сколько людей на видео? A: 3",
    },
    "#bbox-canvas": {
        "title": "Разметка прямоугольниками",
        "description": "Нажмите ЛКМ и протяните, чтобы создать bbox. "
        "Каждому прямоугольнику задайте класс. Экспорт: YOLO / COCO / VOC.",
        "example": "Класс: car, dog, person",
    },
    "#timestamp-btn": {
        "title": "Вставить время",
        "description": "Накладывает текущий таймкод на canvas поверх плеера. "
        "Перемещение — мышью, размер — колесом.",
        "example": "00:01:23",
    },
    "#export-video-btn": {
        "title": "Экспортировать видео с таймкодом",
        "description": "Запускает FFmpeg, который «вшивает» таймкод в каждый кадр. "
        "На Linux доступен NVENC.",
        "example": "Битрейт: 2M, Codec: libx264",
    },
    "#coop-train-btn": {
        "title": "Запустить CoOp/CoCoOp",
        "description": "Генерирует скрипт обучения из шаблона и запускает его в "
        "subprocess. Прогресс — в логе. Перед запуском убедитесь, что выбран "
        "датасет и в YAML модели стоит coop_supported: true.",
        "example": "num_vectors=16, context_init='a photo of a'",
    },
    "#coop-num-vectors": {
        "title": "Длина обучаемого контекста M",
        "description": "Сколько токенов-векторов учим. Авторы CoOp экспериментируют "
        "от 4 до 16; для классификации обычно достаточно 16.",
        "example": "M = 16",
    },
    "#coop-context-init": {
        "title": "Инициализация контекста",
        "description": "Слова, эмбеддинги которых будут начальными значениями "
        "обучаемых векторов. Хорошая инициализация ускоряет сходимость.",
        "example": "a photo of a",
    },
    "#coop-class-pos": {
        "title": "Позиция [CLASS] токена",
        "description": "end — [V]_1...[V]_M [CLASS]; front — [CLASS] [V]_1...[V]_M; "
        "middle — векторы по обе стороны от [CLASS]. По умолчанию end.",
        "example": "end",
    },
    "#coop-net-depth": {
        "title": "Глубина Meta-Net (только CoCoOp)",
        "description": "Количество слоёв в маленьком MLP, который генерирует "
        "сдвиг контекста по эмбеддингу изображения h_θ(x).",
        "example": "depth = 3",
    },
    "#coop-dataset-select": {
        "title": "Датасет для обучения",
        "description": "Берётся .jsonl из datasets/ активного проекта. "
        "Если пусто — завершите сессию разметки на вкладке «Разметка».",
        "example": "dataset.jsonl",
    },
    "#coop-apply-btn": {
        "title": "Применить выученный prompt",
        "description": "Регистрирует файл prompt_vectors.bin как активный для "
        "выбранной модели. Веса самой модели не меняются.",
        "example": "",
    },
    "#benchmark-btn": {
        "title": "Бенчмарк",
        "description": "Сравнивает ответы модели до и после оптимизации. "
        "Возвращает локальные метрики и текстовый отчёт GigaChat.",
        "example": "accuracy=0.83, f1=0.79",
    },
    "#help-btn": {
        "title": "Режим помощи",
        "description": "После клика по «?» нажмите на любой элемент UI, "
        "чтобы увидеть всплывающую подсказку.",
        "example": "",
    },
    "#tour-btn": {
        "title": "Тур по интерфейсу",
        "description": "Пошаговое обучение: подсвечивает основные элементы и "
        "коротко объясняет их назначение.",
        "example": "",
    },
}
