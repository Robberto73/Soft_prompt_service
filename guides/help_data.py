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
        "subprocess. Прогресс — в логе.",
        "example": "num_vectors=16, context_init='a photo of a'",
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
