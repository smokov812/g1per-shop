# Universal Telegram Shop Bot

Универсальный Telegram-бот-магазин на `Python + aiogram 3 + SQLAlchemy`, подготовленный не только для MVP, но и для реального деплоя на VPS.

Проект поддерживает:

- каталог, корзину, заказы, админку
- `manual_crypto`
- `cryptomus`
- webhook + polling fallback для подтверждения оплаты
- `payments`, `payment_events`, `admin_audit_logs`
- db-backed rate limiting
- `/health` и `/ready`
- SQLite для локального старта и Postgres для production

## Что внутри

- [main.py](C:/smokov/g1per%20shop/main.py) — точка входа
- [bot/main.py](C:/smokov/g1per%20shop/bot/main.py) — polling, web server, startup checks, payment sync worker
- [bot/config.py](C:/smokov/g1per%20shop/bot/config.py) — конфиг и `.env`
- [bot/db/models.py](C:/smokov/g1per%20shop/bot/db/models.py) — модели БД
- [bot/db/repositories.py](C:/smokov/g1per%20shop/bot/db/repositories.py) — работа с БД
- [bot/webhooks/cryptomus.py](C:/smokov/g1per%20shop/bot/webhooks/cryptomus.py) — webhook, health, readiness
- [Dockerfile](C:/smokov/g1per%20shop/Dockerfile) — контейнеризация
- [docker-compose.prod.yml](C:/smokov/g1per%20shop/docker-compose.prod.yml) — production stack `bot + Postgres`
- [deploy/nginx.conf.example](C:/smokov/g1per%20shop/deploy/nginx.conf.example) — шаблон reverse proxy
- [.env.production.example](C:/smokov/g1per%20shop/.env.production.example) — production-конфиг

## Production-ready сейчас

Уже закрыто:

- отдельная таблица `payments`
- история `payment_events`
- idempotent обработка callback
- fallback polling статуса оплаты
- audit log админских действий
- db-backed anti-spam
- startup validation админ-чата
- startup validation платежного конфига
- readiness/health endpoints
- поддержка Postgres
- Docker и docker-compose для VPS

## Рекомендуемый режим сейчас

Пока у тебя нет одобренного API от Cryptomus, лучший production path такой:

- `PAYMENT_PROVIDER=manual_crypto`
- Postgres вместо SQLite
- запуск через Docker Compose
- reverse proxy перед ботом

Когда получишь доступы от Cryptomus, переключение будет через `.env`, без ломки архитектуры.

## Быстрый локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

## Деплой на VPS через Docker Compose

### 1. Подготовь сервер

Нужно:

- Linux VPS
- Docker
- Docker Compose
- домен или поддомен для webhook
- reverse proxy с HTTPS

### 2. Скопируй проект на сервер

```bash
git clone <your-repo>
cd g1per-shop
cp .env.production.example .env
```

### 3. Заполни `.env`

Минимум для ручной оплаты:

- `BOT_TOKEN`
- `ADMIN_ID`
- `CRYPTO_WALLET`
- `DATABASE_URL` уже зашит через compose на Postgres

Когда будет Cryptomus:

- `PAYMENT_PROVIDER=cryptomus`
- `CRYPTOMUS_MERCHANT_ID`
- `CRYPTOMUS_API_KEY`
- `CRYPTOMUS_WEBHOOK_ENABLED=true`
- `CRYPTOMUS_WEBHOOK_URL=https://your-domain.example/webhooks/cryptomus`
- `CRYPTOMUS_RETURN_URL=https://your-domain.example/return`
- `CRYPTOMUS_SUCCESS_URL=https://your-domain.example/success`

### 4. Запусти контейнеры

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 5. Проверь состояние

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
```

## Reverse proxy

Шаблон nginx лежит в [deploy/nginx.conf.example](C:/smokov/g1per%20shop/deploy/nginx.conf.example).

Если бот стоит за reverse proxy, в `.env` должно быть:

```env
TRUST_PROXY_HEADERS=true
```

Это нужно для корректного определения IP webhook-запросов.

## Health endpoints

Если `WEB_SERVER_ENABLED=true`, доступны:

- `GET /health` — процесс жив
- `GET /ready` — БД и runtime-конфиг готовы
- `POST /webhooks/cryptomus` — webhook CryptoMus, если включен

## Рекомендация по БД

Для локального старта можно оставить SQLite.

Для деплоя с реальными заказами и оплатами лучше использовать Postgres. В проекте это уже предусмотрено, и [docker-compose.prod.yml](C:/smokov/g1per%20shop/docker-compose.prod.yml) сразу запускает Postgres 16.

## Тесты

Сейчас есть базовые unit-тесты:

- [tests/test_validators.py](C:/smokov/g1per%20shop/tests/test_validators.py)
- [tests/test_cryptomus_signature.py](C:/smokov/g1per%20shop/tests/test_cryptomus_signature.py)
- [tests/test_payment_repository.py](C:/smokov/g1per%20shop/tests/test_payment_repository.py)
- [tests/test_rate_limit_repository.py](C:/smokov/g1per%20shop/tests/test_rate_limit_repository.py)

Запуск:

```powershell
python -m unittest discover -s tests -v
```

## Что еще остается после этого

Это уже не блокеры для деплоя, а следующий уровень hardening:

- timezone-aware UTC вместо `datetime.utcnow()`
- интеграционные тесты webhook/payment API
- alerting и внешний мониторинг на `/ready`
- Redis для FSM/rate-limit, если будет несколько инстансов
- backup policy для Postgres

## Источники по CryptoMus

- [Creating invoice](https://doc.cryptomus.com/merchant-api/payments/creating-invoice)
- [Payment information](https://doc.cryptomus.com/merchant-api/payments/payment-information)
- [Request format](https://doc.cryptomus.com/merchant-api/request-format)

## Деплой на Timeweb

Есть два рабочих сценария.

### Вариант 1. Timeweb App Platform

Используй этот вариант, если хочешь самый быстрый деплой из Git.

Что уже подготовлено в проекте:

- [docker-compose.yml](C:/smokov/g1per%20shop/docker-compose.yml) — совместим с App Platform
- [.env.timeweb.example](C:/smokov/g1per%20shop/.env.timeweb.example) — шаблон переменных
- [Dockerfile](C:/smokov/g1per%20shop/Dockerfile) — контейнер для приложения

Важно:

- для App Platform лучше использовать внешний Postgres
- SQLite для такого деплоя не советую
- в переменные окружения Timeweb нужно передать `DATABASE_URL` от Postgres

Шаги:

1. Создай PostgreSQL в Timeweb или используй внешний Postgres.
2. В панели Timeweb создай приложение из Git-репозитория.
3. Убедись, что платформа использует [docker-compose.yml](C:/smokov/g1per%20shop/docker-compose.yml).
4. Добавь переменные окружения по шаблону из [.env.timeweb.example](C:/smokov/g1per%20shop/.env.timeweb.example).
5. Для текущего режима поставь `PAYMENT_PROVIDER=manual_crypto`.
6. После деплоя проверь:
   - `/`
   - `/health`
   - `/ready`

### Вариант 2. Timeweb Cloud Server / VPS

Используй этот вариант, если хочешь полный контроль и свой Postgres в Docker.

Что уже подготовлено:

- [docker-compose.prod.yml](C:/smokov/g1per%20shop/docker-compose.prod.yml) — бот + Postgres
- [deploy/nginx.conf.example](C:/smokov/g1per%20shop/deploy/nginx.conf.example) — reverse proxy
- [.env.production.example](C:/smokov/g1per%20shop/.env.production.example) — production шаблон

Шаги:

1. Подними сервер в Timeweb.
2. Установи Docker и Docker Compose.
3. Склонируй проект.
4. Скопируй `.env.production.example` в `.env`.
5. Заполни `BOT_TOKEN`, `ADMIN_ID`, `CRYPTO_WALLET`.
6. Запусти:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

7. Подключи nginx или другой reverse proxy.
8. Проверь `http://127.0.0.1:8080/ready`.

### Что выбрать тебе сейчас

С учетом того, что у тебя пока ручная оплата и модерация Cryptomus еще идет:

- если нужен самый простой деплой: `Timeweb App Platform + внешний Postgres`
- если нужен самый надежный и управляемый вариант: `Timeweb VPS + docker-compose.prod.yml`

Я бы для магазина выбрал `Timeweb VPS`, потому что там меньше платформенных ограничений и проще потом без боли включить Cryptomus webhook.
