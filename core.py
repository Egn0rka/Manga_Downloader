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

SUPPORTED_KEYWORDS = LIB_SOCIAL_KEYWORDS + MADARA_KEYWORDS
AGE_RESTRICTED_KEYWORDS = ["hentai", "slash", "shlib", "yaoi"]


def is_supported_url(url: str) -> bool:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    return any(kw in netloc for kw in SUPPORTED_KEYWORDS)


def is_madara_site(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return any(kw in netloc for kw in MADARA_KEYWORDS)


def is_chapter_url(url: str) -> bool:
    if is_madara_site(url):
        return "/chapter-" in urlparse(url).path.lower()
    return "/read/" in url


def requires_age_verification(url: str) -> bool:
    if is_madara_site(url):
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
        ua = page.run_js("return navigator.userAgent;")
    except Exception:
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
            const keys = ["мені є 18", "мне есть 18", "вход", "да"];
            const btns = Array.from(document.querySelectorAll('button'));
            for (const btn of btns) {
                const txt = (btn.innerText || "").toLowerCase();
                if (keys.some(k => txt.includes(k))) {
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
    is_default_team = not raw_team
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
# ОРИГІНАЛЬНА ЛОГІКА ДЛЯ LIB.SOCIAL (MANGALIB / HENTAILIB / SLASHLIB)
# ==============================================================================

def _extract_chapters_lib(page, url: str, on_log=None, stop_event: threading.Event | None = None):
    """Отримує список усіх глав та гілок перекладу з головної сторінки тайтлу."""
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
# ОРИГІНАЛЬНА ЛОГІКА ДЛЯ MADARA (MANGA18FX.COM ТА WEBTOON.XYZ — МИТТЄВИЙ РЕЖИМ)
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
# МАРШРУТИЗАЦІЯ ТА ЗАВАНТАЖЕННЯ
# ==============================================================================

def extract_chapters_from_main_page(page, url: str, on_log=None, stop_event: threading.Event | None = None):
    if is_madara_site(url):
        return _extract_chapters_madara(page, url, on_log=on_log, stop_event=stop_event)
    return _extract_chapters_lib(page, url, on_log=on_log, stop_event=stop_event)


def extract_images_from_reader(
    page,
    url: str,
    on_new_image=None,
    on_total_pages=None,
    on_log=None,
    stop_event: threading.Event | None = None
):
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

    try:
        ext = url.split('.')[-1].split('?')[0]
        if len(ext) > 4 or not ext.isalnum():
            ext = 'jpg'

        filename = f"{index:03d}.{ext}"
        filepath = os.path.join(folder_path, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            if on_page_done:
                on_page_done(True)
            return True

        time.sleep(random.uniform(0.04, 0.12))

        if stop_event and stop_event.is_set():
            return False

        response = session.get(url, stream=True, timeout=15)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(1024 * 64):
                if stop_event and stop_event.is_set():
                    return False
                if chunk:
                    f.write(chunk)

        if on_page_done:
            on_page_done(True)
        return True
    except Exception:
        if on_page_done:
            on_page_done(False)
        return False


def parse_slugs(url: str):
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip('/').split('/') if p]

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
    on_total_pages=None,
    on_page_done=None,
    on_log=None,
    stop_event: threading.Event | None = None
) -> bool:
    def log(msg, level="info"):
        if on_log:
            on_log(msg, level)

    manga_slug, chapter_slug = parse_slugs(ch_url)
    if branch_folder:
        save_dir = os.path.join(
            base_save_dir,
            manga_slug,
            sanitize_folder_name(branch_folder),
            chapter_slug
        )
    else:
        save_dir = os.path.join(base_save_dir, manga_slug, chapter_slug)

    dir_ready = False
    submitted_count = 0
    completed_count = 0
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

        def handle_page_finished(_ok: bool):
            nonlocal completed_count
            with lock:
                completed_count += 1
                notify_progress()

        def handle_new_image(idx: int, img_url: str):
            nonlocal dir_ready, submitted_count
            with lock:
                if not dir_ready:
                    os.makedirs(save_dir, exist_ok=True)
                    dir_ready = True
                submitted_count += 1
                if on_total_pages:
                    on_total_pages(max(known_total, submitted_count))
                notify_progress()
            executor.submit(
                download_image,
                session,
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
                stop_event=stop_event
            )
        except PermissionError as e:
            log(tr("log_perm_err", err=e), "error")
            return False
        except Exception as e:
            log(tr("log_chapter_proc_err", url=ch_url, err=e), "error")
            return False

        if not images:
            log(tr("log_no_images_found", url=ch_url), "error")
            return False

        with lock:
            if on_total_pages:
                on_total_pages(submitted_count)
            notify_progress()

    if stop_event and stop_event.is_set():
        return False

    log(tr("log_downloaded_to", path=save_dir), "success")
    return True


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