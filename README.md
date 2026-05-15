# Интеллектуальная библиотека

Веб-приложение и Telegram-бот для загрузки FB2-книг, извлечения терминов/определений, хранения глоссария и экспорта результатов.

## Стек

- Backend: Python 3.12+, Django, DRF, PostgreSQL, Celery, Redis, pymorphy3, razdel, lxml, reportlab
- Frontend: React + Vite + TypeScript
- Telegram: aiogram

## Структура

```text
project/
  backend/
    manage.py
    config/
    apps/
      accounts/
      books/
      telegram_bot/
    requirements.txt
  frontend/
    package.json
    vite.config.ts
    src/
  docker-compose.yml
  .env.example
  README.md
```

## Быстрый запуск

1. Скопируйте переменные окружения:

```bash
cp .env.example .env
```

2. Запустите PostgreSQL и Redis:

```bash
docker-compose up -d
```

3. Установите backend-зависимости:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

4. Примените миграции:

```bash
python manage.py migrate
```

5. Создайте суперпользователя:

```bash
python manage.py createsuperuser
```

6. Запустите Django API:

```bash
python manage.py runserver
```

7. Запустите Celery worker (в отдельном терминале):

```bash
cd backend
venv\Scripts\activate
celery -A config worker -l info
```

8. Запустите frontend:

```bash
cd frontend
npm install
npm run dev
```

9. Запустите Telegram-бота (в отдельном терминале):

```bash
cd backend
venv\Scripts\activate
python -m apps.telegram_bot.bot
```

## Важные переменные `.env`

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CORS_ALLOWED_ORIGINS`
- `TELEGRAM_BOT_TOKEN`

## Основные API

### Auth

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`

### Books

- `GET /api/books/`
- `POST /api/books/upload/`
- `POST /api/books/upload/confirm-rotation/`
- `GET /api/books/{id}/`
- `DELETE /api/books/{id}/`
- `POST /api/books/{id}/protect/`
- `POST /api/books/{id}/reanalyze/`
- `GET /api/books/{id}/glossary/`
- `PATCH /api/books/{id}/terms/{term_id}/edit/`
- `POST /api/books/{id}/terms/{term_id}/reset/`
- `GET /api/books/{id}/export/?format=csv|txt|pdf`

### Search/Stats

- `GET /api/search/?q=...`
- `GET /api/stats/`

## Telegram команды

- `/start`
- `/upload`
- `/my_books`
- `/glossary <название>`
- `/search <термин>`
- `/stats`
- `/protect <название>`
- `/export <название>`

## Особенности реализации

- Кастомный `User` с авторизацией по email + DRF Token Auth
- Глобальный кэш книг по `SHA-256` (`GlobalBookCache`)
- Ограничение 50 книг на пользователя + ротация с защитой
- Rule-based извлечение терминов (`это`, `называется`, `представляет собой`, `под ... понимается`, `является`)
- Асинхронный анализ книг через Celery
- Пользовательские правки определений без перезаписи оригинала (`UserTermEdit`)
- Экспорт глоссария в CSV/TXT/PDF
- Адаптивный frontend

## Тесты

Запуск:

```bash
cd backend
set USE_SQLITE=true
set CELERY_TASK_ALWAYS_EAGER=true
python manage.py test
```

Покрыты базовые сценарии:

- регистрация пользователя
- загрузка валидного FB2
- отказ для не-FB2
- отказ при превышении лимита размера
- SHA-256
- использование глобального кэша при повторной загрузке
- извлечение термина из `Инкапсуляция — это ...`
- глобальный поиск
- защита книги
- удаление незащищённой/запрет удаления защищённой
- ротация при 51-й книге
