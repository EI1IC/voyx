# Voyx Backend - API Сервер

FastAPI сервер для расчёта маршрутов на основе данных OpenStreetMap.

## 🚀 Запуск

### 1. Создание виртуального окружения

```bash
python -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Запуск сервера

```bash
python main.py
```

Сервер запустится на `http://localhost:8000`

## 📖 API Documentation

OpenAPI (Swagger) документация доступна на:
- `http://localhost:8000/docs` - Swagger UI
- `http://localhost:8000/redoc` - ReDoc

## 📦 Структура

```
backend/
├── main.py               # Точка входа приложения
├── requirements.txt      # Зависимости Python
├── route_engine.py       # Логика маршрутизации (опционально)
├── src/app/             # Основной пакет приложения
│   ├── __init__.py
│   ├── barriers.py      # Работа с барьерами
│   ├── geocoding.py     # Геокодирование адресов
│   ├── graph.py         # Работа с графом дорог
│   ├── routing.py       # Расчёт маршрутов
│   └── config.py        # Конфигурация
├── cache/               # Кэш данных (будет создана)
├── docs/                # Документация (будет создана)
└── .venv/              # Виртуальное окружение
```

## 🔗 API Endpoints

### POST /api/route
Рассчитывает маршрут между двумя адресами

**Body:**
```json
{
  "start_address": "Киров, Ульяновская, 30",
  "end_address": "Киров, Ленина, 50",
  "waypoints": []
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "route": [[49.6, 58.5], ...],
    "distance_km": 2.5,
    "time_min": 10,
    "waypoints": [...],
    "has_barriers": false
  }
}
```

### POST /api/route/multi
Рассчитывает маршрут через несколько точек

**Body:**
```json
{
  "waypoints": ["Адрес 1", "Адрес 2", "Адрес 3"]
}
```

## ⚙️ Конфигурация

Отредактируйте `src/app/config.py` для изменения:
- BBOX (регион для скачивания дорог)
- SPEED_LIMITS (ограничения скорости)
- ROAD_PENALTIES (штрафы за тип дороги)

## 🐛 Troubleshooting

### Ошибка: scikit-learn не установлен
```bash
pip install scikit-learn
```

### Ошибка: нет доступа к интернету при загрузке графа
Граф будет закэширован в папке `cache/` после первого успешного скачивания.

### Медленный старт приложения
При первом запуске проходит инициализация графа дорог (может занять несколько минут).

## 📝 Разработка

### Запуск в режиме development с горячей перезагрузкой

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Запуск в production

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 🔗 Связь для frontend

Frontend подключается к backend через CORS. По умолчанию разрешены все источники.
Для production измените `allow_origins` в `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # вместо ["*"]
    ...
)
```
