# Реестр ключей твина: что даёт каждый ключ, где его взять и куда положить.
#
#   python3 -m twin.keys              # что уже есть, чего не хватает
#   python3 -m twin.keys --md         # тот же реестр как docs/twin_keys.md
#
# ГДЕ ЛЕЖАТ КЛЮЧИ. Два места и ни одного больше:
#   1) переменная окружения (TERRA_OPENSKY_ID и т. п.) — для CI и разовых команд;
#   2) файл twin/.keys.json — он в .gitignore, в репозиторий не попадёт.
# В коде, в данных сцены и в собранной странице ключей нет никогда: страница
# спрашивает браузерные ключи (Google) у пользователя и держит их в localStorage
# этого браузера. twin.doctor обыскивает исходники, сцену и страницу на предмет
# похожего на ключ и валит сборку, если найдёт.
#
# ПОЧЕМУ БРАУЗЕРНЫЙ КЛЮЧ — ОСОБЫЙ СЛУЧАЙ. Ключ, которым страница ходит к Google,
# по своей природе виден тому, кто открыл страницу. Спрятать его нельзя — можно
# только ОГРАНИЧИТЬ: привязать к своему домену (HTTP referrer), включить ровно
# те API, что нужны, и поставить потолок расходов. Поэтому в нашей странице
# ключ вводит сам зритель и он остаётся у него; в выложенный файл мы не кладём
# ничего.

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

KEYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".keys.json")


@dataclass(frozen=True)
class Key:
    name: str                 # короткое имя: python3 -m twin.keys показывает его
    env: str                  # переменная окружения
    title: str
    unlocks: str              # что это даёт ИМЕННО твину
    signup: str               # где заводить
    cost: str
    steps: tuple[str, ...]
    where: str = "ingest"     # ingest — у нас на машине; browser — у зрителя
    status: str = "planned"   # wired — источник уже читает ключ; planned — ещё нет
    group: str = ""
    extra_env: tuple[str, ...] = field(default_factory=tuple)
    # ГЛАВНЫЙ признак: требует ли регистрация платёжную карту. Всё, что двигает
    # твин вперёд, доступно БЕЗ карты; карту просит ровно один поставщик.
    card: bool = False


REGISTRY: tuple[Key, ...] = (
    # ── воздух и орбита ──────────────────────────────────────────────────────
    Key(
        name="opensky", env="TERRA_OPENSKY_ID", extra_env=("TERRA_OPENSKY_SECRET",),
        group="Воздух и орбита",
        title="OpenSky Network",
        unlocks="История полётов, а не только текущий кадр: треки бортов за "
                "прошедшие сутки и месяцы. Наш живой слой (adsb.lol) знает "
                "только «сейчас» — с OpenSky можно проигрывать вчерашний день "
                "и сверять прогнозы движения с тем, что вышло.",
        signup="https://opensky-network.org/ → Sign up, затем Account → "
               "API client (выдаёт client_id и client_secret, OAuth2)",
        cost="бесплатно для некоммерческого использования; лимит запросов "
             "выше у зарегистрированных",
        steps=(
            "Завести учётную запись на opensky-network.org",
            "В личном кабинете создать API client — получить client_id и secret",
            "python3 -m twin.keys --set opensky <client_id>",
            "python3 -m twin.keys --set opensky_secret <client_secret>",
        ),
    ),
    Key(
        name="spacetrack", env="TERRA_SPACETRACK_USER",
        extra_env=("TERRA_SPACETRACK_PASS",),
        group="Воздух и орбита",
        title="Space-Track.org",
        unlocks="Полный каталог объектов на орбите и АРХИВ элементов: небо над "
                "городом можно отмотать на любую дату. CelesTrak (без ключа) "
                "даёт только свежие элементы.",
        signup="https://www.space-track.org/auth/createAccount",
        cost="бесплатно, учётная запись обязательна",
        steps=(
            "Зарегистрироваться, подтвердить почту",
            "python3 -m twin.keys --set spacetrack <логин>",
            "python3 -m twin.keys --set spacetrack_pass <пароль>",
        ),
    ),

    # ── земля и вода ─────────────────────────────────────────────────────────
    Key(
        name="fivetheleven", env="TERRA_511_TOKEN",
        group="Земля и вода",
        title="511.org (Bay Area)",
        unlocks="ЖИВОЙ ОБЩЕСТВЕННЫЙ ТРАНСПОРТ: GTFS-Realtime по каждому "
                "перевозчику Залива (Muni, BART, AC Transit…) — положение "
                "каждого вагона и автобуса раз в 15–30 с. Это то, чего в "
                "городе больше всего движется, и его нет ни у кого без ключа.",
        signup="https://511.org/open-data/token",
        cost="бесплатно, форма имя+почта, токен приходит письмом сразу",
        steps=(
            "Заполнить форму на 511.org/open-data/token",
            "Забрать токен из письма",
            "python3 -m twin.keys --set fivetheleven <токен>",
        ),
    ),
    Key(
        name="aisstream", env="TERRA_AISSTREAM_KEY",
        group="Земля и вода",
        title="aisstream.io",
        unlocks="СУДА в заливе живьём (AIS по вебсокету): паромы, контейнеровозы, "
                "буксиры. Залив без судов — не залив.",
        signup="https://aisstream.io/ → вход через GitHub → API keys",
        cost="бесплатно",
        steps=(
            "Войти на aisstream.io через GitHub",
            "Создать API key",
            "python3 -m twin.keys --set aisstream <ключ>",
        ),
    ),

    # ── воздух, огонь, вода ──────────────────────────────────────────────────
    Key(
        name="airnow", env="TERRA_AIRNOW_KEY",
        group="Атмосфера и стихии",
        title="AirNow (EPA)",
        unlocks="Качество воздуха по часам — дымка и смог в кадре получают "
                "измеренную причину, а не художественную. В сезон пожаров это "
                "половина того, как выглядит небо над Заливом.",
        signup="https://docs.airnowapi.org/account/request/",
        cost="бесплатно",
        steps=(
            "Запросить ключ на docs.airnowapi.org/account/request/",
            "python3 -m twin.keys --set airnow <ключ>",
        ),
    ),
    Key(
        name="firms", env="TERRA_FIRMS_KEY",
        group="Атмосфера и стихии",
        title="NASA FIRMS",
        unlocks="Очаги пожаров со спутников (VIIRS/MODIS) почти в реальном "
                "времени — источник той самой дымки, и проверяемое событие "
                "для прогнозов.",
        signup="https://firms.modaps.eosdis.nasa.gov/api/map_key/",
        cost="бесплатно, MAP_KEY выдаётся по почте сразу",
        steps=(
            "Запросить MAP_KEY на firms.modaps.eosdis.nasa.gov/api/map_key/",
            "python3 -m twin.keys --set firms <ключ>",
        ),
    ),
    Key(
        name="openaq", env="TERRA_OPENAQ_KEY",
        group="Атмосфера и стихии",
        title="OpenAQ",
        unlocks="Тот же воздух, но по всему миру и с историей — пригодится, "
                "когда твин выйдет за пределы Залива.",
        signup="https://explore.openaq.org/register",
        cost="бесплатно",
        steps=(
            "Зарегистрироваться, забрать ключ в личном кабинете",
            "python3 -m twin.keys --set openaq <ключ>",
        ),
    ),

    # ── съёмка и рельеф ──────────────────────────────────────────────────────
    Key(
        name="opentopo", env="TERRA_OPENTOPO_KEY",
        group="Съёмка и рельеф",
        title="OpenTopography",
        unlocks="ЛИДАР 1 м (USGS 3DEP) вместо спутникового рельефа 30 м. Это "
                "прямое лекарство от известной болячки: Copernicus GLO-30 — "
                "поверхностная модель, она поднимает землю крышами. С 3DEP "
                "центр города встанет на настоящую землю.",
        signup="https://portal.opentopography.org/ → Register → My Account → "
               "API key",
        cost="бесплатно; крупные выборки — по квоте",
        steps=(
            "Завести учётную запись на portal.opentopography.org",
            "My Account → получить API key",
            "python3 -m twin.keys --set opentopo <ключ>",
        ),
    ),
    Key(
        name="earthdata", env="TERRA_EARTHDATA_USER",
        extra_env=("TERRA_EARTHDATA_PASS",),
        group="Съёмка и рельеф",
        title="NASA Earthdata Login",
        unlocks="Единый вход к архивам NASA: тепловые снимки поверхности "
                "(ECOSTRESS, 70 м) — независимая ПОВЕРКА нашего тепловизора, "
                "а не картинка; ночные огни VIIRS; исторические серии.",
        signup="https://urs.earthdata.nasa.gov/users/new",
        cost="бесплатно",
        steps=(
            "Зарегистрироваться на urs.earthdata.nasa.gov",
            "python3 -m twin.keys --set earthdata <логин>",
            "python3 -m twin.keys --set earthdata_pass <пароль>",
        ),
    ),
    Key(
        name="usgs_m2m", env="TERRA_USGS_USER", extra_env=("TERRA_USGS_TOKEN",),
        group="Съёмка и рельеф",
        title="USGS EarthExplorer (M2M API)",
        unlocks="ИСТОРИЧЕСКАЯ АЭРОФОТОСЪЁМКА с 1930-х и весь архив Landsat. "
                "Это подложка для прошлого: сегодня под ногами фотография "
                "2022 года, а в 1938-м должна быть фотография 1938-го.",
        signup="https://ers.cr.usgs.gov/register → затем запросить доступ к "
               "M2M API в профиле",
        cost="бесплатно; доступ к M2M подтверждают вручную (обычно за сутки)",
        steps=(
            "Зарегистрироваться на ers.cr.usgs.gov",
            "В профиле запросить Machine-to-Machine (M2M) access",
            "Сгенерировать application token",
            "python3 -m twin.keys --set usgs_m2m <логин>",
            "python3 -m twin.keys --set usgs_token <токен>",
        ),
    ),
    Key(
        name="copernicus", env="TERRA_CDSE_USER", extra_env=("TERRA_CDSE_PASS",),
        group="Съёмка и рельеф",
        title="Copernicus Data Space Ecosystem",
        unlocks="Sentinel-2 (10 м, свежий снимок каждые 5 дней) — СЕЗОННОСТЬ и "
                "изменения: зелень летом и зимой, новые стройки, выгоревшие "
                "склоны. NAIP снимают раз в два года, этого мало для «сейчас».",
        signup="https://dataspace.copernicus.eu/ → Register",
        cost="бесплатно",
        steps=(
            "Зарегистрироваться на dataspace.copernicus.eu",
            "python3 -m twin.keys --set copernicus <логин>",
            "python3 -m twin.keys --set copernicus_pass <пароль>",
        ),
    ),
    Key(
        name="mapillary", env="TERRA_MAPILLARY_TOKEN",
        group="Съёмка и рельеф",
        title="Mapillary",
        unlocks="Вторая уличная съёмка вдобавок к KartaView — гуще покрытие и "
                "готовая разметка объектов (знаки, столбы, деревья). Больше "
                "точек, где нашу геометрию можно поймать на вранье.",
        signup="https://www.mapillary.com/dashboard/developers",
        cost="бесплатно",
        steps=(
            "Войти на mapillary.com, открыть Developers → Register application",
            "Скопировать Client Token (MLY|…)",
            "python3 -m twin.keys --set mapillary <токен>",
        ),
    ),

    # ── Google ───────────────────────────────────────────────────────────────
    Key(
        name="google_maps", env="TERRA_GOOGLE_MAPS_KEY", where="browser",
        status="wired", card=True,
        group="Требует платёжную карту (можно не заводить)",
        title="Google Maps Platform (Street View Static + Map Tiles)",
        unlocks="Фотореалистичный слой целиком: снимок улицы из той самой "
                "точки, вид сверху плитками и фотограмметрия города "
                "3D-плитками. Единственное здесь, что стоит денег, — и "
                "единственное, что даёт настоящую фотореалистичность без "
                "генеративных выдумок.",
        signup="https://console.cloud.google.com/ → проект → APIs & Services",
        cost="ПЛАТНО и ТРЕБУЕТ ПРИВЯЗАННОЙ КАРТЫ: без биллинг-аккаунта ключ не "
             "выдаётся вовсе, даже под бесплатный лимит. Тарифы: "
             "https://developers.google.com/maps/documentation/tile/usage-and-billing "
             "Документация плиток: "
             "https://developers.google.com/maps/documentation/tile "
             "Слой написан и ждёт ключа, но твин без него полон: карту можно "
             "не заводить.",
        steps=(
            "Создать проект в console.cloud.google.com и привязать биллинг "
            "(тут и потребуется карта — если её не хочется, пропустите весь "
            "этот пункт реестра)",
            "Включить: Street View Static API, Map Tiles API",
            "Credentials → Create credentials → API key",
            "ОБЯЗАТЕЛЬНО ограничить ключ: Application restrictions → "
            "HTTP referrers → добавить свой адрес "
            "(bekzod25-terra-world.static.hf.space/*)",
            "ОБЯЗАТЕЛЬНО ограничить по API: только те два, что включили",
            "Поставить потолок расходов: Billing → Budgets & alerts",
            "Ключ НЕ класть в репозиторий: открыть twin.html и вписать его в "
            "поле «Google» на самой странице — он останется в вашем браузере",
        ),
    ),
    Key(
        name="cesium_ion", env="TERRA_CESIUM_TOKEN",
        group="Съёмка и рельеф",
        title="Cesium ion",
        unlocks="Мировой рельеф Cesium и хранилище готовых 3D-наборов. Отсюда "
                "же раздаются фотореалистичные плитки Google — но за них всё "
                "равно платит владелец ключа Google, так что обходным путём к "
                "ним это НЕ является.",
        signup="https://ion.cesium.com/signup",
        cost="бесплатный уровень без карты; плитки Google через ion всё равно "
             "считаются по тарифу Google",
        steps=(
            "Зарегистрироваться на ion.cesium.com",
            "Access Tokens → создать токен",
            "python3 -m twin.keys --set cesium_ion <токен>",
        ),
    ),

    # ── прошлое ──────────────────────────────────────────────────────────────
    Key(
        name="nhgis", env="TERRA_NHGIS_KEY",
        group="Прошлое",
        title="IPUMS NHGIS",
        unlocks="Перепись по десятилетиям с 1790 года и исторические границы. "
                "Сейчас жители твина расселены по переписи 2020; с NHGIS "
                "население можно отматывать назад вместе с домами — город "
                "1900 года получит своих жителей, а не сегодняшних.",
        signup="https://uma.pop.umn.edu/nhgis/user/new",
        cost="бесплатно, учётная запись; ключ в разделе API",
        steps=(
            "Завести учётную запись IPUMS",
            "Account → API keys → создать ключ",
            "python3 -m twin.keys --set nhgis <ключ>",
        ),
    ),

    # ── речь ─────────────────────────────────────────────────────────────────
    Key(
        name="anthropic", env="ANTHROPIC_API_KEY", where="browser",
        status="wired", card=True,
        group="Требует платёжную карту (можно не заводить)",
        title="Anthropic API",
        unlocks="Свободный разговор с жителями прямо из браузера — уже "
                "работает в игровом слое play.html; тот же путь годится "
                "жителям твина.",
        signup="https://console.anthropic.com/",
        cost="платно по счётчику",
        steps=(
            "Создать ключ в console.anthropic.com",
            "Вписать его в поле на странице игры — он остаётся в браузере",
        ),
    ),
)

# Порядок разделов при показе: сначала то, что берётся без карты, и внутри —
# от самого полезного твину к вспомогательному. Карточные — последними, чтобы
# было видно: без них список всё равно длинный.
GROUP_ORDER = (
    "Съёмка и рельеф",
    "Земля и вода",
    "Воздух и орбита",
    "Атмосфера и стихии",
    "Прошлое",
    "Требует платёжную карту (можно не заводить)",
)


def _ordered() -> list[Key]:
    return sorted(REGISTRY, key=lambda k: (GROUP_ORDER.index(k.group)
                                           if k.group in GROUP_ORDER else 99))


BY_NAME = {k.name: k for k in REGISTRY}
# вторые половинки пар логин/пароль: их тоже можно класть через --set
ALIASES = {
    "opensky_secret": "TERRA_OPENSKY_SECRET",
    "spacetrack_pass": "TERRA_SPACETRACK_PASS",
    "earthdata_pass": "TERRA_EARTHDATA_PASS",
    "usgs_token": "TERRA_USGS_TOKEN",
    "copernicus_pass": "TERRA_CDSE_PASS",
}


def _load_file() -> dict:
    if not os.path.exists(KEYS_FILE):
        return {}
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_file(data: dict) -> None:
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.chmod(KEYS_FILE, 0o600)


def env_of(name: str) -> str:
    if name in BY_NAME:
        return BY_NAME[name].env
    if name in ALIASES:
        return ALIASES[name]
    raise KeyError(f"неизвестный ключ: {name}; есть "
                   f"{', '.join(sorted(list(BY_NAME) + list(ALIASES)))}")


def get(name: str) -> str | None:
    """Ключ из окружения, иначе из twin/.keys.json, иначе None."""
    env = env_of(name)
    v = os.environ.get(env)
    if v:
        return v.strip()
    v = _load_file().get(env)
    return v.strip() if isinstance(v, str) and v.strip() else None


def require(name: str) -> str:
    """Ключ или внятный отказ с инструкцией, а не KeyError в середине сбора."""
    v = get(name)
    if v:
        return v
    k = BY_NAME.get(name)
    hint = ""
    if k:
        hint = (f"\n  {k.title}: {k.signup}"
                f"\n  положить: python3 -m twin.keys --set {name} <значение>"
                f"\n  или переменной окружения {k.env}")
    raise RuntimeError(f"нет ключа «{name}»{hint}")


def set_key(name: str, value: str) -> str:
    env = env_of(name)
    data = _load_file()
    data[env] = value.strip()
    _save_file(data)
    return env


# Приватный склад секретов проекта — тот же, где уже лежат токены GitHub и HF.
# Контейнер, в котором работает Фейбл, живёт недолго и умирает вместе с диском;
# складывать ключи туда бессмысленно, а пересылать их в переписке — небезопасно
# (переписка пишется в журнал). Поэтому ключи кладутся ОДИН раз в приватный
# репозиторий, а сюда подтягиваются по требованию.
HF_SECRETS_REPO = "Bekzod25/terra-secrets"
HF_KEYS_PATH = "twin_keys.json"


def template() -> str:
    """Пустой бланк для приватного склада: заполнить и положить туда."""
    blank = {}
    for k in REGISTRY:
        if k.where == "browser":
            continue          # браузерные ключи вводятся на самой странице
        blank[k.env] = ""
        for e in k.extra_env:
            blank[e] = ""
    return json.dumps(blank, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def pull_hf(token: str | None = None) -> tuple[int, str]:
    """Забрать бланк с ключами из приватного репозитория в twin/.keys.json.

    Токен HF берётся из HF_TOKEN/HUGGINGFACE_TOKEN. Пустые значения не
    затирают уже имеющиеся: бланк можно заполнять по частям.
    """
    token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError("нет HF_TOKEN в окружении — без него приватный "
                           "склад не открыть")
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(repo_id=HF_SECRETS_REPO, filename=HF_KEYS_PATH,
                           repo_type="model", token=token)
    with open(path, "r", encoding="utf-8") as f:
        remote = json.load(f)
    data = _load_file()
    added = 0
    for env, val in sorted(remote.items()):
        if not isinstance(val, str) or not val.strip():
            continue
        if data.get(env) != val.strip():
            data[env] = val.strip()
            added += 1
    _save_file(data)
    return added, KEYS_FILE


def status() -> list[dict]:
    out = []
    for k in _ordered():
        have = get(k.name) is not None
        second = all(os.environ.get(e) or _load_file().get(e) for e in k.extra_env)
        out.append({"name": k.name, "title": k.title, "have": have,
                    "complete": have and (second or not k.extra_env),
                    "where": k.where, "status": k.status, "group": k.group,
                    "card": k.card})
    return out


def free_count() -> tuple[int, int]:
    """Сколько ключей берётся без платёжной карты — и сколько всего."""
    return sum(1 for k in REGISTRY if not k.card), len(REGISTRY)


def _markdown() -> str:
    """Тот же реестр как документ, чтобы описание и код не разъезжались."""
    L = ["# Keys the twin can use",
         "",
         "Generated by `python3 -m twin.keys --md` — edit `twin/keys.py`, not this",
         "file, or the two will drift apart.",
         "",
         "Everything the twin does today runs on **keyless** sources. Every key",
         "below buys a specific new capability, named in its row. Nothing here is",
         "required to build or run the twin.",
         "",
         "**No payment card is needed for any of it except Google.** Of the "
         f"{len(REGISTRY)} providers listed, {sum(1 for k in REGISTRY if not k.card)}",
         "hand out a key against an email address and nothing else. Google Maps",
         "Platform refuses to issue a key at all without a billing account, and",
         "Anthropic bills per token — those two are marked, kept in their own",
         "section, and are entirely optional: the twin's realism roadmap does not",
         "route through either of them.",
         "",
         "## Where keys live (and why never in git)",
         "",
         "| | |",
         "|---|---|",
         "| **Ingest keys** (our machine) | environment variable, or `twin/.keys.json` — which is gitignored and written with mode 600 |",
         "| **Browser keys** (Google, Anthropic) | typed into the page by whoever opens it, kept in that browser's `localStorage`, never serialised into the HTML or the scene |",
         "| **In the repository** | never. `twin.doctor` greps the sources, the compiled scene and the built page for key-shaped strings and fails the build if it finds one |",
         "",
         "A browser key is inherently visible to whoever opens the page — that is",
         "what it means for a browser to send it. It cannot be hidden, only",
         "**restricted**: bind it to your own domain (HTTP referrer), enable only",
         "the APIs you actually call, and set a spending cap. That is why our page",
         "asks the viewer for the key instead of shipping one.",
         "",
         "```bash",
         "python3 -m twin.keys                    # what is present, what is missing",
         "python3 -m twin.keys --set 511 <token>  # store one (never printed back)",
         "python3 -m twin.keys --template         # blank form for the private store",
         "python3 -m twin.keys --pull-hf          # fetch the filled form (needs HF_TOKEN)",
         "python3 -m twin.keys --md               # regenerate this document",
         "```",
         "",
         "## Handing keys to the agent",
         "",
         "Never in chat. A conversation is written to a session log on disk, and a",
         "key that lands there cannot be taken back — it can only be revoked. Two",
         "routes carry a key to a cloud session without passing through the",
         "transcript:",
         "",
         "1. **Environment variables on the environment itself.** Set them where",
         "   the remote environment is configured; every session starts with them",
         "   already in `os.environ`, and nothing touches the repository. Best for",
         "   keys you expect to keep.",
         f"2. **The project's private store** — `{HF_SECRETS_REPO}`, the same",
         f"   private repo that already holds the GitHub and Hugging Face tokens.",
         f"   Run `python3 -m twin.keys --template`, fill the blanks, upload it as",
         f"   `{HF_KEYS_PATH}`, and a session with `HF_TOKEN` in its environment",
         "   pulls it with `--pull-hf`. Containers are ephemeral; the private repo",
         "   is not, so this survives the session that created it.",
         "",
         "If a key does end up somewhere it should not — in a message, a commit, a",
         "screenshot — treat it as burned: revoke it at the provider and issue a new",
         "one. Every provider in this document lets you do that in one click.",
         ""]
    order = _ordered()
    seen = []
    for k in order:
        if k.group not in seen:
            seen.append(k.group)
    for g in seen:
        L += [f"## {g}", ""]
        for k in order:
            if k.group != g:
                continue
            mark = "wired" if k.status == "wired" else "not wired yet"
            L += [f"### {k.title}",
                  "",
                  ("**Requires a payment card.** Optional — skip it and nothing "
                   "else breaks." if k.card else "**No payment card.** Email "
                   "address and a form."),
                  "",
                  f"**Unlocks.** {k.unlocks}",
                  "",
                  f"- Sign up: {k.signup}",
                  f"- Cost: {k.cost}",
                  f"- Stored as: `{k.env}`"
                  + (f" (+ `{'`, `'.join(k.extra_env)}`)" if k.extra_env else ""),
                  f"- Lives: {'in the viewer''s browser' if k.where == 'browser' else 'on our machine'}"
                  f" · code path: {mark}",
                  "",
                  "Steps:",
                  ""]
            L += [f"{i}. {s}" for i, s in enumerate(k.steps, 1)]
            L += [""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Ключи твина: что есть, где взять")
    ap.add_argument("--set", nargs=2, metavar=("ИМЯ", "ЗНАЧЕНИЕ"),
                    help="положить ключ в twin/.keys.json (в git не попадёт)")
    ap.add_argument("--md", action="store_true",
                    help="напечатать реестр как markdown (docs/twin_keys.md)")
    ap.add_argument("--template", action="store_true",
                    help="бланк для приватного склада: заполнить и положить "
                         f"в {HF_SECRETS_REPO}/{HF_KEYS_PATH}")
    ap.add_argument("--pull-hf", action="store_true",
                    help="забрать заполненный бланк из приватного склада "
                         "(нужен HF_TOKEN в окружении)")
    args = ap.parse_args()

    if args.md:
        sys.stdout.write(_markdown())
        return 0
    if args.template:
        sys.stdout.write(template())
        return 0
    if args.pull_hf:
        try:
            n, path = pull_hf()
        except Exception as e:
            print(f"не вышло: {type(e).__name__}: {e}")
            return 2
        print(f"взято ключей: {n} -> {path}")
        return 0
    if args.set:
        name, value = args.set
        try:
            env = set_key(name, value)
        except KeyError as e:
            print(e)
            return 2
        print(f"положил {name} -> {KEYS_FILE} (переменная {env}); "
              f"файл в .gitignore, права 600")
        return 0

    rows = status()
    have = [r for r in rows if r["complete"]]
    free, total = free_count()
    print(f"ключей в реестре {total}, готово {len(have)}")
    print(f"без платёжной карты: {free} из {total} — карту просит только Google "
          f"(и Anthropic для речи); твин полон и без них\n")
    group = None
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            print(f"── {group}")
        mark = "[v]" if r["complete"] else ("[~]" if r["have"] else "[ ]")
        notes = []
        if r["card"]:
            notes.append("НУЖНА КАРТА")
        if r["where"] == "browser":
            notes.append("у зрителя в браузере")
        if not r["complete"] and r["status"] != "wired":
            notes.append("источник ещё не написан")
        print(f"  {mark} {r['name']:<14} {r['title']}"
              + (f"   ({' · '.join(notes)})" if notes else ""))
    print("\nчто и где брать: docs/twin_keys.md "
          "(или python3 -m twin.keys --md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
