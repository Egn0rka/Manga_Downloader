import os
import re
import time
import random
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, parse_qs, urlencode
from concurrent.futures import ThreadPoolExecutor
from DrissionPage import ChromiumPage, ChromiumOptions

from i18n import tr

LIB_SOCIAL_KEYWORDS = [
    "mangalib",
    "hentailib",
    "slashlib",
    "shlib",
    "yaoilib",
    "ranobelib",
    "animelib",
    "lib.social"
]

MADARA_KEYWORDS = [
    "manga18fx",
    "webtoon.xyz"
]

SENKURO_DOMAINS = [
    "senkuro.com",
    "senkognito.com"
]

MANGADEX_DOMAINS = [
    "mangadex.org"
]

MANGADEX_API_BASE = "https://api.mangadex.org"
MANGADEX_UUID_RE = re.compile(
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    re.IGNORECASE
)

SUPPORTED_KEYWORDS = LIB_SOCIAL_KEYWORDS + MADARA_KEYWORDS + SENKURO_DOMAINS + MANGADEX_DOMAINS
AGE_RESTRICTED_KEYWORDS = ["hentai", "slash", "shlib", "yaoi"]


def is_mangadex_site(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return any(netloc == d or netloc.endswith("." + d) for d in MANGADEX_DOMAINS)


def is_senkuro_site(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return any(netloc == d or netloc.endswith("." + d) for d in SENKURO_DOMAINS)


def is_madara_site(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return any(kw in netloc for kw in MADARA_KEYWORDS)


def is_supported_url(url: str) -> bool:
    if is_mangadex_site(url) or is_senkuro_site(url) or is_madara_site(url):
        return True
    netloc = urlparse(url).netloc.lower()
    return any(kw in netloc for kw in LIB_SOCIAL_KEYWORDS)


def is_chapter_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if is_mangadex_site(url):
        return bool(re.search(r'/chapter/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', path))
    if is_senkuro_site(url):
        return bool(re.search(r'/chapters/\d+', path))
    if is_madara_site(url):
        return "/chapter-" in path
    return "/read/" in url


def requires_age_verification(url: str) -> bool:
    if is_mangadex_site(url) or is_madara_site(url) or is_senkuro_site(url):
        return False
    domain = urlparse(url).netloc.lower()
    return any(k in domain for k in AGE_RESTRICTED_KEYWORDS)


def sanitize_folder_name(name: str) -> str:
    """Очищує назву папки (напр. нік команди перекладу) від заборонених символів ОС."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name or "").strip().rstrip('.')
    return cleaned if cleaned else "branch"


def init_browser(on_log=None):
    if on_log:
        on_log(tr("log_init_browser"), "info")
    co = ChromiumOptions()
    page = ChromiumPage(co)
    return page


def create_http_session(page, domain: str) -> requests.Session:
    """Створює HTTP-сесію з пулом з'єднань, автоповторами та куками з браузера."""
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    try:
        ua = page.run_js("return navigator.userAgent;") if page is not None else ""
    except Exception:
        ua = ""

    if not ua:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

    session.headers.update({
        "User-Agent": ua,
        "Referer": f"https://{domain}/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6"
    })

    if page is not None:
        try:
            for cookie in page.cookies():
                if isinstance(cookie, dict) and "name" in cookie and "value" in cookie:
                    session.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain", "")
                    )
        except Exception:
            pass

    return session


def bypass_age_warning(page):
    try:
        clicked = page.run_js(r"""
            const keys = ["мені є 18", "мне есть 18", "да, мне есть 18", "вход", "да"];
            const btns = Array.from(document.querySelectorAll('button'));
            for (const btn of btns) {
                const txt = (btn.innerText || "").trim().toLowerCase();
                if (txt && txt.length <= 35 && keys.some(k => txt === k || txt.includes("есть 18") || txt.includes("є 18"))) {
                    btn.click();
                    return true;
                }
            }
            return false;
        """)
        if clicked:
            time.sleep(1.2)
    except Exception:
        pass


def _make_chapter_entry(vol: str, ch_num: str, url: str, bid: str = "", team: str = "") -> dict:
    try:
        vol_float = float(vol)
    except ValueError:
        vol_float = 0.0

    try:
        num_float = float(ch_num)
    except ValueError:
        num_float = 0.0

    raw_team = (team or "").strip()
    is_default_team = not raw_team and not bid
    if raw_team:
        clean_team = raw_team
    elif bid:
        clean_team = tr("branch_numbered", bid=bid)
    else:
        clean_team = tr("default_branch")

    branch_key = f"bid:{bid}" if bid else f"team:{raw_team or 'default'}"

    return {
        'vol': vol,
        'vol_float': vol_float,
        'num': ch_num,
        'num_float': num_float,
        'bid': bid,
        'raw_team': raw_team,
        'is_default_team': is_default_team,
        'team': clean_team,
        'branch_key': branch_key,
        'url': url
    }


def resolve_team_display_name(ch: dict) -> str:
    """Повертає актуальну локалізовану назву перекладача для запису глави."""
    raw_team = ch.get("raw_team", "").strip()
    if raw_team:
        return raw_team
    bid = ch.get("bid", "")
    if bid:
        return tr("branch_numbered", bid=bid)
    return tr("default_branch")


# ==============================================================================
# ЛОГІКА ДЛЯ MANGADEX.ORG (ОФІЦІЙНИЙ REST API — ОРИГІНАЛЬНА ЯКІСТЬ /data/)
# ==============================================================================

def _extract_mangadex_uuid(url: str, segment: str = "") -> str:
    path = urlparse(url).path
    if segment:
        m = re.search(
            rf'/{re.escape(segment)}/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}})',
            path,
            re.IGNORECASE
        )
        if m:
            return m.group(1).lower()
    m_any = MANGADEX_UUID_RE.search(path)
    return m_any.group(1).lower() if m_any else ""


def _pick_mangadex_title(attributes: dict) -> str:
    if not isinstance(attributes, dict):
        return ""
    title_map = attributes.get("title") or {}
    if isinstance(title_map, dict):
        for lang in ("en", "ja-ro", "uk", "ru", "ja", "ko", "zh"):
            val = (title_map.get(lang) or "").strip()
            if val:
                return val
        for val in title_map.values():
            if isinstance(val, str) and val.strip():
                return val.strip()

    alt_titles = attributes.get("altTitles") or []
    if isinstance(alt_titles, list):
        for lang in ("en", "ja-ro", "uk", "ru"):
            for item in alt_titles:
                if isinstance(item, dict) and item.get(lang):
                    return str(item[lang]).strip()
    return ""


def _sleep_interruptible(seconds: float, stop_event: threading.Event | None = None):
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if stop_event and stop_event.is_set():
            return
        time.sleep(min(0.2, deadline - time.monotonic()))


def _mangadex_api_get(
    session: requests.Session,
    endpoint_url: str,
    params: dict | list | None = None,
    on_log=None,
    stop_event: threading.Event | None = None
) -> dict | None:
    headers = {
        "User-Agent": "MangaDownloader/1.0 (Python requests)",
        "Accept": "application/json",
        "Referer": None,
    }
    last_err = ""
    for attempt in range(4):
        if stop_event and stop_event.is_set():
            return None
        try:
            resp = session.get(endpoint_url, params=params, headers=headers, timeout=20)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After") or resp.headers.get("X-RateLimit-Retry-After")
                try:
                    wait_sec = max(2.0, min(float(retry_after), 30.0))
                except (TypeError, ValueError):
                    wait_sec = 3.0 * (attempt + 1)
                if on_log:
                    on_log(tr("log_mangadex_rate_limit", sec=int(round(wait_sec))), "warn")
                _sleep_interruptible(wait_sec, stop_event)
                continue
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}: {resp.text[:160].strip()}"
                if resp.status_code in (400, 403, 404):
                    break
                _sleep_interruptible(0.8 * (attempt + 1), stop_event)
                continue
            return resp.json()
        except Exception as e:
            last_err = str(e)
            if attempt < 3:
                _sleep_interruptible(0.8 * (attempt + 1), stop_event)

    if on_log and last_err:
        on_log(tr("log_mangadex_api_err", err=last_err), "error")
    return None


def _fetch_mangadex_manga_slug(
    session: requests.Session,
    url: str,
    manga_id: str,
    stop_event: threading.Event | None = None
) -> str:
    parts = [p for p in urlparse(url).path.strip('/').split('/') if p]
    if len(parts) >= 3 and parts[0].lower() == "title" and parts[2].strip():
        return sanitize_folder_name(parts[2].strip())

    if manga_id:
        data = _mangadex_api_get(session, f"{MANGADEX_API_BASE}/manga/{manga_id}", stop_event=stop_event)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            title = _pick_mangadex_title(data["data"].get("attributes") or {})
            if title:
                return sanitize_folder_name(title)

    return sanitize_folder_name(manga_id or "mangadex")


def _resolve_mangadex_chapter_meta(
    session: requests.Session,
    ch_url: str,
    stop_event: threading.Event | None = None
) -> tuple[str, str]:
    """Повертає (manga_slug, chapter_slug) для прямого посилання на главу MangaDex."""
    chapter_id = _extract_mangadex_uuid(ch_url, "chapter")
    if not chapter_id:
        return "mangadex", "chapter"

    payload = _mangadex_api_get(
        session,
        f"{MANGADEX_API_BASE}/chapter/{chapter_id}",
        params=[("includes[]", "manga")],
        stop_event=stop_event
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return "mangadex", f"id-{chapter_id[:8]}"

    ch_data = payload["data"]
    attrs = ch_data.get("attributes") or {}
    vol = str(attrs.get("volume") or "1").strip() or "1"
    ch_num = str(attrs.get("chapter") or "0").strip() or "0"
    chapter_slug = f"v{vol}-c{ch_num}"

    manga_slug = ""
    for rel in ch_data.get("relationships") or []:
        if isinstance(rel, dict) and rel.get("type") == "manga":
            title = _pick_mangadex_title(rel.get("attributes") or {})
            if title:
                manga_slug = sanitize_folder_name(title)
                break
            if rel.get("id"):
                manga_slug = sanitize_folder_name(str(rel["id"]))

    return (manga_slug or "mangadex"), chapter_slug


def _extract_chapters_mangadex(
    session: requests.Session,
    url: str,
    on_log=None,
    stop_event: threading.Event | None = None
) -> list[dict]:
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    manga_id = _extract_mangadex_uuid(url, "title")
    if not manga_id:
        log(tr("log_no_chapters"), "error")
        return []

    log(tr("log_goto_title", url=url), "info")
    log(tr("log_mangadex_api_chapters"), "info")

    manga_slug = _fetch_mangadex_manga_slug(session, url, manga_id, stop_event=stop_event)

    chapters_list: list[dict] = []
    seen_ids: set[str] = set()
    limit = 500
    offset = 0

    while True:
        if stop_event and stop_event.is_set():
            log(tr("log_scan_stopped"), "warn")
            break

        params = [
            ("limit", str(limit)),
            ("offset", str(offset)),
            ("includes[]", "scanlation_group"),
            ("includes[]", "user"),
            ("contentRating[]", "safe"),
            ("contentRating[]", "suggestive"),
            ("contentRating[]", "erotica"),
            ("contentRating[]", "pornographic"),
            ("order[volume]", "asc"),
            ("order[chapter]", "asc"),
        ]
        payload = _mangadex_api_get(
            session,
            f"{MANGADEX_API_BASE}/manga/{manga_id}/feed",
            params=params,
            on_log=on_log,
            stop_event=stop_event
        )
        if not isinstance(payload, dict) or payload.get("result") != "ok":
            break

        items = payload.get("data") or []
        if not items:
            break

        for item in items:
            if not isinstance(item, dict):
                continue
            ch_id = str(item.get("id") or "").strip()
            if not ch_id or ch_id in seen_ids:
                continue

            attrs = item.get("attributes") or {}
            # Пропускаємо зовнішні глави (MangaPlus тощо), де немає картинок на серверах MangaDex
            if attrs.get("externalUrl") or attrs.get("pages") == 0:
                continue

            seen_ids.add(ch_id)
            vol = str(attrs.get("volume") or "1").strip() or "1"
            ch_num = str(attrs.get("chapter") or "0").strip() or "0"
            lang = (attrs.get("translatedLanguage") or "unk").upper()

            group_names = []
            uploader_name = ""
            for rel in item.get("relationships") or []:
                if not isinstance(rel, dict):
                    continue
                rel_type = rel.get("type")
                rel_attrs = rel.get("attributes") or {}
                if rel_type == "scanlation_group" and rel_attrs.get("name"):
                    group_names.append(str(rel_attrs["name"]).strip())
                elif rel_type == "user" and rel_attrs.get("username") and not uploader_name:
                    uploader_name = str(rel_attrs["username"]).strip()

            if group_names:
                translator_label = " & ".join(group_names)
            elif uploader_name:
                translator_label = uploader_name
            else:
                translator_label = "No Group"

            team_name = f"[{lang}] {translator_label}"
            ch_url = f"https://mangadex.org/chapter/{ch_id}"

            entry = _make_chapter_entry(vol, ch_num, ch_url, bid="", team=team_name)
            entry["manga_slug"] = manga_slug
            entry["chapter_slug"] = f"v{vol}-c{ch_num}"
            chapters_list.append(entry)

        total = int(payload.get("total") or 0)
        offset += len(items)
        if offset >= total:
            break

        _sleep_interruptible(0.25, stop_event)

    chapters_list.sort(key=lambda x: (x['vol_float'], x['num_float'], x['team']))
    return chapters_list


def _extract_images_mangadex(
    session: requests.Session,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None
) -> list[str]:
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    chapter_id = _extract_mangadex_uuid(url, "chapter")
    if not chapter_id:
        return []

    log(tr("log_goto_chapter", url=url), "info")
    log(tr("log_getting_pages"), "info")

    payload = _mangadex_api_get(
        session,
        f"{MANGADEX_API_BASE}/at-home/server/{chapter_id}",
        on_log=on_log,
        stop_event=stop_event
    )
    if not isinstance(payload, dict) or payload.get("result") != "ok":
        return []

    base_url = (payload.get("baseUrl") or "").rstrip("/")
    ch_obj = payload.get("chapter") or {}
    ch_hash = (ch_obj.get("hash") or "").strip()
    # Використовуємо саме 'data' (оригінали без стиснення), а не 'dataSaver'
    files = ch_obj.get("data") or []

    if not base_url or not ch_hash or not isinstance(files, list) or not files:
        return []

    images = [f"{base_url}/data/{ch_hash}/{fname}" for fname in files if fname]
    if images:
        log(tr("log_mangadex_api_pages", count=len(images)), "success")
        if on_total_pages:
            on_total_pages(len(images))
        if on_new_image:
            for idx, img_url in enumerate(images, 1):
                if stop_event and stop_event.is_set():
                    break
                on_new_image(idx, img_url)

    return images


# ==============================================================================
# ЛОГІКА ДЛЯ LIB.SOCIAL (MANGALIB / HENTAILIB / SLASHLIB)
# ==============================================================================

def _extract_chapters_lib(page, url: str, on_log=None, stop_event: threading.Event | None = None):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    log(tr("log_goto_title", url=url), "info")
    try:
        page.get(url)
    except Exception as e:
        log(tr("log_page_load_err", err=e), "error")
        return []

    if stop_event and stop_event.is_set():
        return []

    bypass_age_warning(page)
    time.sleep(1.2)

    log(tr("log_getting_chapters"), "info")
    chapters_list = []

    # Спосіб 1: Спроба через внутрішній JS API
    try:
        js_cmd = r"""
        let list = null;
        let branches = null;
        if (window.__DATA__ && window.__DATA__.chapters) {
            list = window.__DATA__.chapters.list || null;
            branches = window.__DATA__.chapters.branches || null;
        } else if (window.__info && window.__info.chapters) {
            list = window.__info.chapters;
        }
        return list ? { list: list, branches: branches } : null;
        """
        api_payload = page.run_js(js_cmd)

        if api_payload and isinstance(api_payload.get('list'), list):
            chapters_data = api_payload['list']
            raw_branches = api_payload.get('branches')

            branch_map: dict[str, str] = {}
            if isinstance(raw_branches, list):
                for b in raw_branches:
                    if isinstance(b, dict) and b.get('id') is not None:
                        teams = b.get('teams') or []
                        names = [t.get('name') for t in teams if isinstance(t, dict) and t.get('name')]
                        if names:
                            branch_map[str(b['id'])] = " & ".join(names)
            elif isinstance(raw_branches, dict):
                for b_id, b in raw_branches.items():
                    if isinstance(b, dict):
                        teams = b.get('teams') or []
                        names = [t.get('name') for t in teams if isinstance(t, dict) and t.get('name')]
                        if names:
                            branch_map[str(b_id)] = " & ".join(names)

            orig_qs = parse_qs(urlparse(url).query)
            ui_val = orig_qs.get('ui', [None])[0]

            for ch in chapters_data:
                vol = str(ch.get('volume', '1'))
                ch_num = str(ch.get('number', '1'))
                bid = str(ch['branch_id']) if ch.get('branch_id') is not None else ""

                team_name = ""
                if isinstance(ch.get('teams'), list):
                    t_names = [t.get('name') for t in ch['teams'] if isinstance(t, dict) and t.get('name')]
                    if t_names:
                        team_name = " & ".join(t_names)
                if not team_name and bid in branch_map:
                    team_name = branch_map[bid]

                base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                main_path = urlparse(url).path
                for infix in ['/manga/', '/hentai/', '/yaoi/', '/slash/', '/ranobe/', '/anime/', '/comic/']:
                    main_path = main_path.replace(infix, '/')
                main_path = main_path.rstrip('/')

                ch_url = f"{base_url}{main_path}/read/v{vol}/c{ch_num}"

                qs_dict = {}
                if bid:
                    qs_dict['bid'] = bid
                if ui_val:
                    qs_dict['ui'] = str(ui_val)

                if qs_dict:
                    ch_url += "?" + urlencode(sorted(qs_dict.items()))

                chapters_list.append(_make_chapter_entry(vol, ch_num, ch_url, bid=bid, team=team_name))

            if len(chapters_list) > 0:
                unique_chapters = {c['url']: c for c in chapters_list}.values()
                chapters_list = list(unique_chapters)
                chapters_list.sort(key=lambda x: (x['vol_float'], x['num_float']))
                return chapters_list
    except Exception:
        pass

    # Спосіб 2: Швидке сканування HTML із атомарним JS-скролом та розпізнаванням перекладачів
    log(tr("log_api_fallback_html"), "warn")
    seen_urls = set()
    chapters_list = []

    try:
        page.scroll.to_top()
    except Exception:
        pass
    time.sleep(0.5)

    same_pos_count = 0

    for _ in range(150):
        if stop_event and stop_event.is_set():
            log(tr("log_scan_stopped"), "warn")
            break

        try:
            step_data = page.run_js(r"""
                const prevY = window.scrollY;
                const prevH = document.body ? document.body.scrollHeight : 0;

                const isNoiseLine = (line) => {
                    const s = line.trim();
                    if (!s) return true;
                    if (/^(том|volume|vol\.?)\s*\d+/i.test(s)) return true;
                    if (/^(глава|chapter|ch\.?)\s*[\d\.]+/i.test(s)) return true;
                    if (/^\d{1,2}\.\d{1,2}\.\d{2,4}$/.test(s)) return true;
                    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return true;
                    if (/^\d+\s*(сек|мин|хв|час|год|дн|нед|тиж|мес|міс|рік|рок)/i.test(s)) return true;
                    if (/^(читать|читати|read|скачать|завантажити|в закладки)$/i.test(s)) return true;
                    return false;
                };

                const extractTeamName = (a) => {
                    const raw = (a.innerText || a.textContent || "").trim();
                    const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(l => !isNoiseLine(l));
                    if (lines.length > 0) {
                        return lines[0];
                    }
                    const parent = a.parentElement;
                    if (parent) {
                        const pRaw = (parent.innerText || "").trim();
                        const pLines = pRaw.split(/\r?\n/).map(l => l.trim()).filter(l => !isNoiseLine(l));
                        if (pLines.length > 0 && pLines.length <= 3) {
                            return pLines[0];
                        }
                    }
                    return "";
                };

                const items = Array.from(document.querySelectorAll('a[href*="/read/"]'))
                    .map(a => {
                        const href = a.getAttribute('href');
                        if (!href) return null;
                        return {
                            href: href,
                            team: extractTeamName(a)
                        };
                    })
                    .filter(Boolean);

                let clickedMore = false;
                const keys = ["показать еще", "показать ещё", "загрузить еще", "показати ще"];
                const btns = Array.from(document.querySelectorAll('button'));
                for (const btn of btns) {
                    const txt = (btn.innerText || "").toLowerCase();
                    if (keys.some(k => txt.includes(k))) {
                        btn.click();
                        clickedMore = true;
                        break;
                    }
                }

                window.scrollBy(0, Math.max(Math.round(window.innerHeight * 1.8), 1400));
                return {
                    items: items,
                    clickedMore: clickedMore,
                    moved: Math.abs(window.scrollY - prevY) > 2 || (document.body ? document.body.scrollHeight : 0) !== prevH
                };
            """) or {}

            for entry in step_data.get('items', []):
                href = entry.get('href', '')
                team_name = entry.get('team', '')
                if not href:
                    continue

                parsed_href = urlparse(href)
                qs = parse_qs(parsed_href.query)

                if 'p' in qs:
                    del qs['p']

                bid = qs.get('bid', [''])[0]
                clean_query = urlencode(sorted(qs.items()), doseq=True)
                clean_url = parsed_href._replace(query=clean_query).geturl()

                if not clean_url.startswith('http'):
                    clean_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}" + clean_url

                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)

                parsed_path = urlparse(clean_url).path
                parts = [p for p in parsed_path.split('/') if p]
                vol, num = "1", "1"
                for p in parts:
                    if p.startswith('v') and (p[1:].isdigit() or p[1:].replace('.', '', 1).isdigit()):
                        vol = p[1:]
                    elif p.startswith('c') and (p[1:].isdigit() or p[1:].replace('.', '', 1).isdigit()):
                        num = p[1:]

                chapters_list.append(
                    _make_chapter_entry(vol, num, clean_url, bid=bid, team=team_name)
                )

            if step_data.get('clickedMore'):
                time.sleep(random.uniform(0.3, 0.45))
                same_pos_count = 0
            elif step_data.get('moved'):
                same_pos_count = 0
                time.sleep(random.uniform(0.14, 0.22))
            else:
                same_pos_count += 1
                if same_pos_count >= 5:
                    break
                time.sleep(0.25)
        except Exception:
            break

    chapters_list.sort(key=lambda x: (x['vol_float'], x['num_float']))
    return chapters_list


def try_extract_images_from_api(page):
    """Спроба отримати прямий список сторінок із JS-даних сторінки (Nuxt 3 / __DATA__ / __pg)."""
    images = []
    try:
        js_cmd = r"""
        let imgs = [];
        let srv = "";

        if (window.__pg && window.__pg.length > 0) {
            imgs = window.__pg;
        } else if (window.__info && window.__info.pages && window.__info.pages.length > 0) {
            imgs = window.__info.pages;
        } else if (window.__DATA__) {
            if (window.__DATA__.pages && Array.isArray(window.__DATA__.pages)) imgs = window.__DATA__.pages;
            else if (window.__DATA__.pages && window.__DATA__.pages.list) imgs = window.__DATA__.pages.list;
            else if (window.__DATA__.reader && window.__DATA__.reader.pages) {
                if (Array.isArray(window.__DATA__.reader.pages)) imgs = window.__DATA__.reader.pages;
                else if (window.__DATA__.reader.pages.list) imgs = window.__DATA__.reader.pages.list;
            }
        }

        if (imgs.length === 0 && window.useNuxtApp) {
            try {
                let payload = window.useNuxtApp().payload;
                if (payload && payload.data) {
                    for (let key in payload.data) {
                        let data = payload.data[key];
                        if (data && data.pages) {
                            if (Array.isArray(data.pages)) imgs = data.pages;
                            else if (data.pages.list) imgs = data.pages.list;
                        } else if (data && data.chapter && data.chapter.pages) {
                            imgs = data.chapter.pages;
                        }
                    }
                }
            } catch(e) {}
        }

        try {
            srv = (window.__info && window.__info.servers && window.__info.servers.main) || 
                  (window.__DATA__ && window.__DATA__.servers && window.__DATA__.servers.main) || "";
            if (!srv && window.useNuxtApp) {
                 let payload = window.useNuxtApp().payload;
                 for (let key in payload.state) {
                      if (payload.state[key] && payload.state[key].servers && payload.state[key].servers.main) {
                           srv = payload.state[key].servers.main;
                      }
                 }
            }
        } catch(e) {}

        return { images: imgs, server: srv };
        """
        api_result = page.run_js(js_cmd)

        if api_result and isinstance(api_result, dict):
            pg_data = api_result.get('images', [])
            server = api_result.get('server', "")

            if pg_data and isinstance(pg_data, list) and len(pg_data) > 0:
                for item in pg_data:
                    img_path = item.get('u') or item.get('url') if isinstance(item, dict) else item
                    if img_path:
                        if not img_path.startswith('http') and not img_path.startswith('//'):
                            full_url = server.rstrip('/') + '/' + img_path.lstrip('/')
                        elif img_path.startswith('//'):
                            full_url = 'https:' + img_path
                        else:
                            full_url = img_path
                        if full_url not in images:
                            images.append(full_url)
    except Exception:
        pass
    return images


ATOMIC_SCAN_AND_SCROLL_JS = r"""
const doScroll = arguments[0];
const scrollMultiplier = arguments[1];

const prevHeight = document.body ? document.body.scrollHeight : 0;
const prevY = window.scrollY;

const imgs = Array.from(document.querySelectorAll('img')).map(img =>
    img.getAttribute('data-src') || img.getAttribute('src') || img.getAttribute('data-srcset') || ''
).filter(Boolean);

let totalPages = 0;
if (document.body) {
    const visibleText = document.body.innerText || '';
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
    const fullText = clone.textContent || '';
    for (const txt of [visibleText, fullText]) {
        const regex = /\b(\d+)\s*(?:\/|з|из)\s*(\d+)\b/g;
        let m;
        while ((m = regex.exec(txt)) !== null) {
            const cur = parseInt(m[1], 10);
            const tot = parseInt(m[2], 10);
            if (cur >= 1 && cur <= tot && tot >= 2 && tot <= 500) {
                if (tot > totalPages) totalPages = tot;
            }
        }
        if (totalPages > 0) break;
    }
}

const bodyLower = (document.body ? document.body.innerText : '').toLowerCase();
const hasEndMarker = ["комментари", "наступна глава", "next chapter", "следующая глава"]
    .some(w => bodyLower.includes(w));

if (doScroll) {
    const step = Math.max(Math.round(window.innerHeight * scrollMultiplier), 1500);
    window.scrollBy(0, step);
}

const newHeight = document.body ? document.body.scrollHeight : 0;
const newY = window.scrollY;

return {
    imgs: imgs,
    totalPages: totalPages,
    hasEndMarker: hasEndMarker,
    prevHeight: prevHeight,
    newHeight: newHeight,
    prevY: prevY,
    newY: newY
};
"""


def append_valid_images(raw_srcs, images, on_new_image=None):
    """Фільтрує та додає нові URL сторінок, одразу передаючи їх у завантажувач."""
    for src in raw_srcs:
        if src.startswith('//'):
            src = 'https:' + src
        if src.startswith('http') and src not in images:
            src_lower = src.lower()
            if any(k in src_lower for k in ['/chapters/', '/manga/', '/hentai/', '/pages/', 'lib.social']):
                if not any(bad in src_lower for bad in ['avatar', 'cover', 'thumb', 'logo', 'icon']):
                    images.append(src)
                    if on_new_image:
                        on_new_image(len(images), src)


def _extract_images_lib(
    page,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None
):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    log(tr("log_goto_chapter", url=url), "info")
    try:
        page.get(url)
    except Exception as e:
        log(tr("log_reader_open_err", err=e), "error")
        return []

    if stop_event and stop_event.is_set():
        return []

    bypass_age_warning(page)
    log(tr("log_getting_pages"), "info")

    # Спосіб 1: Спроба через розширений API (включаючи Nuxt 3)
    images = try_extract_images_from_api(page)
    if len(images) > 3:
        log(tr("log_total_pages", total=len(images)), "info")
        if on_total_pages:
            on_total_pages(len(images))
        if on_new_image:
            for idx, img_url in enumerate(images, 1):
                on_new_image(idx, img_url)
        return images

    # Спосіб 2: Швидкий турбо-скролінг із атомарним JS-збором та потоковим завантаженням
    log(tr("log_turbo_scan"), "warn")

    try:
        page.scroll.to_top()
    except Exception:
        pass

    total_pages = 0
    images = []
    for _ in range(30):
        if stop_event and stop_event.is_set():
            return images

        time.sleep(0.15)
        api_imgs = try_extract_images_from_api(page)
        if len(api_imgs) > 3:
            log(tr("log_total_pages", total=len(api_imgs)), "info")
            if on_total_pages:
                on_total_pages(len(api_imgs))
            if on_new_image:
                for idx, img_url in enumerate(api_imgs, 1):
                    on_new_image(idx, img_url)
            return api_imgs

        try:
            init_state = page.run_js(ATOMIC_SCAN_AND_SCROLL_JS, False, 2.0) or {}
            if init_state.get('totalPages', 0) > 1:
                total_pages = init_state['totalPages']
            append_valid_images(init_state.get('imgs', []), images, on_new_image)
        except Exception:
            pass

        if total_pages > 1 or len(images) > 0:
            break

    if total_pages > 1:
        log(tr("log_total_pages", total=total_pages), "info")
        if on_total_pages:
            on_total_pages(total_pages)

    same_bottom_count = 0
    stall_retries = 0
    unknown_total_retries = 0

    for _ in range(600):
        if stop_event and stop_event.is_set():
            log(tr("log_chapter_scan_aborted"), "warn")
            break

        prev_len = len(images)
        try:
            state = page.run_js(ATOMIC_SCAN_AND_SCROLL_JS, True, 2.0) or {}
        except Exception:
            break

        if total_pages == 0 and state.get('totalPages', 0) > 1:
            total_pages = state['totalPages']
            log(tr("log_total_pages", total=total_pages), "info")
            if on_total_pages:
                on_total_pages(total_pages)

        append_valid_images(state.get('imgs', []), images, on_new_image)

        if total_pages > 0 and len(images) >= total_pages:
            log(tr("log_collected_all_pages", count=len(images)), "success")
            break

        moved_down = abs(state.get('newY', 0) - state.get('prevY', 0)) > 2
        height_grew = state.get('newHeight', 0) > state.get('prevHeight', 0)
        got_new_images = len(images) > prev_len

        if moved_down or height_grew or got_new_images:
            same_bottom_count = 0
            time.sleep(random.uniform(0.14, 0.22))
        else:
            same_bottom_count += 1

            if same_bottom_count in (2, 5, 9):
                try:
                    page.run_js('window.scrollBy(0, -350); setTimeout(() => window.scrollBy(0, 600), 60);')
                except Exception:
                    pass
                time.sleep(0.22)
            elif same_bottom_count >= 12:
                has_end_marker = state.get('hasEndMarker', False)

                if total_pages > 0 and len(images) < total_pages and stall_retries < 35:
                    stall_retries += 1
                    if stall_retries % 3 == 1:
                        log(tr("log_waiting_pages", cur=len(images), total=total_pages), "warn")
                    try:
                        page.run_js('window.scrollBy(0, -450); setTimeout(() => window.scrollBy(0, 750), 80);')
                    except Exception:
                        pass
                    same_bottom_count = 7
                    time.sleep(0.28)
                elif total_pages == 0 and len(images) <= 2 and not has_end_marker and unknown_total_retries < 5:
                    unknown_total_retries += 1
                    log(tr("log_pages_still_loading", count=len(images)), "warn")
                    try:
                        page.run_js('window.scrollBy(0, -400); setTimeout(() => window.scrollBy(0, 800), 80);')
                    except Exception:
                        pass
                    same_bottom_count = 6
                    time.sleep(0.3)
                else:
                    if has_end_marker:
                        log(tr("log_end_marker"), "info")
                    break
            else:
                time.sleep(random.uniform(0.18, 0.28))

    return images


# ==============================================================================
# ЛОГІКА ДЛЯ MADARA (MANGA18FX.COM ТА WEBTOON.XYZ — МИТТЄВИЙ РЕЖИМ)
# ==============================================================================

def _set_madara_load_mode(page, enabled: bool):
    try:
        if enabled:
            page.set.load_mode.eager()
        else:
            page.set.load_mode.normal()
    except Exception:
        pass


def _extract_chapters_madara(page, url: str, on_log=None, stop_event: threading.Event | None = None):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    _set_madara_load_mode(page, True)
    try:
        log(tr("log_goto_title", url=url), "info")
        try:
            page.get(url)
        except Exception as e:
            log(tr("log_page_load_err", err=e), "error")
            return []

        if stop_event and stop_event.is_set():
            return []

        time.sleep(1.0)
        log(tr("log_madara_expand"), "info")

        for attempt in range(10):
            if stop_event and stop_event.is_set():
                log(tr("log_scan_stopped"), "warn")
                return []

            prev_count = 0
            try:
                prev_count = page.run_js('return document.querySelectorAll(\'a[href*="/chapter-"]\').length;') or 0
            except Exception:
                pass

            clicked = False
            try:
                clicked = page.run_js(r"""
                    function triggerClick(el) {
                        el.scrollIntoView({block: "center"});
                        ['mousedown', 'mouseup', 'click'].forEach(evtType => {
                            el.dispatchEvent(new MouseEvent(evtType, {bubbles: true, cancelable: true, view: window}));
                        });
                        if (typeof el.click === 'function') el.click();
                    }

                    const classSelectors = [
                        '.chapter-readmore',
                        '.c-chapter-readmore',
                        '.btn-readmore',
                        '.readmore-chap',
                        '[class*="readmore"]',
                        '[class*="show-more"]',
                        '[id*="readmore"]'
                    ];
                    for (const sel of classSelectors) {
                        const els = Array.from(document.querySelectorAll(sel));
                        for (const el of els) {
                            const style = window.getComputedStyle(el);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                triggerClick(el);
                                return true;
                            }
                        }
                    }

                    const allEls = Array.from(document.querySelectorAll('a, button, span, div, p, b, strong, li'));
                    for (const el of allEls) {
                        if (el.children.length > 2) continue;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;

                        const rawTxt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        const beforeTxt = (window.getComputedStyle(el, '::before').content || '').replace(/["']/g, '').trim().toLowerCase();
                        const afterTxt = (window.getComputedStyle(el, '::after').content || '').replace(/["']/g, '').trim().toLowerCase();

                        if (rawTxt === 'show more' || rawTxt === 'show all' || beforeTxt === 'show more' || afterTxt === 'show more') {
                            triggerClick(el);
                            return true;
                        }
                    }
                    return false;
                """)
            except Exception:
                clicked = False

            if not clicked:
                try:
                    btn = (
                        page.ele('@@tx():Show More', timeout=1)
                        or page.ele('css:.chapter-readmore, .c-chapter-readmore', timeout=1)
                    )
                    if btn:
                        btn.scroll.to_see()
                        time.sleep(0.2)
                        btn.click()
                        clicked = True
                except Exception:
                    pass

            if clicked:
                log(tr("log_madara_show_more"), "success")
                time.sleep(1.0)
                try:
                    new_count = page.run_js('return document.querySelectorAll(\'a[href*="/chapter-"]\').length;') or 0
                    if new_count == prev_count and attempt >= 1:
                        break
                except Exception:
                    break
            else:
                break

        try:
            raw_links = page.run_js(r"""
                return Array.from(document.querySelectorAll('a[href*="/chapter-"]'))
                    .map(a => ({ href: a.href || a.getAttribute('href') || '', text: (a.innerText || '').trim() }))
                    .filter(item => item.href);
            """) or []
        except Exception:
            raw_links = []

        path_parts = [p for p in urlparse(url).path.strip('/').split('/') if p]
        manga_slug = ""
        if len(path_parts) >= 2 and path_parts[0].lower() in ('manga', 'read', 'webtoon', 'manhwa', 'manhua'):
            manga_slug = path_parts[1].lower()
        elif len(path_parts) >= 1:
            manga_slug = path_parts[0].lower()

        seen_urls = set()
        chapters_list = []

        for item in raw_links:
            href = item['href']
            if not href.startswith('http'):
                href = f"{urlparse(url).scheme}://{urlparse(url).netloc}/{href.lstrip('/')}"

            clean_url = href.split('?')[0].rstrip('/')
            clean_lower = clean_url.lower()

            if manga_slug and f"/{manga_slug}/" not in clean_lower:
                continue

            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            match = re.search(r'/chapter-([\d]+(?:[\.-]\d+)?)', clean_lower)
            if match:
                ch_num = match.group(1).replace('-', '.')
            else:
                txt_match = re.search(r'([\d]+(?:\.\d+)?)', item['text'])
                ch_num = txt_match.group(1) if txt_match else "0"

            chapters_list.append(_make_chapter_entry('1', ch_num, clean_url))

        chapters_list.sort(key=lambda x: (x['vol_float'], x['num_float']))
        return chapters_list
    finally:
        _set_madara_load_mode(page, False)


def _extract_madara_instant(page) -> list[str]:
    """Миттєво дістає всі URL сторінок із DOM на manga18fx.com та webtoon.xyz без скролу."""
    try:
        raw_srcs = page.run_js(r"""
            function resolveUrl(raw) {
                if (!raw) return '';
                raw = raw.trim();
                if (!raw || raw.startsWith('data:')) return '';
                try {
                    return new URL(raw, document.baseURI).href;
                } catch (e) {
                    return raw;
                }
            }

            let imgNodes = [];
            const readerContainers = document.querySelectorAll(
                '.reading-content, .read-content, .chapter-content, .chapter-c, #chapter-content, .page-break'
            );
            if (readerContainers.length > 0) {
                readerContainers.forEach(c => {
                    c.querySelectorAll('img').forEach(img => imgNodes.push(img));
                });
            } else {
                const selects = Array.from(document.querySelectorAll('select')).filter(s =>
                    (s.innerText || '').toLowerCase().includes('chapter')
                );
                const allImgs = Array.from(document.querySelectorAll('img'));
                if (selects.length >= 2) {
                    const topNav = selects[0];
                    const bottomNav = selects[selects.length - 1];
                    imgNodes = allImgs.filter(img =>
                        (topNav.compareDocumentPosition(img) & Node.DOCUMENT_POSITION_FOLLOWING) &&
                        (bottomNav.compareDocumentPosition(img) & Node.DOCUMENT_POSITION_PRECEDING)
                    );
                }
            }

            return imgNodes.map(img => {
                if (img.complete && img.naturalWidth > 0 && img.naturalWidth < 300) return '';
                const raw = img.getAttribute('data-src')
                    || img.getAttribute('data-lazy-src')
                    || img.getAttribute('data-original')
                    || img.getAttribute('data-lazy')
                    || img.getAttribute('data-url')
                    || img.getAttribute('src')
                    || '';
                return resolveUrl(raw);
            }).filter(Boolean);
        """) or []
    except Exception:
        raw_srcs = []

    bad_keywords = [
        'logo', 'icon', 'avatar', 'loader', 'spinner',
        'banner', 'ads.', 'data:image', '/175x', '/193x', '/110x'
    ]
    images = []
    for src in raw_srcs:
        src = src.strip()
        if src.startswith('//'):
            src = 'https:' + src
        if src.startswith('http') and src not in images:
            src_lower = src.lower()
            if not any(bad in src_lower for bad in bad_keywords):
                images.append(src)
    return images


ATOMIC_SCAN_AND_SCROLL_MADARA_JS = r"""
const doScroll = arguments[0];
const prevY = window.scrollY;
const prevHeight = document.body ? document.body.scrollHeight : 0;

function resolveUrl(raw) {
    if (!raw) return '';
    raw = raw.trim();
    if (!raw || raw.startsWith('data:')) return '';
    try {
        return new URL(raw, document.baseURI).href;
    } catch (e) {
        return raw;
    }
}

let imgNodes = [];
const readerContainers = document.querySelectorAll(
    '.reading-content, .read-content, .chapter-content, .chapter-c, #chapter-content, .page-break'
);
if (readerContainers.length > 0) {
    readerContainers.forEach(c => {
        c.querySelectorAll('img').forEach(img => imgNodes.push(img));
    });
} else {
    imgNodes = Array.from(document.querySelectorAll('img')).filter(img =>
        !img.closest('header, footer, nav, aside, .sidebar, .widget, .related-manga, .c-related, .manga-discussion')
    );
}

const imgs = imgNodes.map(img => {
    if (img.complete && img.naturalWidth > 0 && img.naturalWidth < 300) return '';
    const raw = img.getAttribute('data-src')
        || img.getAttribute('data-lazy-src')
        || img.getAttribute('data-original')
        || img.getAttribute('data-lazy')
        || img.getAttribute('data-url')
        || img.getAttribute('src')
        || '';
    return resolveUrl(raw);
}).filter(Boolean);

if (doScroll) {
    window.scrollBy(0, Math.max(Math.round(window.innerHeight * 1.2), 800));
}

return {
    imgs: imgs,
    prevY: prevY,
    newY: window.scrollY,
    prevHeight: prevHeight,
    newHeight: document.body ? document.body.scrollHeight : 0
};
"""


def _extract_images_madara(
    page,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None
):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    _set_madara_load_mode(page, True)
    try:
        log(tr("log_goto_chapter", url=url), "info")
        try:
            page.get(url)
        except Exception as e:
            log(tr("log_reader_open_err", err=e), "error")
            return []

        if stop_event and stop_event.is_set():
            return []

        for _ in range(10):
            if stop_event and stop_event.is_set():
                return []
            time.sleep(0.15)
            instant_imgs = _extract_madara_instant(page)
            if len(instant_imgs) >= 3:
                log(tr("log_madara_instant_found", count=len(instant_imgs)), "success")
                if on_total_pages:
                    on_total_pages(len(instant_imgs))
                if on_new_image:
                    for idx, img_url in enumerate(instant_imgs, 1):
                        on_new_image(idx, img_url)
                return instant_imgs

        images = []
        bad_keywords = [
            'logo', 'icon', 'avatar', 'loader', 'spinner',
            'banner', 'ads.', 'data:image', '/175x', '/193x', '/110x'
        ]
        same_bottom = 0
        for _ in range(80):
            if stop_event and stop_event.is_set():
                break
            state = page.run_js(ATOMIC_SCAN_AND_SCROLL_MADARA_JS, True) or {}
            for src in state.get('imgs', []):
                src = src.strip()
                if src.startswith('//'):
                    src = 'https:' + src
                if src.startswith('http') and src not in images:
                    if not any(bad in src.lower() for bad in bad_keywords):
                        images.append(src)
                        if on_new_image:
                            on_new_image(len(images), src)

            moved = abs(state.get('newY', 0) - state.get('prevY', 0)) > 2
            grew = state.get('newHeight', 0) > state.get('prevHeight', 0)
            if moved or grew:
                same_bottom = 0
                time.sleep(0.15)
            else:
                same_bottom += 1
                if same_bottom >= 4:
                    break
                time.sleep(0.15)

        if images:
            log(tr("log_madara_bottom_reached", count=len(images)), "info")
        return images
    finally:
        _set_madara_load_mode(page, False)


# ==============================================================================
# ЛОГІКА ДЛЯ SENKURO.COM ТА SENKOGNITO.COM
# (ЄДИНИЙ СПИСОК ГЛАВ БЕЗ РОЗБИТТЯ ЗА ДАТАМИ + КОНТРОЛЬ МЕЖІ ГЛАВИ)
# ==============================================================================

def _normalize_senkuro_title_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    if re.search(r'/manga/[^/]+$', path):
        path = path + '/chapters'
    return parsed._replace(path=path, query='', fragment='').geturl()


def _normalize_senkuro_chapter_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    match = re.search(r'^(/manga/[^/]+/chapters/\d+)', path)
    if match:
        path = match.group(1) + '/pages/1'
    return parsed._replace(path=path, query='', fragment='').geturl()


def _extract_chapters_senkuro(page, url: str, on_log=None, stop_event: threading.Event | None = None):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    target_url = _normalize_senkuro_title_url(url)
    log(tr("log_goto_title", url=target_url), "info")
    try:
        page.get(target_url)
    except Exception as e:
        log(tr("log_page_load_err", err=e), "error")
        return []

    if stop_event and stop_event.is_set():
        return []

    bypass_age_warning(page)
    time.sleep(1.2)
    log(tr("log_getting_chapters"), "info")

    parsed_base = urlparse(target_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    try:
        page.scroll.to_top()
    except Exception:
        pass
    time.sleep(0.4)

    seen_chapters: dict[str, dict] = {}
    same_pos_count = 0

    for _ in range(180):
        if stop_event and stop_event.is_set():
            log(tr("log_scan_stopped"), "warn")
            break

        try:
            step_data = page.run_js(r"""
                const prevY = window.scrollY;
                const prevH = document.body ? document.body.scrollHeight : 0;

                const items = [];
                const links = Array.from(document.querySelectorAll('a[href*="/chapters/"]'));
                for (const a of links) {
                    const rawHref = a.getAttribute('href') || a.href || '';
                    const m = rawHref.match(/\/manga\/([^\/]+)\/chapters\/(\d+)/);
                    if (!m) continue;

                    const fullText = (a.innerText || a.textContent || '').trim();
                    const lines = fullText.split(/\r?\n/).map(l => l.trim()).filter(Boolean);

                    let vol = '1';
                    let num = '';

                    for (const line of lines) {
                        // Ігноруємо дати публікації (напр. 2026-10-17 або 17.10.2026)
                        if (/^\d{4}-\d{2}-\d{2}$/.test(line) || /^\d{1,2}\.\d{1,2}\.\d{2,4}$/.test(line)) {
                            continue;
                        }

                        const volMatch = line.match(/(?:том|vol\.?|volume)\s*(\d+(?:\.\d+)?)/i);
                        if (volMatch) vol = volMatch[1];

                        const chMatch = line.match(/(?:глава|ch\.?|chapter)\s*(\d+(?:\.\d+)?)/i);
                        if (chMatch) {
                            num = chMatch[1];
                        } else if (!num && /^\d+(?:\.\d+)?$/.test(line)) {
                            num = line;
                        }
                    }

                    if (!num) {
                        const titleAttr = a.getAttribute('title') || '';
                        const tMatch = titleAttr.match(/(?:глава|ch\.?|chapter)\s*(\d+(?:\.\d+)?)/i);
                        if (tMatch) num = tMatch[1];
                        const vMatch = titleAttr.match(/(?:том|vol\.?|volume)\s*(\d+(?:\.\d+)?)/i);
                        if (vMatch) vol = vMatch[1];
                    }

                    items.push({
                        slug: m[1],
                        chapterId: m[2],
                        vol: vol,
                        num: num || '0'
                    });
                }

                window.scrollBy(0, Math.max(Math.round(window.innerHeight * 1.6), 1200));

                return {
                    items: items,
                    moved: Math.abs(window.scrollY - prevY) > 2 || (document.body ? document.body.scrollHeight : 0) !== prevH
                };
            """) or {}

            for item in step_data.get('items', []):
                ch_id = item.get('chapterId', '')
                slug = item.get('slug', '')
                if not ch_id or not slug:
                    continue

                ch_url = f"{base_origin}/manga/{slug}/chapters/{ch_id}/pages/1"
                if ch_url not in seen_chapters:
                    # На Senkuro / Senkognito немає вибору гілок перекладу — зберігаємо єдиним списком
                    seen_chapters[ch_url] = _make_chapter_entry(
                        vol=item.get('vol', '1'),
                        ch_num=item.get('num', '0'),
                        url=ch_url,
                        bid="",
                        team=""
                    )

            if step_data.get('moved'):
                same_pos_count = 0
                time.sleep(random.uniform(0.18, 0.28))
            else:
                same_pos_count += 1
                if same_pos_count >= 6:
                    break
                time.sleep(0.25)
        except Exception:
            break

    chapters_list = list(seen_chapters.values())
    chapters_list.sort(key=lambda x: (x['vol_float'], x['num_float']))
    return chapters_list


def _try_extract_senkuro_api(page, target_chapter_id: str) -> list[str]:
    """Шукає сторінки конкретної глави за її chapter_id у Nuxt 3 payload/state без скролу."""
    if not target_chapter_id:
        return []
    try:
        raw_urls = page.run_js(r"""
            const targetId = String(arguments[0]);
            const visited = new WeakSet();
            let foundPages = null;

            function searchObj(obj, depth) {
                if (!obj || typeof obj !== 'object' || depth > 12 || foundPages) return;
                if (visited.has(obj)) return;
                visited.add(obj);

                if (String(obj.id || '') === targetId && Array.isArray(obj.pages) && obj.pages.length > 0) {
                    foundPages = obj.pages;
                    return;
                }

                if (Array.isArray(obj)) {
                    for (let i = 0; i < obj.length; i++) {
                        searchObj(obj[i], depth + 1);
                        if (foundPages) return;
                    }
                } else {
                    for (const key of Object.keys(obj)) {
                        searchObj(obj[key], depth + 1);
                        if (foundPages) return;
                    }
                }
            }

            try {
                if (window.__NUXT__) searchObj(window.__NUXT__, 0);
            } catch (e) {}

            try {
                if (!foundPages && window.useNuxtApp) {
                    const nuxt = window.useNuxtApp();
                    if (nuxt && nuxt.payload) searchObj(nuxt.payload, 0);
                }
            } catch (e) {}

            if (!foundPages) return [];

            const sorted = foundPages.slice().sort((a, b) => {
                const na = Number(a && (a.number ?? a.index ?? 0));
                const nb = Number(b && (b.number ?? b.index ?? 0));
                return na - nb;
            });

            return sorted.map(p => {
                if (!p) return '';
                if (typeof p === 'string') return p;
                if (p.image) {
                    if (typeof p.image === 'string') return p.image;
                    if (p.image.original && p.image.original.url) return p.image.original.url;
                    if (p.image.url) return p.image.url;
                }
                return p.url || p.src || '';
            }).filter(Boolean);
        """, target_chapter_id) or []
    except Exception:
        raw_urls = []

    images = []
    for src in raw_urls:
        src = src.strip()
        if src.startswith('//'):
            src = 'https:' + src
        if src.startswith('http') and src not in images:
            images.append(src)
    return images


ATOMIC_SCAN_SENKURO_JS = r"""
const targetChapterId = String(arguments[0]);
const doScroll = Boolean(arguments[1]);

const prevY = window.scrollY;
const prevHeight = document.body ? document.body.scrollHeight : 0;
const currentPath = window.location.pathname || '';

// 1. Перевірка, чи URL ще належить поточній главі (Senkuro при автопідвантаженні змінює URL на ID наступної глави)
const pathChapterMatch = currentPath.match(/\/chapters\/(\d+)/);
const currentChapterId = pathChapterMatch ? pathChapterMatch[1] : targetChapterId;
const urlSwitchedToNext = Boolean(targetChapterId && currentChapterId !== targetChapterId);

function resolveUrl(raw) {
    if (!raw) return '';
    raw = raw.trim();
    if (!raw || raw.startsWith('data:')) return '';
    try {
        return new URL(raw, document.baseURI).href;
    } catch (e) {
        return raw;
    }
}

function pickBestSrc(img) {
    const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
    if (srcset) {
        const candidates = srcset.split(',')
            .map(s => s.trim().split(/\s+/)[0])
            .filter(Boolean);
        if (candidates.length > 0) {
            return resolveUrl(candidates[candidates.length - 1]);
        }
    }
    const raw = img.getAttribute('data-src')
        || img.getAttribute('data-original')
        || img.getAttribute('data-lazy-src')
        || img.getAttribute('src')
        || '';
    return resolveUrl(raw);
}

// 2. Пошук першої межі кінця глави в DOM ("Над главой работали", "Следующая >", або посилання на іншу главу)
let boundaryEl = null;
const allAnchors = Array.from(document.querySelectorAll('a[href*="/chapters/"]'));
for (const a of allAnchors) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/chapters\/(\d+)/);
    if (m && m[1] !== targetChapterId) {
        boundaryEl = a;
        break;
    }
}

if (!boundaryEl) {
    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) {
        if (node.children.length > 3) continue;
        const txt = (node.innerText || '').trim().toLowerCase();
        if (txt === 'над главой работали' || txt === 'к тайтлу' || txt.startsWith('следующая')) {
            boundaryEl = node;
            break;
        }
    }
}

// 3. Збір зображень ТІЛЬКИ ДО межі кінця глави (DOCUMENT_POSITION_PRECEDING)
const allImgs = Array.from(document.querySelectorAll('img'));
const validUrls = [];

for (const img of allImgs) {
    if (img.closest('header, nav, aside, footer, [role="dialog"]')) continue;
    if (boundaryEl) {
        const pos = boundaryEl.compareDocumentPosition(img);
        if (!(pos & Node.DOCUMENT_POSITION_PRECEDING)) {
            continue;
        }
    }
    if (img.complete && img.naturalWidth > 0 && img.naturalWidth < 250) continue;
    const url = pickBestSrc(img);
    if (url) {
        validUrls.push(url);
    }
}

// 4. Зчитування індикатора сторінок (наприклад "1/21" праворуч), поки URL ще на поточній главі
let totalPages = 0;
if (!urlSwitchedToNext && document.body) {
    const sideNodes = Array.from(document.querySelectorAll('div, span, p, button'));
    for (const el of sideNodes) {
        if (el.children.length > 2) continue;
        const t = (el.innerText || '').trim();
        const m = t.match(/^(\d+)\s*\/\s*(\d+)$/);
        if (m) {
            const cur = parseInt(m[1], 10);
            const tot = parseInt(m[2], 10);
            if (cur >= 1 && cur <= tot && tot >= 1 && tot <= 500) {
                totalPages = tot;
                break;
            }
        }
    }
}

// Перевірка, чи межа вже в межах видимості або вище (тобто ми дійшли до кінця глави)
let reachedBoundary = false;
if (boundaryEl) {
    const rect = boundaryEl.getBoundingClientRect();
    if (rect.top <= window.innerHeight + 120) {
        reachedBoundary = true;
    }
}

if (doScroll && !urlSwitchedToNext && !reachedBoundary) {
    const step = Math.max(Math.round(window.innerHeight * 0.85), 750);
    window.scrollBy(0, step);
}

return {
    imgs: validUrls,
    totalPages: totalPages,
    urlSwitchedToNext: urlSwitchedToNext,
    reachedBoundary: reachedBoundary,
    prevY: prevY,
    newY: window.scrollY,
    prevHeight: prevHeight,
    newHeight: document.body ? document.body.scrollHeight : 0
};
"""


def _detect_senkuro_chapter_slug(page, fallback_id: str) -> str:
    """Зчитує 'Том X Глава Y' із заголовка читалки Senkuro для формування назви папки vX-cY."""
    try:
        header_txt = page.run_js(r"""
            const els = Array.from(document.querySelectorAll('header *, nav *, a, span, h1, h2, div'));
            for (const el of els) {
                if (el.children.length > 2) continue;
                const t = (el.innerText || '').trim();
                if (/(?:том|vol\.?)\s*\d+.*(?:глава|ch\.?)\s*\d+/i.test(t) && t.length < 60) {
                    return t;
                }
            }
            return document.title || '';
        """) or ""
        vol_m = re.search(r'(?:том|vol\.?|volume)\s*(\d+(?:\.\d+)?)', header_txt, re.IGNORECASE)
        ch_m = re.search(r'(?:глава|ch\.?|chapter)\s*(\d+(?:\.\d+)?)', header_txt, re.IGNORECASE)
        if ch_m:
            vol = vol_m.group(1) if vol_m else "1"
            num = ch_m.group(1)
            return f"v{vol}-c{num}"
    except Exception:
        pass
    return f"ch-{fallback_id}"


def _extract_images_senkuro(
    page,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None
):
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    target_url = _normalize_senkuro_chapter_url(url)
    id_match = re.search(r'/chapters/(\d+)', urlparse(target_url).path)
    target_chapter_id = id_match.group(1) if id_match else ""

    log(tr("log_goto_chapter", url=target_url), "info")
    try:
        page.get(target_url)
    except Exception as e:
        log(tr("log_reader_open_err", err=e), "error")
        return []

    if stop_event and stop_event.is_set():
        return []

    bypass_age_warning(page)
    log(tr("log_getting_pages"), "info")

    bad_keywords = [
        'avatar', 'cover', 'thumb', 'logo', 'icon',
        'banner', 'ads.', 'data:image'
    ]

    # Спосіб 1: Спроба отримати масив сторінок конкретної глави з Nuxt 3 state
    for _ in range(12):
        if stop_event and stop_event.is_set():
            return []
        time.sleep(0.2)
        api_imgs = _try_extract_senkuro_api(page, target_chapter_id)
        if len(api_imgs) > 0:
            log(tr("log_senkuro_api_found", count=len(api_imgs)), "success")
            if on_total_pages:
                on_total_pages(len(api_imgs))
            if on_new_image:
                for idx, img_url in enumerate(api_imgs, 1):
                    on_new_image(idx, img_url)
            return api_imgs

    # Спосіб 2: Контрольований скрол із жорсткою фіксацією межі поточної глави
    log(tr("log_turbo_scan"), "warn")
    try:
        page.scroll.to_top()
    except Exception:
        pass

    images: list[str] = []
    total_pages = 0
    same_bottom_count = 0
    boundary_retries = 0

    def collect_filtered(raw_list: list[str]):
        for src in raw_list:
            if src.startswith('//'):
                src = 'https:' + src
            if src.startswith('http') and src not in images:
                src_lower = src.lower()
                if not any(bad in src_lower for bad in bad_keywords):
                    images.append(src)
                    if on_new_image:
                        on_new_image(len(images), src)

    for _ in range(500):
        if stop_event and stop_event.is_set():
            log(tr("log_chapter_scan_aborted"), "warn")
            break

        prev_len = len(images)
        try:
            state = page.run_js(ATOMIC_SCAN_SENKURO_JS, target_chapter_id, True) or {}
        except Exception:
            break

        if total_pages == 0 and state.get('totalPages', 0) > 0:
            total_pages = state['totalPages']
            log(tr("log_total_pages", total=total_pages), "info")
            if on_total_pages:
                on_total_pages(total_pages)

        collect_filtered(state.get('imgs', []))

        if total_pages > 0 and len(images) >= total_pages:
            log(tr("log_collected_all_pages", count=len(images)), "success")
            break

        url_switched = state.get('urlSwitchedToNext', False)
        reached_boundary = state.get('reachedBoundary', False)

        if url_switched or reached_boundary:
            if total_pages > 0 and len(images) < total_pages and boundary_retries < 12:
                boundary_retries += 1
                if boundary_retries % 3 == 1:
                    log(tr("log_waiting_pages", cur=len(images), total=total_pages), "warn")
                try:
                    page.run_js('window.scrollBy(0, -500);')
                except Exception:
                    pass
                time.sleep(0.3)
                continue

            log(tr("log_senkuro_boundary", count=len(images)), "info")
            break

        moved = abs(state.get('newY', 0) - state.get('prevY', 0)) > 2
        grew = state.get('newHeight', 0) > state.get('prevHeight', 0)
        got_new = len(images) > prev_len

        if moved or grew or got_new:
            same_bottom_count = 0
            time.sleep(random.uniform(0.18, 0.28))
        else:
            same_bottom_count += 1
            if same_bottom_count >= 10:
                break
            time.sleep(0.25)

    return images


# ==============================================================================
# МАРШРУТИЗАЦІЯ ТА ЗАВАНТАЖЕННЯ
# ==============================================================================

def extract_chapters_from_main_page(
    page,
    url: str,
    on_log=None,
    stop_event: threading.Event | None = None,
    session: requests.Session | None = None
):
    if is_mangadex_site(url):
        active_session = session or create_http_session(page, urlparse(url).netloc or "mangadex.org")
        return _extract_chapters_mangadex(active_session, url, on_log=on_log, stop_event=stop_event)
    if is_senkuro_site(url):
        return _extract_chapters_senkuro(page, url, on_log=on_log, stop_event=stop_event)
    if is_madara_site(url):
        return _extract_chapters_madara(page, url, on_log=on_log, stop_event=stop_event)
    return _extract_chapters_lib(page, url, on_log=on_log, stop_event=stop_event)


def extract_images_from_reader(
    page,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None,
    session: requests.Session | None = None
):
    if is_mangadex_site(url):
        active_session = session or create_http_session(page, urlparse(url).netloc or "mangadex.org")
        return _extract_images_mangadex(
            active_session,
            url,
            on_new_image=on_new_image,
            on_total_pages=on_total_pages,
            on_log=on_log,
            stop_event=stop_event
        )
    if is_senkuro_site(url):
        return _extract_images_senkuro(
            page,
            url,
            on_new_image=on_new_image,
            on_total_pages=on_total_pages,
            on_log=on_log,
            stop_event=stop_event
        )
    if is_madara_site(url):
        return _extract_images_madara(
            page,
            url,
            on_new_image=on_new_image,
            on_total_pages=on_total_pages,
            on_log=on_log,
            stop_event=stop_event
        )
    return _extract_images_lib(
        page,
        url,
        on_new_image=on_new_image,
        on_total_pages=on_total_pages,
        on_log=on_log,
        stop_event=stop_event
    )


def download_image(
    session: requests.Session,
    url: str,
    folder_path: str,
    index: int,
    on_page_done=None,
    stop_event: threading.Event | None = None
) -> bool:
    if stop_event and stop_event.is_set():
        return False

    tmp_filepath = ""
    try:
        ext = url.split('.')[-1].split('?')[0]
        if len(ext) > 4 or not ext.isalnum():
            ext = 'jpg'

        filename = f"{index:03d}.{ext}"
        filepath = os.path.join(folder_path, filename)
        tmp_filepath = filepath + ".part"

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            if on_page_done:
                on_page_done(True)
            return True

        time.sleep(random.uniform(0.04, 0.12))

        if stop_event and stop_event.is_set():
            return False

        response = session.get(url, stream=True, timeout=15)
        response.raise_for_status()

        with open(tmp_filepath, 'wb') as f:
            for chunk in response.iter_content(1024 * 64):
                if stop_event and stop_event.is_set():
                    f.close()
                    if os.path.exists(tmp_filepath):
                        os.remove(tmp_filepath)
                    return False
                if chunk:
                    f.write(chunk)

        os.replace(tmp_filepath, filepath)

        if on_page_done:
            on_page_done(True)
        return True
    except Exception:
        if tmp_filepath and os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except Exception:
                pass
        if on_page_done:
            on_page_done(False)
        return False


def parse_slugs(url: str):
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip('/').split('/') if p]

    if is_mangadex_site(url):
        ch_id = _extract_mangadex_uuid(url, "chapter")
        if ch_id:
            return "mangadex", f"id-{ch_id[:8]}"
        manga_slug = parts[2] if len(parts) >= 3 and parts[0].lower() == "title" else (parts[1] if len(parts) >= 2 else "mangadex")
        return sanitize_folder_name(manga_slug), "chapter"

    if is_senkuro_site(url):
        manga_slug = parts[1] if len(parts) > 1 and parts[0].lower() == 'manga' else (parts[0] if parts else "manga")
        ch_id = parts[3] if len(parts) > 3 and parts[2].lower() == 'chapters' else "chapter"
        return manga_slug, f"id-{ch_id}"

    if is_madara_site(url):
        if parts and parts[0].lower() in ('manga', 'read', 'webtoon', 'manhwa', 'manhua'):
            manga_slug = parts[1] if len(parts) > 1 else "manga"
            raw_ch = parts[2].lower() if len(parts) > 2 else "chapter-1"
            match = re.search(r'chapter-([\d]+(?:[\.-]\d+)?)', raw_ch)
            ch_num = match.group(1).replace('-', '.') if match else "1"
            return manga_slug, f"v1-c{ch_num}"

    if parts and parts[0] == 'ru':
        parts = parts[1:]
    manga_slug = parts[0] if len(parts) > 0 else "manga"

    chapter_parts = []
    for p in parts:
        if p.startswith('v') or p.startswith('c') or p.isdigit() or p == 'read':
            if p != 'read':
                chapter_parts.append(p)
    chapter_slug = "-".join(chapter_parts) if chapter_parts else "chapter"
    return manga_slug, chapter_slug


def download_single_chapter(
    page,
    session: requests.Session,
    ch_url: str,
    base_save_dir: str,
    branch_folder: str = "",
    chapter_slug_override: str = "",
    manga_slug_override: str = "",
    on_total_pages=None,
    on_page_done=None,
    on_log=None,
    stop_event: threading.Event | None = None
) -> dict:
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    active_session = session or create_http_session(page, urlparse(ch_url).netloc or "mangadex.org")

    manga_slug, parsed_chapter_slug = parse_slugs(ch_url)
    if manga_slug_override:
        manga_slug = sanitize_folder_name(manga_slug_override)
    chapter_slug = chapter_slug_override or parsed_chapter_slug

    if is_mangadex_site(ch_url) and (not manga_slug_override or not chapter_slug_override):
        resolved_manga, resolved_ch = _resolve_mangadex_chapter_meta(
            active_session,
            ch_url,
            stop_event=stop_event
        )
        if not manga_slug_override:
            manga_slug = resolved_manga
        if not chapter_slug_override:
            chapter_slug = resolved_ch

    def resolve_save_dir(current_ch_slug: str) -> str:
        if branch_folder:
            return os.path.join(
                base_save_dir,
                manga_slug,
                sanitize_folder_name(branch_folder),
                current_ch_slug
            )
        return os.path.join(base_save_dir, manga_slug, current_ch_slug)

    save_dir = resolve_save_dir(chapter_slug)

    dir_ready = False
    submitted_count = 0
    completed_count = 0
    saved_count = 0
    known_total = 0
    lock = threading.Lock()
    workers = 10 if is_madara_site(ch_url) else 5

    def notify_progress():
        if on_page_done:
            on_page_done(completed_count, max(known_total, submitted_count))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        def handle_total_pages(total: int):
            nonlocal known_total
            with lock:
                known_total = total
                if on_total_pages:
                    on_total_pages(max(known_total, submitted_count))
                notify_progress()

        def handle_page_finished(ok: bool):
            nonlocal completed_count, saved_count
            with lock:
                completed_count += 1
                if ok:
                    saved_count += 1
                notify_progress()

        def handle_new_image(idx: int, img_url: str):
            nonlocal dir_ready, submitted_count, chapter_slug, save_dir
            with lock:
                if not dir_ready:
                    if not chapter_slug_override and is_senkuro_site(ch_url) and chapter_slug.startswith("id-"):
                        fallback_id = chapter_slug[3:]
                        chapter_slug = _detect_senkuro_chapter_slug(page, fallback_id)
                        save_dir = resolve_save_dir(chapter_slug)
                    os.makedirs(save_dir, exist_ok=True)
                    dir_ready = True
                submitted_count += 1
                if on_total_pages:
                    on_total_pages(max(known_total, submitted_count))
                notify_progress()
            executor.submit(
                download_image,
                active_session,
                img_url,
                save_dir,
                idx,
                handle_page_finished,
                stop_event
            )

        try:
            images = extract_images_from_reader(
                page,
                ch_url,
                on_new_image=handle_new_image,
                on_total_pages=handle_total_pages,
                on_log=on_log,
                stop_event=stop_event,
                session=active_session
            )
        except PermissionError as e:
            log(tr("log_perm_err", err=e), "error")
            return {
                "ok": False,
                "status": "failed",
                "reason_key": "fail_reason_perm",
                "reason_kwargs": {"err": str(e)},
                "saved": 0,
                "expected": 0,
                "save_dir": save_dir
            }
        except Exception as e:
            log(tr("log_chapter_proc_err", url=ch_url, err=e), "error")
            return {
                "ok": False,
                "status": "failed",
                "reason_key": "fail_reason_exception",
                "reason_kwargs": {"err": str(e)},
                "saved": 0,
                "expected": 0,
                "save_dir": save_dir
            }

        if stop_event and stop_event.is_set():
            return {
                "ok": False,
                "status": "stopped",
                "reason_key": "",
                "reason_kwargs": {},
                "saved": saved_count,
                "expected": max(known_total, submitted_count),
                "save_dir": save_dir
            }

        if not images:
            log(tr("log_no_images_found", url=ch_url), "error")
            return {
                "ok": False,
                "status": "failed",
                "reason_key": "fail_reason_no_images",
                "reason_kwargs": {},
                "saved": 0,
                "expected": 0,
                "save_dir": save_dir
            }

        with lock:
            if on_total_pages:
                on_total_pages(submitted_count)
            notify_progress()

    if stop_event and stop_event.is_set():
        return {
            "ok": False,
            "status": "stopped",
            "reason_key": "",
            "reason_kwargs": {},
            "saved": saved_count,
            "expected": max(known_total, submitted_count),
            "save_dir": save_dir
        }

    expected_total = max(known_total, submitted_count)

    if saved_count == 0:
        reason_kwargs = {"total": expected_total}
        log(tr("fail_reason_zero_saved", **reason_kwargs), "error")
        return {
            "ok": False,
            "status": "failed",
            "reason_key": "fail_reason_zero_saved",
            "reason_kwargs": reason_kwargs,
            "saved": 0,
            "expected": expected_total,
            "save_dir": save_dir
        }

    if saved_count < submitted_count:
        reason_kwargs = {
            "saved": saved_count,
            "total": expected_total,
            "failed": submitted_count - saved_count
        }
        log(tr("fail_reason_http_pages", **reason_kwargs), "warn")
        return {
            "ok": False,
            "status": "partial",
            "reason_key": "fail_reason_http_pages",
            "reason_kwargs": reason_kwargs,
            "saved": saved_count,
            "expected": expected_total,
            "save_dir": save_dir
        }

    if known_total > 0 and submitted_count < known_total:
        reason_kwargs = {
            "saved": saved_count,
            "total": known_total
        }
        log(tr("fail_reason_slow_load", **reason_kwargs), "warn")
        return {
            "ok": False,
            "status": "partial",
            "reason_key": "fail_reason_slow_load",
            "reason_kwargs": reason_kwargs,
            "saved": saved_count,
            "expected": known_total,
            "save_dir": save_dir
        }

    log(tr("log_downloaded_to", path=save_dir), "success")
    return {
        "ok": True,
        "status": "ok",
        "reason_key": "",
        "reason_kwargs": {},
        "saved": saved_count,
        "expected": expected_total,
        "save_dir": save_dir
    }


def filter_chapters_by_range(
    chapters_list: list[dict],
    user_input: str,
    branch_key: str | None = None
) -> list[dict]:
    pool = chapters_list
    if branch_key:
        pool = [ch for ch in chapters_list if ch.get('branch_key') == branch_key]

    user_input = user_input.strip().lower()
    if user_input == 'all':
        return pool

    match_range = re.match(r'^([\d\.]+)\s*-\s*([\d\.]+)$', user_input)
    if match_range:
        try:
            start_num = float(match_range.group(1))
            end_num = float(match_range.group(2))
            if start_num > end_num:
                start_num, end_num = end_num, start_num
            return [ch for ch in pool if start_num <= ch['num_float'] <= end_num]
        except ValueError:
            pass

    try:
        single_num = float(user_input)
        return [ch for ch in pool if ch['num_float'] == single_num]
    except ValueError:
        pass

    return []
