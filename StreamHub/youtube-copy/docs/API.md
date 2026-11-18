# API (основные маршруты)

Полная интерактивная спецификация доступна в `/docs` после запуска.

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| POST | `/api/auth/register` | публичный | Регистрация и выдача cookie |
| POST | `/api/auth/login` | публичный | Вход |
| POST | `/api/auth/logout` | публичный | Очистка cookie |
| GET | `/api/auth/me` | user | Текущий аккаунт |
| GET | `/api/videos` | публичный | Главная лента (`sort=recent|popular`) |
| GET | `/api/search?q=...` | публичный | Поиск видео по тексту |
| POST | `/api/videos/upload` | user | Multipart-загрузка и запуск обработки |
| GET | `/api/videos/{id}` | public / owner / ACL | Метаданные |
| GET | `/api/videos/{id}/stream` | public / owner / ACL | Видео с поддержкой Range |
| GET | `/api/videos/{id}/thumbnail` | public / owner / ACL | Превью |
| POST | `/api/videos/{id}/like` | user | Переключить лайк |
| GET/POST | `/api/videos/{id}/comments` | чтение публичное, создание user | Комментарии |
| POST | `/api/videos/{id}/report` | user | Создать жалобу |
| GET/POST/DELETE | `/api/videos/{id}/access` | owner | Список / выдача / отзыв доступа |
| GET | `/api/channels/{username}` | public | Канал и публичные видео/плейлисты |
| POST | `/api/channels/{username}/subscribe` | user | Переключить подписку |
| POST | `/api/playlists` | user | Создать плейлист |
| GET | `/api/playlists/{id}` | public / owner | Просмотр плейлиста |
| POST | `/api/playlists/{id}/videos` | owner | Добавить видео в плейлист |
| GET | `/api/moderation/reports` | moderator/admin | Список жалоб |
| PATCH | `/api/moderation/reports/{id}` | moderator/admin | Закрыть/отклонить жалобу, опционально скрыть видео |
| POST | `/api/moderation/videos/{id}/hide` | moderator/admin | Скрыть видео |
| POST | `/api/moderation/videos/{id}/restore` | moderator/admin | Восстановить видео |

Входные JSON-схемы и ответы описаны в OpenAPI. На frontend авторизация использует HttpOnly cookie; `access_token` дополнительно возвращается в JSON для проверки через Swagger Authorize/клиентов.

## Личная библиотека

| Метод | Маршрут | Назначение | Авторизация |
|---|---|---|---|
| GET | `/api/me/videos` | Опубликованные видео текущего пользователя, в том числе приватные собственные ролики | Да |
| GET | `/api/me/liked` | Доступные пользователю видео, которым он поставил лайк | Да |
| GET | `/api/me/playlists` | Собственные плейлисты, включая приватные | Да |
| GET | `/api/subscriptions/feed` | Последние публичные видео каналов из подписок | Да |
| GET | `/api/videos/{video_id}/download` | Потоковое скачивание MP4 с проверкой доступа | Необязательная; приватные видео требуют разрешение |

История просмотров, «Смотреть позже» и список инициированных загрузок — браузерные списки в `localStorage`; они не являются синхронизируемыми серверными данными.
