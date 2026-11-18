# Покрытие исходного тестового задания

| Пункт из ТЗ | Реализация | Где проверять |
|---|---|---|
| Главная — лента видео с превью | Адаптивная лента, сортировка по недавним/популярным, карточки с thumbnail и метаданными | `frontend/assets/app.js` → `renderHome`; `GET /api/videos` |
| Просмотр — плеер, лайки, комментарии | HTML5 player, byte-range streaming, toggle like, список/создание/удаление комментариев | `renderWatch`; `GET /api/videos/{id}/stream`; `POST /api/videos/{id}/like`; `/comments` |
| Канал — видео, плейлисты, подписка | Страница канала, публичные видео/плейлисты, переключение подписки | `renderChannel`; `app/api/channels.py` |
| Поиск по названию | Поиск по title и description | `renderSearch`; `GET /api/search` |
| Загрузка — файл, прогресс, метаданные | Multipart upload, XHR progress, title/description/visibility, размер и проверка сигнатуры | `renderUpload`; `POST /api/videos/upload` |
| Вход и регистрация | Регистрация, login/logout, Argon2, JWT и HttpOnly cookie | `app/api/auth.py`; `app/core/security.py` |
| Модерация — жалобы и скрытие видео | Создание жалобы, очередь, close/dismiss, hide/restore | `renderModeration`; `app/api/moderation.py` |
| Python + FastAPI | Backend API, server-rendered static hosting | `app/main.py`; `requirements.txt` |
| PostgreSQL | Реляционная схема SQLAlchemy и Alembic | `app/models.py`; `alembic/versions/0001_initial_schema.py` |
| Swagger `/docs` | Автогенерируемый OpenAPI UI | `http://localhost:8000/docs` |
| Объектное хранилище — загрузка, хранение, раздача | RustFS/S3, object keys, original/processed/thumbnail, проксирование приватных объектов через API | `app/services/storage.py`; `app/tasks/video_processing.py` |
| Роли user/moderator/admin | Роль хранится на пользователе; серверные dependency checks | `app/core/dependencies.py`; demo accounts |
| Приватные видео | Owner ACL + таблица `video_access`; проверка metadata/stream/thumbnail | `VideoAccess`; `/api/videos/{id}/access`; `get_visible_video` |
| Деплой одной командой на Ubuntu | `deploy.sh` при необходимости устанавливает Docker/Compose, генерирует `.env`, собирает и запускает Compose, ждёт healthcheck | `./deploy.sh` |
| Git-репозиторий с историей | `.git` включён в архив, отдельные коммиты по этапам | `git log --oneline` |
| README, docs, автотесты, демоданные | README, архитектура, БД, API, безопасность, тест-план, Alembic и seed-скрипт | `README.md`, `docs/`, `tests/`, `app/seed.py` |
| Исходные диалоги ИИ в оригинальном формате | Нужны реальные экспорты инструментов, в архив не подставлены вымышленные файлы | `ai_artifacts/README.md` |
| Агентная обвязка | Проектные инструкции и правила для AGENTS/Cursor/Claude Code | `AGENTS.md`, `CLAUDE.md`, `.cursor/`, `.claude/` |

## Что было проверено в среде сборки

- `pytest -q`: 10 passed;
- `python -m compileall -q app tests alembic`: успешно;
- `node --check frontend/assets/app.js`: успешно;
- YAML parse `compose.yaml`: успешно; обнаружены все 5 сервисов;
- `app.openapi()`: схема генерируется, 26 API paths;
- `alembic upgrade head` на отдельной SQLite-БД: успешно, созданы 9 прикладных таблиц и служебная `alembic_version`;
- FFmpeg: генерация демо-файла, ffprobe duration, перекодирование H.264/AAC и создание JPEG-превью: успешно.

**Ограничение проверки:** в среде сборки отсутствует Docker Engine/Compose, поэтому реальные `docker compose up`, интеграция API с PostgreSQL/Redis/RustFS и полный браузерный сценарий не были запущены здесь. Compose-конфигурация синтаксически разобрана, но окончательная интеграционная проверка должна быть выполнена на Ubuntu командой `./deploy.sh`.
