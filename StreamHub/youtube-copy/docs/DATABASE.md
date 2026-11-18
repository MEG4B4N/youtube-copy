# Проектирование базы данных

Схема создаётся Alembic-миграцией `0001_initial`. Все основные таблицы используют целочисленный PK; даты хранятся как UTC timestamps. Удаление пользователя каскадно удаляет принадлежащие ему видео и зависимые записи. Видео хранит только object keys, а не BLOB.

## Таблицы и связи

| Таблица | Назначение | Ключевые связи и ограничения |
|---|---|---|
| `users` | Аккаунт и роль | `username` и `email` уникальны; `role` = user/moderator/admin |
| `videos` | Метаданные и состояние медиаресурса | `owner_id → users`; visibility public/private; status processing/ready/failed |
| `video_access` | Персональные разрешения на приватные видео | `video_id → videos`, `user_id → users`, уникальная пара |
| `likes` | Лайки | Уникальная пара `(video_id, user_id)` |
| `comments` | Комментарии | `video_id → videos`, `user_id → users` |
| `subscriptions` | Подписка пользователя на канал | `subscriber_id` и `channel_id → users`, уникальная пара |
| `playlists` | Плейлист канала | `owner_id → users`, visibility public/private |
| `playlist_videos` | Позиция видео в плейлисте | Уникальная пара `(playlist_id, video_id)` |
| `reports` | Жалобы и решение модератора | `video_id`, `reporter_id`, nullable `moderator_id`; status open/resolved/dismissed |

## Кардинальности

- `users 1—N videos`;
- `videos 1—N comments`, `videos 1—N likes`, `videos 1—N video_access`;
- `users N—N users` через `subscriptions` (подписчик → канал);
- `users 1—N playlists`, `playlists N—N videos` через `playlist_videos`;
- `videos 1—N reports`, пользователь создаёт множество жалоб.

## Индексы

Индексы заданы для внешних ключей и частых условий выборки: username/email, owner_id, visibility/status/is_hidden/created_at, comment video/date, report status, subscription pair и уникальные пары связующих таблиц. PostgreSQL полнотекстовый индекс не подключён; поиск использует `ILIKE` по title/description, достаточный для учебного объёма.

## Важные правила целостности

- Повторный лайк и повторная подписка блокируются уникальными ограничениями.
- Повторное добавление того же видео в плейлист блокируется уникальной парой.
- Одно и то же персональное разрешение на видео не дублируется.
- Внешние ключи зависимых сущностей настроены с `ON DELETE CASCADE`, а удалённый модератор в жалобе становится `NULL`.
