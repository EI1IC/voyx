# Voyx Frontend - Веб-интерфейс

Статический веб-интерфейс для маршрутизации на основе Leaflet и Vanilla JavaScript.

## 🚀 Запуск

### Локально (Python 3)

```bash
# Запустить встроенный HTTP сервер на порту 3000
python -m http.server 3000
```

Откройте браузер: `http://localhost:3000`

### Локально (Node.js)

```bash
# Вариант 1: http-server (если установлен)
npx http-server -p 3000

# Вариант 2: если установлены зависимости
npm run dev
```

## 📁 Структура

```
frontend/
├── package.json         # npm конфигурация
├── index.html           # Главная страница
├── style.css            # Стили
├── main.js              # Основная логика приложения
├── api.js               # Клиент для backend API
├── README.md
└── public/              # Статические файлы
    ├── fonts/          # Шрифты (пусто)
    └── images/         # Изображения (пусто)
```

## 🔧 Конфигурация

### Подключение к backend

По умолчанию frontend подключается к `http://localhost:8000`.

Для изменения бэкэнда добавьте в `index.html` перед загрузкой `main.js`:

```html
<script>
  window.API_BASE_URL = 'http://your-backend-url:8000';
</script>
<script src="main.js"></script>
```

## 📦 Зависимости

- **Leaflet 1.9.4** - для интерактивных карт (подгружается из CDN)
- **OpenStreetMap** - источник данных карт
- Vanilla JavaScript (без фреймворков)

## 🎨 Компоненты

### Карта
- Инициализация на центре Кирова (58.5967, 49.6074)
- Использует OpenStreetMap слой
- Масштабирование при отображении маршрута

### Боковая панель
- **Адреса**: начало и конец маршрута
- **Промежуточные точки**: добавление/удаление динамически
- **Результаты**: расстояние, время, количество точек, сегменты

### Маршрут
- Отображение полилинией на карте
- Красный цвет если проходит через барьеры
- Синий цвет если маршрут чистый
- Маркеры для каждой точки (старт 📍, финиш 🏁, промежуточные 🔹)

## 🔗 API интеграция

Frontend использует `api.js` для общения с backend:

```javascript
import { calculateRoute, calculateMultiPointRoute } from './api.js';

// Простой маршрут
const route = await calculateRoute('Адрес 1', 'Адрес 2', []);

// Маршрут через несколько точек
const multiRoute = await calculateMultiPointRoute(['Адрес 1', 'Адрес 2', 'Адрес 3']);
```

## 🚀 Production развёртывание

### Статический хостинг (например, Netlify, Vercel)

1. Загрузите содержимое папки `src/` и `public/`
2. Установите переменную окружения `API_BASE_URL` для backend URL
3. Обновите ссылку на backend в `index.html` или передайте через переменные окружения

### Через веб-сервер

```bash
# Nginx
location / {
  root /path/to/voyx/frontend;
  try_files $uri /index.html;
}
```

## 📝 Разработка

### Структура main.js

- Инициализация карты Leaflet
- Функции для работы с точками (addWaypoint, removeWaypoint)
- Функция calculateRoute - основная логика
- Обработчики ошибок и валидация

### Добавление новых функций

1. Добавьте функцию в `main.js`
2. Используйте `api.js` для вызова backend
3. Обновляйте UI элементы (карта, результаты)

## 🐛 Troubleshooting

### "Cannot reach backend" ошибка
- Проверьте что backend запущен на `http://localhost:8000`
- Проверьте что CORS включен на backend
- Откройте DevTools (F12) и посмотрите Network вкладку

### Карта не загружается
- Проверьте интернет соединение (нужен доступ к CDN Leaflet)
- Проверьте что нет CORS ошибок в консоли

### Ошибка "Cannot read properties of undefined"
- Проверьте что backend возвращает правильный формат JSON
- Откройте DevTools и посмотрите ответ сервера

## 📝 Лицензия

MIT
