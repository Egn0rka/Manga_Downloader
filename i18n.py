import os
import sys
import json
import threading

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

LANGUAGES = {
    "uk": "Українська",
    "ru": "Русский",
    "en": "English",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "uk": {
        "app_title": "Manga_Downloader",
        "subtitle": "MangaLib • Manga18FX • Webtoon.xyz • Senkuro ",
        "lang_label": "Мова:",
        "btn_confirm_auth": "Підтвердити вхід 18+",
        "lbl_url": "Посилання:",
        "ph_url": "Вставте посилання на головну сторінку тайтлу або конкретну главу (/read/... або /chapter-...)...",
        "btn_get_chapters": "Отримати глави",
        "btn_dl_chapter": "Завантажити главу",
        "tip_dl_chapter": "Використовуйте, якщо вставили пряме посилання на /read/... або /chapter-...",
        "lbl_save_to": "Зберегти у:",
        "btn_browse": "Обрати...",
        "btn_open_dir": "Відкрити папку",
        "sec_chapters": "Список глав",
        "lbl_branch": "Перекладач / Гілка:",
        "all_translators": "Усі перекладачі ({count})",
        "branch_item": "{team} ({count} гл.)",
        "chapter_item": "Том {vol}  •  Глава {num}   [{team}]",
        "ph_range": "Діапазон (напр. 10-25 або 106)",
        "btn_apply_range": "Виділити діапазон",
        "btn_select_all": "Обрати всі у гілці",
        "btn_deselect_all": "Зняти всі у гілці",
        "counter_filtered": "Обрано у гілці: {vis_chk} / {vis_tot}  (всього до завантаження: {all_chk})",
        "counter_simple": "Обрано: {all_chk} / {all_tot}",
        "hint_multi_branch": "Виявлено {count} гілки перекладу — папки розсортуються за перекладачем.",
        "btn_dl_selected": "Завантажити обрані глави",
        "btn_stop": "Зупинити",
        "status_idle": "Очікування запуску...",
        "status_scanning": "Сканування списку глав...",
        "status_ready": "Список глав готовий до вибору.",
        "status_done": "Завантаження завершено!",
        "status_stopped": "Операцію зупинено.",
        "status_error": "Виникла помилка під час виконання.",
        "prog_chapters": "Глави: %v / %m (%p%)",
        "prog_pages": "Сторінки поточної глави: %v / %m (%p%)",
        "prog_scanning_pages": "Сканування сторінок глави...",
        "chapter_label": "Глава {num} (Том {vol}){team_tag}",
        "dlg_choose_dir": "Оберіть папку для збереження",
        "dlg_empty_title": "Порожнє поле",
        "dlg_empty_msg": "Введіть посилання на тайтл або главу.",
        "dlg_unsupported_title": "Непідтримуваний домен",
        "dlg_unsupported_msg": "Підтримуються домени сімейства Lib.Social (MangaLib, HentaiLib, SlashLib, YaoiLib), а також Manga18FX і Webtoon.xyz.",
        "dlg_title_link_title": "Посилання на тайтл",
        "dlg_title_link_msg": "Це посилання на головну сторінку тайтлу. Спочатку натисніть «Отримати глави».",
        "dlg_select_branch_title": "Оберіть гілку перекладу",
        "dlg_select_branch_msg": (
            "У цьому тайтлі є декілька гілок перекладу.\n\n"
            "Оберіть потрібного перекладача у випадаючому списку «Перекладач / Гілка» справа, "
            "щоб виділити діапазон лише для його перекладу без дублікатів."
        ),
        "dlg_range_title": "Діапазон",
        "dlg_range_not_found": "Не знайдено глав за запитом '{expr}' у поточній гілці.",
        "dlg_auth_title": "Авторизація 18+",
        "dlg_auth_msg": (
            "Перевірте авторизацію 18+ у відкритому вікні браузера Chromium.\n\n"
            "Після входу в акаунт натисніть «ОК» (або кнопку «Підтвердити вхід 18+» у вікні програми)."
        ),
        "default_branch": "Основний переклад",
        "branch_numbered": "Гілка #{bid}",
        "log_init_browser": "Ініціалізація браузера (Chromium)...",
        "log_goto_title": "Переходимо на головну сторінку тайтлу: {url}",
        "log_page_load_err": "Помилка завантаження сторінки: {err}",
        "log_getting_chapters": "Отримання списку глав та гілок перекладу...",
        "log_madara_expand": "Розгортання списку глав (пошук кнопки Show More)...",
        "log_madara_show_more": "Натиснуто 'Show More', підвантажуємо всі глави...",
        "log_api_fallback_html": "API не віддало повний список. Запускаємо сканування HTML...",
        "log_scan_stopped": "Сканування глав зупинено користувачем.",
        "log_goto_chapter": "Переходимо за посиланням глави: {url}",
        "log_reader_open_err": "Помилка відкриття читалки: {err}",
        "log_madara_instant_found": "Миттєво знайдено {count} сторінок!",
        "log_madara_bottom_reached": "Досягнуто кінця глави. Зібрано {count} сторінок.",
        "log_getting_pages": "Отримання даних сторінок...",
        "log_total_pages": "Визначено загальну кількість сторінок у главі: {total}",
        "log_turbo_scan": "Запускаємо сканування зображень ...",
        "log_chapter_scan_aborted": "Сканування глави перервано.",
        "log_collected_all_pages": "Успішно зібрано всі {count} сторінок!",
        "log_waiting_pages": "Чекаємо підвантаження сторінок ({cur}/{total})...",
        "log_pages_still_loading": "Сторінки глави ще підвантажуються (знайдено {count}), очікуємо...",
        "log_end_marker": "Досягнуто кінця глави (знайдено блок коментарів/навігації).",
        "log_perm_err": "Помилка доступу під час створення папки: {err}",
        "log_chapter_proc_err": "Помилка під час обробки глави {url}: {err}",
        "log_no_images_found": "Не вдалося знайти зображення для {url}",
        "log_downloaded_to": "✓ Завантажено у: {path}",
        "log_auth_warn": "УВАГА: Перевірте авторизацію 18+ у відкритому браузері та натисніть «Підтвердити вхід 18+».",
        "log_unexpected_err": "Непередбачена помилка: {err}",
        "log_found_branches": "Знайдено {total} записів у {branches} гілках перекладу: {summary}",
        "log_found_chapters": "Знайдено глав: {total} (від {first} до {last})",
        "log_no_chapters": "Не вдалося знайти список глав на сторінці.",
        "log_start_download": "Починаємо завантаження {total} глав...",
        "log_download_stopped": "Завантаження зупинено користувачем.",
        "log_processing_chapter": "[{idx}/{total}] Обробка: {label}...",
        "log_all_done": "Усі обрані глави успішно завантажені!",
        "log_direct_chapter": "Вставлено посилання на конкретну главу — запускаємо її завантаження напряму.",
        "log_sending_stop": "Надсилаємо сигнал зупинки...",
        "fail_reason_perm": "помилка доступу до папки ({err})",
        "fail_reason_exception": "помилка обробки сторінки ({err})",
        "fail_reason_no_images": "не знайдено жодної сторінки (повільний інтернет або збій завантаження)",
        "fail_reason_zero_saved": "не вдалося зберегти жодної сторінки з {total} (таймаут або помилка мережі)",
        "fail_reason_http_pages": "завантажено {saved} з {total} стор. ({failed} не завантажились через мережу/таймаут)",
        "fail_reason_slow_load": "завантажено {saved} з {total} стор. (не всі сторінки встигли підвантажитись через повільний інтернет)",
        "fail_reason_unknown": "невідома помилка завантаження",
        "report_header": "=== ЗАГАЛЬНИЙ ЗВІТ ЗАВАНТАЖЕННЯ ===",
        "report_footer": "=====================================",
        "report_stats_ok": "Успішно завантажено: {succeeded} з {total} глав.",
        "report_stats_stopped": "Операцію зупинено. Успішно завантажено до зупинки: {succeeded} з {total} глав.",
        "report_failed_count": "Не вдалося або завантажено неповністю: {failed} глав:",
        "report_more_items": "  ... та ще {count} глав (повний список у журналі подій).",
        "subtitle": "MangaLib • Manga18FX • Webtoon.xyz • Senkuro • MangaDex",
        "dlg_unsupported_msg": "Підтримуються домени сімейства Lib.Social (MangaLib, HentaiLib, SlashLib, YaoiLib), а також Manga18FX, Webtoon.xyz, Senkuro та MangaDex.",
        "log_mangadex_api_chapters": "Отримання списку глав через MangaDex API...",
        "log_mangadex_api_pages": "Отримано {count} сторінок в оригінальній якості через MangaDex API.",
        "log_mangadex_rate_limit": "Перевищено ліміт запитів MangaDex API, очікуємо {sec} с...",
        "log_mangadex_api_err": "Помилка запиту до MangaDex API: {err}",

    },
    "ru": {
        "app_title": "Manga_Downloader",
        "subtitle": "MangaLib •  Manga18FX • Webtoon.xyz • Senkuro ",
        "lang_label": "Язык:",
        "btn_confirm_auth": "Подтвердить вход 18+",
        "lbl_url": "Ссылка:",
        "ph_url": "Вставьте ссылку на главную страницу тайтла или конкретную главу (/read/... или /chapter-...)...",
        "btn_get_chapters": "Получить главы",
        "btn_dl_chapter": "Скачать главу",
        "tip_dl_chapter": "Используйте, если вставили прямую ссылку на /read/... или /chapter-...",
        "lbl_save_to": "Сохранить в:",
        "btn_browse": "Выбрать...",
        "btn_open_dir": "Открыть папку",
        "sec_chapters": "Список глав",
        "lbl_branch": "Переводчик / Ветка:",
        "all_translators": "Все переводчики ({count})",
        "branch_item": "{team} ({count} гл.)",
        "chapter_item": "Том {vol}  •  Глава {num}   [{team}]",
        "ph_range": "Диапазон (напр. 10-25 или 106)",
        "btn_apply_range": "Выделить диапазон",
        "btn_select_all": "Выбрать все в ветке",
        "btn_deselect_all": "Снять все в ветке",
        "counter_filtered": "Выбрано в ветке: {vis_chk} / {vis_tot}  (всего к загрузке: {all_chk})",
        "counter_simple": "Выбрано: {all_chk} / {all_tot}",
        "hint_multi_branch": "Обнаружено {count} ветки перевода — папки рассортируются по переводчику.",
        "btn_dl_selected": "Скачать выбранные главы",
        "btn_stop": "Остановить",
        "status_idle": "Ожидание запуска...",
        "status_scanning": "Сканирование списка глав...",
        "status_ready": "Список глав готов к выбору.",
        "status_done": "Загрузка завершена!",
        "status_stopped": "Операция остановлена.",
        "status_error": "Произошла ошибка при выполнении.",
        "prog_chapters": "Главы: %v / %m (%p%)",
        "prog_pages": "Страницы текущей главы: %v / %m (%p%)",
        "prog_scanning_pages": "Сканирование страниц главы...",
        "chapter_label": "Глава {num} (Том {vol}){team_tag}",
        "dlg_choose_dir": "Выберите папку для сохранения",
        "dlg_empty_title": "Пустое поле",
        "dlg_empty_msg": "Введите ссылку на тайтл или главу.",
        "dlg_unsupported_title": "Неподдерживаемый домен",
        "dlg_unsupported_msg": "Поддерживаются домены семейства Lib.Social (MangaLib, HentaiLib, SlashLib, YaoiLib), а также Manga18FX и Webtoon.xyz.",
        "dlg_title_link_title": "Ссылка на тайтл",
        "dlg_title_link_msg": "Это ссылка на главную страницу тайтла. Сначала нажмите «Получить главы».",
        "dlg_select_branch_title": "Выберите ветку перевода",
        "dlg_select_branch_msg": (
            "В этом тайтле есть несколько веток перевода.\n\n"
            "Выберите нужного переводчика в выпадающем списке «Переводчик / Ветка» справа, "
            "чтобы выделить диапазон только для его перевода без дубликатов."
        ),
        "dlg_range_title": "Диапазон",
        "dlg_range_not_found": "Не найдено глав по запросу '{expr}' в текущей ветке.",
        "dlg_auth_title": "Авторизация 18+",
        "dlg_auth_msg": (
            "Проверьте авторизацию 18+ в открытом окне браузера Chromium.\n\n"
            "После входа в аккаунт нажмите «ОК» (или кнопку «Подтвердить вход 18+» в окне программы)."
        ),
        "default_branch": "Основной перевод",
        "branch_numbered": "Ветка #{bid}",
        "log_init_browser": "Инициализация браузера (Chromium)...",
        "log_goto_title": "Переходим на главную страницу тайтла: {url}",
        "log_page_load_err": "Ошибка загрузки страницы: {err}",
        "log_getting_chapters": "Получение списка глав и веток перевода...",
        "log_madara_expand": "Разворачивание списка глав (поиск кнопки Show More)...",
        "log_madara_show_more": "Нажато 'Show More', подгружаем все главы...",
        "log_api_fallback_html": "API не отдало полный список. Запускаем сканирование HTML...",
        "log_scan_stopped": "Сканирование глав остановлено пользователем.",
        "log_goto_chapter": "Переходим по ссылке главы: {url}",
        "log_reader_open_err": "Ошибка открытия читалки: {err}",
        "log_madara_instant_found": "Мгновенно найдено {count} страниц ",
        "log_madara_bottom_reached": "Достигнут конец главы. Собрано {count} страниц.",
        "log_getting_pages": "Получение данных страниц...",
        "log_total_pages": "Определено общее количество страниц в главе: {total}",
        "log_turbo_scan": "Запускаем сканирование изображений ...",
        "log_chapter_scan_aborted": "Сканирование главы прервано.",
        "log_collected_all_pages": "Успешно собраны все {count} страниц!",
        "log_waiting_pages": "Ждем подгрузки страниц ({cur}/{total})...",
        "log_pages_still_loading": "Страницы главы еще подгружаются (найдено {count}), ожидаем...",
        "log_end_marker": "Достигнут конец главы (найден блок комментариев/навигации).",
        "log_perm_err": "Ошибка доступа при создании папки: {err}",
        "log_chapter_proc_err": "Ошибка при обработке главы {url}: {err}",
        "log_no_images_found": "Не удалось найти изображения для {url}",
        "log_downloaded_to": "✓ Загружено в: {path}",
        "log_auth_warn": "ВНИМАНИЕ: Проверьте авторизацию 18+ в открытом браузере и нажмите «Подтвердить вход 18+».",
        "log_unexpected_err": "Непредвиденная ошибка: {err}",
        "log_found_branches": "Найдено {total} записей в {branches} ветках перевода: {summary}",
        "log_found_chapters": "Найдено глав: {total} (от {first} до {last})",
        "log_no_chapters": "Не удалось найти список глав на странице.",
        "log_start_download": "Начинаем загрузку {total} глав...",
        "log_download_stopped": "Загрузка остановлена пользователем.",
        "log_processing_chapter": "[{idx}/{total}] Обработка: {label}...",
        "log_all_done": "Все выбранные главы успешно загружены!",
        "log_direct_chapter": "Вставлена ссылка на конкретную главу — запускаем ее загрузку напрямую.",
        "log_sending_stop": "Отправляем сигнал остановки...",
        "fail_reason_perm": "ошибка доступа к папке ({err})",
        "fail_reason_exception": "ошибка обработки страницы ({err})",
        "fail_reason_no_images": "не найдено ни одной страницы (медленный интернет или сбой загрузки)",
        "fail_reason_zero_saved": "не удалось сохранить ни одной страницы из {total} (таймаут или ошибка сети)",
        "fail_reason_http_pages": "скачано {saved} из {total} стр. ({failed} не скачались из-за сети/таймаута)",
        "fail_reason_slow_load": "скачано {saved} из {total} стр. (не все страницы успели подгрузиться из-за медленного интернета)",
        "fail_reason_unknown": "неизвестная ошибка загрузки",
        "report_header": "=== ОБЩИЙ ОТЧЕТ ЗАГРУЗКИ ===",
        "report_footer": "=====================================",
        "report_stats_ok": "Успешно загружено: {succeeded} из {total} глав.",
        "report_stats_stopped": "Операция остановлена. Успешно загружено до остановки: {succeeded} из {total} глав.",
        "report_failed_count": "Не удалось или загружено неполностью: {failed} глав:",
        "report_more_items": "  ... и еще {count} глав (полный список в журнале событий).",
        "subtitle": "MangaLib • Manga18FX • Webtoon.xyz • Senkuro • MangaDex",
        "dlg_unsupported_msg": "Поддерживаются домены семейства Lib.Social (MangaLib, HentaiLib, SlashLib, YaoiLib), а также Manga18FX, Webtoon.xyz, Senkuro и MangaDex.",
        "log_mangadex_api_chapters": "Получение списка глав через MangaDex API...",
        "log_mangadex_api_pages": "Получено {count} страниц в оригинальном качестве через MangaDex API.",
        "log_mangadex_rate_limit": "Превышен лимит запросов MangaDex API, ожидаем {sec} с...",
        "log_mangadex_api_err": "Ошибка запроса к MangaDex API: {err}",
    },
    "en": {
        "app_title": "Manga_Downloader",
        "subtitle": "MangaLib • Manga18FX • Webtoon.xyz • Senkuro ",
        "lang_label": "Language:",
        "btn_confirm_auth": "Confirm 18+ Login",
        "lbl_url": "URL:",
        "ph_url": "Paste a link to the title's main page or a specific chapter (/read/... or /chapter-...)...",
        "btn_get_chapters": "Get Chapters",
        "btn_dl_chapter": "Download Chapter",
        "tip_dl_chapter": "Use this if you pasted a direct /read/... or /chapter-... link",
        "lbl_save_to": "Save to:",
        "btn_browse": "Browse...",
        "btn_open_dir": "Open Folder",
        "sec_chapters": "Chapters List",
        "lbl_branch": "Translator / Branch:",
        "all_translators": "All translators ({count})",
        "branch_item": "{team} ({count} ch.)",
        "chapter_item": "Vol. {vol}  •  Ch. {num}   [{team}]",
        "ph_range": "Range (e.g. 10-25 or 106)",
        "btn_apply_range": "Select Range",
        "btn_select_all": "Select All in Branch",
        "btn_deselect_all": "Deselect All in Branch",
        "counter_filtered": "Selected in branch: {vis_chk} / {vis_tot}  (total to download: {all_chk})",
        "counter_simple": "Selected: {all_chk} / {all_tot}",
        "hint_multi_branch": "Detected {count} translation branches — folders will be sorted by translator.",
        "btn_dl_selected": "Download Selected Chapters",
        "btn_stop": "Stop",
        "status_idle": "Waiting to start...",
        "status_scanning": "Scanning chapters list...",
        "status_ready": "Chapters list ready for selection.",
        "status_done": "Download complete!",
        "status_stopped": "Operation stopped.",
        "status_error": "An error occurred during execution.",
        "prog_chapters": "Chapters: %v / %m (%p%)",
        "prog_pages": "Current chapter pages: %v / %m (%p%)",
        "prog_scanning_pages": "Scanning chapter pages...",
        "chapter_label": "Chapter {num} (Vol. {vol}){team_tag}",
        "dlg_choose_dir": "Select Save Folder",
        "dlg_empty_title": "Empty Field",
        "dlg_empty_msg": "Please enter a link to a title or chapter.",
        "dlg_unsupported_title": "Unsupported Domain",
        "dlg_unsupported_msg": "Supported domains include the Lib.Social family (MangaLib, HentaiLib, SlashLib, YaoiLib ), as well as Manga18FX and Webtoon.xyz.",
        "dlg_title_link_title": "Title Link",
        "dlg_title_link_msg": "This is a link to the title's main page. Click «Get Chapters» first.",
        "dlg_select_branch_title": "Select Translation Branch",
        "dlg_select_branch_msg": (
            "This title has multiple translation branches.\n\n"
            "Select the desired translator in the «Translator / Branch» dropdown on the right "
            "to select a range for their translation without duplicates."
        ),
        "dlg_range_title": "Range",
        "dlg_range_not_found": "No chapters found matching '{expr}' in the current branch.",
        "dlg_auth_title": "18+ Authorization",
        "dlg_auth_msg": (
            "Please verify 18+ authorization in the opened Chromium browser window.\n\n"
            "After logging in, click «OK» (or the «Confirm 18+ Login» button in the app window)."
        ),
        "default_branch": "Main translation",
        "branch_numbered": "Branch #{bid}",
        "log_init_browser": "Initializing browser (Chromium)...",
        "log_goto_title": "Navigating to title page: {url}",
        "log_page_load_err": "Page load error: {err}",
        "log_getting_chapters": "Fetching chapters and translation branches...",
        "log_madara_expand": "Expanding chapters list (searching for Show More button)...",
        "log_madara_show_more": "Clicked 'Show More', loading all chapters...",
        "log_api_fallback_html": "API did not return the full list. Starting HTML scan...",
        "log_scan_stopped": "Chapter scan stopped by user.",
        "log_goto_chapter": "Navigating to chapter URL: {url}",
        "log_reader_open_err": "Reader open error: {err}",
        "log_madara_instant_found": "Instantly found {count} pages !",
        "log_madara_bottom_reached": "Reached end of chapter. Collected {count} pages.",
        "log_getting_pages": "Fetching page data...",
        "log_total_pages": "Detected total pages in chapter: {total}",
        "log_turbo_scan": "Starting image scan (collecting + parallel download)...",
        "log_chapter_scan_aborted": "Chapter scan aborted.",
        "log_collected_all_pages": "Successfully collected all {count} pages!",
        "log_waiting_pages": "Waiting for pages to load ({cur}/{total})...",
        "log_pages_still_loading": "Chapter pages are still loading (found {count}), waiting...",
        "log_end_marker": "Reached end of chapter (comments/navigation block detected).",
        "log_perm_err": "Permission error while creating folder: {err}",
        "log_chapter_proc_err": "Error processing chapter {url}: {err}",
        "log_no_images_found": "Could not find images for {url}",
        "log_downloaded_to": "✓ Downloaded to: {path}",
        "log_auth_warn": "WARNING: Verify 18+ authorization in the opened browser and click «Confirm 18+ Login».",
        "log_unexpected_err": "Unexpected error: {err}",
        "log_found_branches": "Found {total} entries across {branches} translation branches: {summary}",
        "log_found_chapters": "Found chapters: {total} (from {first} to {last})",
        "log_no_chapters": "Could not find chapters list on the page.",
        "log_start_download": "Starting download of {total} chapters...",
        "log_download_stopped": "Download stopped by user.",
        "log_processing_chapter": "[{idx}/{total}] Processing: {label}...",
        "log_all_done": "All selected chapters downloaded successfully!",
        "log_direct_chapter": "Direct chapter link detected — starting direct download.",
        "log_sending_stop": "Sending stop signal...",
        "fail_reason_perm": "folder permission error ({err})",
        "fail_reason_exception": "page processing error ({err})",
        "fail_reason_no_images": "no pages found (slow internet or page load failure)",
        "fail_reason_zero_saved": "failed to save any of {total} pages (timeout or network error)",
        "fail_reason_http_pages": "downloaded {saved} of {total} pages ({failed} failed due to network/timeout)",
        "fail_reason_slow_load": "downloaded {saved} of {total} pages (remaining pages failed to lazy-load due to slow internet)",
        "fail_reason_unknown": "unknown download error",
        "report_header": "=== DOWNLOAD SUMMARY REPORT ===",
        "report_footer": "=====================================",
        "report_stats_ok": "Successfully downloaded: {succeeded} of {total} chapters.",
        "report_stats_stopped": "Operation stopped. Successfully downloaded before stop: {succeeded} of {total} chapters.",
        "report_failed_count": "Failed or incomplete chapters: {failed}:",
        "report_more_items": "  ... and {count} more chapters (see full list in the event log).",
        "subtitle": "MangaLib • Manga18FX • Webtoon.xyz • Senkuro • MangaDex",
        "dlg_unsupported_msg": "Supported domains include the Lib.Social family (MangaLib, HentaiLib, SlashLib, YaoiLib), as well as Manga18FX, Webtoon.xyz, Senkuro, and MangaDex.",
        "log_mangadex_api_chapters": "Fetching chapters list via MangaDex API...",
        "log_mangadex_api_pages": "Fetched {count} original-quality pages via MangaDex API.",
        "log_mangadex_rate_limit": "MangaDex API rate limit reached, waiting {sec}s...",
        "log_mangadex_api_err": "MangaDex API request error: {err}",
    },
}

_lock = threading.Lock()
_current_lang = "en"


def _load_saved_language() -> str:
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                lang = data.get("language", "en")
                if lang in TRANSLATIONS:
                    return lang
    except Exception:
        pass
    return "en"


def save_language_preference(lang_code: str):
    if lang_code not in TRANSLATIONS:
        return
    try:
        data = {}
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        data["language"] = lang_code
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_language(lang_code: str, persist: bool = True):
    global _current_lang
    if lang_code not in TRANSLATIONS:
        return
    with _lock:
        _current_lang = lang_code
    if persist:
        save_language_preference(lang_code)


def get_language() -> str:
    with _lock:
        return _current_lang


def tr(key: str, **kwargs) -> str:
    with _lock:
        lang = _current_lang
    text = TRANSLATIONS.get(lang, TRANSLATIONS["uk"]).get(key)
    if text is None:
        text = TRANSLATIONS["uk"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


_current_lang = _load_saved_language()
