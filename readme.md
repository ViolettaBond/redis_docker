# Redis Demo — Python + Flask + Redis

Учебный проект: 5 механик Redis в одном приложении.

| Механика                     | Redis-структура   |
| ---------------------------- | ----------------- |
| Профили пользователей        | **Hash**          |
| Кэш профиля (45 сек)         | **String + TTL**  |
| История событий (12 записей) | **List + LTRIM**  |
| Уникальные визиты            | **HyperLogLog**   |
| Rate limit                   | **INCR + EXPIRE** |

---

## 📦 Стек

- Python 3.12, Flask 3.0, redis-py 5.0
- Redis 7
- Docker + Docker Compose

---

## 📁 Структура проекта

```
redis_project/
├── app.py                 # Flask + логика Redis
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── templates/
    ├── index.html
    └── profile.html
```

---

## 🚀 Быстрый старт

```bash
cd redis_project
docker compose up --build
```

Открыть: **http://localhost:5000**

Остановить:

```bash
docker compose down
```

Данные Redis сохраняются в volume `redis_data` — переживут `down`/`up`.

---

## 🧪 Проверка механик

**Hash — профили**

1. Форма «Новый профиль» → имя + email.
2. ID выдаётся автоматически (`INCR users:seq`).

**Кэш (String + TTL)**

1. Открыть профиль → бейдж **REDIS-HASH**.
2. Обновить → **CACHE**, TTL ~45 сек.
3. Через 45 сек → снова **REDIS-HASH**.

**История (List + LTRIM)**

1. Открывать профиль многократно.
2. Список не превышает 12 записей.

**HyperLogLog**

1. Кликать разные IP в «Симуляции визитов».
2. Уникальный IP → +1, повтор → без изменений.

**Rate limit**

1. Открыть профиль 7 раз подряд → **429 «Слишком часто»**.
2. Через 90 сек лимит сбрасывается.

---

## 🛠 Управление контейнерами

```bash
# Запуск в фоне
docker compose up -d --build

# Логи в реальном времени
docker compose logs -f

# Логи только app
docker compose logs -f app

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Остановка + удаление данных Redis
docker compose down -v
```

---

## 🔍 Redis CLI

```bash
# Все ключи
docker exec -it redis redis-cli KEYS '*'

# Только профили
docker exec -it redis redis-cli KEYS 'u:*'

# Профиль #1
docker exec -it redis redis-cli HGETALL u:1

# Кэш профиля #1
docker exec -it redis redis-cli GET cache:u:1

# TTL кэша профиля #1
docker exec -it redis redis-cli TTL cache:u:1

# История профиля #1
docker exec -it redis redis-cli LRANGE log:1 0 -1

# Уникальных IP
docker exec -it redis redis-cli PFCOUNT hll:visits

# Уникальных профилей
docker exec -it redis redis-cli PFCOUNT hll:users

# Активные throttle-ключи
docker exec -it redis redis-cli KEYS 'throttle:*'

# Размер базы (кол-во ключей)
docker exec -it redis redis-cli DBSIZE

# Полная очистка
docker exec -it redis redis-cli FLUSHDB
```

---

## 🐞 Отладка

```bash
# Внутрь app-контейнера
docker exec -it redis_app bash

# Проверка связи app → redis
docker exec -it redis_app python -c "import redis; r=redis.Redis(host='redis'); print(r.ping())"

# Внутрь redis-контейнера
docker exec -it redis sh
```

---

## 🔧 Параметры (`app.py`)

```python
PROFILE_CACHE_SEC = 45    # TTL кэша профиля
LOG_MAX = 12              # максимум записей в истории
THROTTLE_MAX = 6          # максимум запросов...
THROTTLE_SEC = 90         # ...за столько секунд
```

После изменения:

```bash
docker compose up -d --build
```

---

## 🌐 Маршруты

| Метод | URL         | Что делает                     |
| ----- | ----------- | ------------------------------ |
| GET   | `/`         | Главная: список + аналитика    |
| POST  | `/new`      | Создать профиль                |
| GET   | `/u/<uid>`  | Профиль (кэш + throttle)       |
| GET   | `/hit/<ip>` | Симуляция визита (HyperLogLog) |

---

## 🧩 Схема ключей Redis

```
users:seq         → INCR-счётчик uid
u:<id>            → Hash: name, email, created_at, token
cache:u:<id>      → String: кэш профиля (TTL 45 сек)
log:<id>          → List: последние 12 событий
throttle:<id>     → String: счётчик запросов (TTL 90 сек)
hll:visits        → HyperLogLog: уникальные IP
hll:users         → HyperLogLog: уникальные профили
```

---

## ❓ Частые проблемы

**Порт 5000 занят** — сменить в `docker-compose.yml`:

```yaml
ports:
    - '5001:5000'
```

**Порт 6379 занят** — убрать публикацию порта у `redis` (приложению он не нужен).

**Данные исчезают после `down`** — проверить, что в `docker-compose.yml` есть:

```yaml
volumes:
    - redis_data:/data

# в самом низу файла:
volumes:
    redis_data:
```

**Не растёт счётчик уникальных** — HyperLogLog считает только уникальные. Повтор IP/uid не увеличивает.

**429 «Слишком часто»** — сработал rate limit. Подождать 90 сек или уменьшить `THROTTLE_MAX` / `THROTTLE_SEC`.
