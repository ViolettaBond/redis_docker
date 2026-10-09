import time
import uuid
import redis
from flask import Flask, request, redirect, url_for, render_template

app = Flask(__name__)

store = redis.Redis(host='redis', port=6379, db=0)

PROFILE_CACHE_SEC = 45
LOG_MAX = 12
THROTTLE_MAX = 6
THROTTLE_SEC = 90


def write_log(uid, text):
    """Пишем событие в историю пользователя и обрезаем до LOG_MAX."""
    key = f"log:{uid}"
    stamp = time.strftime("%d.%m %H:%M:%S")
    store.lpush(key, f"[{stamp}] {text}")
    store.ltrim(key, 0, LOG_MAX - 1)


def throttle(uid):
    """
    Комбинированный rate limit:
    - если ключа нет — создаём с TTL через SET NX EX
    - иначе INCR
    Возвращает True, если запрос разрешён.
    """
    key = f"throttle:{uid}"
    pipe = store.pipeline()
    pipe.set(key, 0, nx=True, ex=THROTTLE_SEC)
    pipe.incr(key)
    _, count = pipe.execute()
    return count <= THROTTLE_MAX


def bump_counter(metric, value):
    """Увеличить HyperLogLog-счётчик."""
    store.pfadd(f"hll:{metric}", value)


def read_counter(metric):
    """Прочитать HyperLogLog-счётчик."""
    return store.pfcount(f"hll:{metric}")



@app.route('/')
def home():
    """Главная: список + аналитика."""
    profiles = []
    for raw in store.scan_iter("u:*"):
        name = raw.decode()
        tail = name.split(":", 1)[1] if ":" in name else ""
        if tail.isdigit():
            h = store.hgetall(raw)
            profiles.append({
                "uid": tail,
                "name": h.get(b"name", b"").decode(),
                "email": h.get(b"email", b"").decode(),
            })

    profiles.sort(key=lambda p: int(p["uid"]))

    return render_template(
        "index.html",
        profiles=profiles,
        hll_visits=read_counter("visits"),
        hll_users=read_counter("users"),
    )


@app.route('/new', methods=['POST'])
def create_profile():
    """Создание профиля. ID выдаёт сам Redis через INCR."""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()

    if not name or not email:
        return redirect(url_for("home"))

    uid = store.incr("users:seq")
    ukey = f"u:{uid}"

    store.hset(ukey, mapping={
        "name": name,
        "email": email,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token": uuid.uuid4().hex[:8],
    })

    # сброс возможного кэша
    store.delete(f"cache:u:{uid}")

    bump_counter("users", f"u-{uid}")
    write_log(uid, "Профиль создан")

    return redirect(url_for("show_profile", uid=uid))


@app.route('/u/<uid>')
def show_profile(uid):
    """Профиль с кэшем и throttle."""
    if not uid.isdigit():
        return redirect(url_for("home"))

    if not throttle(uid):
        left = store.ttl(f"throttle:{uid}")
        return (
            f"<h1>Слишком часто</h1>"
            f"<p>Осталось ждать {left} сек.</p>"
            f"<a href='/'>На главную</a>",
            429,
        )

    ckey = f"cache:u:{uid}"

    snapshot = store.get(ckey)
    if snapshot:
        origin = "CACHE"
        payload = snapshot.decode()
    else:
        raw = store.hgetall(f"u:{uid}")
        if not raw:
            return (
                f"<h1>Профиль {uid} не найден</h1>"
                f"<a href='/'>На главную</a>",
                404,
            )

        payload = " · ".join(
            f"{k.decode()}={v.decode()}" for k, v in sorted(raw.items())
        )
        store.set(ckey, payload, ex=PROFILE_CACHE_SEC)
        origin = "REDIS-HASH"
        write_log(uid, "Открыт профиль")

    return render_template(
        "profile.html",
        uid=uid,
        payload=payload,
        origin=origin,
        ttl=store.ttl(ckey),
        events=[e.decode() for e in store.lrange(f"log:{uid}", 0, -1)],
    )


@app.route('/hit/<ip>')
def track_visit(ip):
    """Симуляция визита — HyperLogLog."""
    bump_counter("visits", ip)
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
