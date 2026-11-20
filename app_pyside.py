import os
import sys
import time
import queue
import random
import threading
from collections import Counter
from urllib.parse import urlparse

if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QColor, QTextCursor, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFrame,
    QSplitter,
    QComboBox
)

import core
from i18n import LANGUAGES, tr, get_language, set_language


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #16181d;
    color: #e4e6eb;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QFrame#Card {
    background-color: #1f2229;
    border: 1px solid #2d323e;
    border-radius: 10px;
}
QLabel#TitleLabel {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#SubtitleLabel {
    font-size: 12px;
    color: #9aa1b2;
}
QLabel#SectionHeader {
    font-size: 13px;
    font-weight: 600;
    color: #cbd2e0;
}
QLineEdit, QComboBox {
    background-color: #14161b;
    border: 1px solid #323846;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f0f2f5;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1a1d24;
    border: 1px solid #323846;
    color: #f0f2f5;
    selection-background-color: #2563eb;
}
QPushButton {
    background-color: #2a2f3b;
    border: 1px solid #3a4152;
    border-radius: 6px;
    padding: 7px 14px;
    color: #e4e6eb;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #353b4a;
}
QPushButton:disabled {
    background-color: #1c1f26;
    color: #5c6375;
    border-color: #252932;
}
QPushButton#PrimaryBtn {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton#PrimaryBtn:hover {
    background-color: #1d4ed8;
}
QPushButton#SuccessBtn {
    background-color: #059669;
    border-color: #10b981;
    color: #ffffff;
}
QPushButton#SuccessBtn:hover {
    background-color: #047857;
}
QPushButton#DangerBtn {
    background-color: #dc2626;
    border-color: #ef4444;
    color: #ffffff;
}
QPushButton#DangerBtn:hover {
    background-color: #b91c1c;
}
QPushButton#AuthBtn, QPushButton#WarnBtn {
    background-color: #d97706;
    border-color: #f59e0b;
    color: #ffffff;
}
QPushButton#AuthBtn:hover, QPushButton#WarnBtn:hover {
    background-color: #b45309;
}
QListWidget {
    background-color: #14161b;
    border: 1px solid #2d323e;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 5px 8px;
    border-radius: 4px;
}
QListWidget::item:hover {
    background-color: #222630;
}
QListWidget::item:selected {
    background-color: #26334d;
    color: #ffffff;
}
QProgressBar {
    background-color: #14161b;
    border: 1px solid #2d323e;
    border-radius: 6px;
    height: 18px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 5px;
}
QProgressBar#PageBar::chunk {
    background-color: #10b981;
}
QTextEdit {
    background-color: #111317;
    border: 1px solid #2d323e;
    border-radius: 6px;
    padding: 6px;
    font-family: "Consolas", "JetBrains Mono", monospace;
    font-size: 12px;
}
"""


class BrowserWorker(QThread):
    """Єдиний фоновий потік, що керує Chromium і завантаженням без блокування GUI."""

    log_signal = Signal(str, str)                # (message, level)
    chapters_loaded = Signal(list)               # list[dict]
    chapter_progress = Signal(int, int, str)     # (current_idx, total_chapters, label)
    page_progress = Signal(int, int)             # (done_pages, total_pages)
    auth_required = Signal()
    download_report = Signal(dict)               # summary report dict
    task_finished = Signal(str)                  # ("scan" | "download" | "stopped" | "error")
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cmd_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.auth_event = threading.Event()
        self._shutdown = False

        self.page = None
        self.session = None
        self.current_domain = ""
        self.auth_confirmed_domains: set[str] = set()

    def enqueue_scan(self, url: str):
        self.stop_event.clear()
        self.cmd_queue.put({"type": "scan", "url": url})

    def enqueue_download(self, chapters: list[dict], save_dir: str, separate_by_branch: bool = False):
        self.stop_event.clear()
        self.cmd_queue.put({
            "type": "download",
            "chapters": chapters,
            "save_dir": save_dir,
            "separate_by_branch": separate_by_branch
        })

    def request_stop(self):
        self.stop_event.set()
        self.auth_event.set()

    def confirm_auth(self):
        self.auth_event.set()

    def shutdown(self):
        self._shutdown = True
        self.stop_event.set()
        self.auth_event.set()
        self.cmd_queue.put({"type": "shutdown"})

    def _ensure_browser_and_auth(self, url: str) -> bool:
        domain = urlparse(url).netloc

        if self.page is None:
            self.page = core.init_browser(on_log=self.log_signal.emit)

        if core.requires_age_verification(url) and domain not in self.auth_confirmed_domains:
            self.log_signal.emit(tr("log_auth_warn"), "warn")
            self.auth_event.clear()
            self.auth_required.emit()
            self.auth_event.wait()

            if self.stop_event.is_set() or self._shutdown:
                return False

            self.auth_confirmed_domains.add(domain)

        if self.session is None or self.current_domain != domain:
            if self.session is not None:
                try:
                    self.session.close()
                except Exception:
                    pass
            self.session = core.create_http_session(self.page, domain)
            self.current_domain = domain

        return True

    def _refresh_session_cookies(self, url: str):
        domain = urlparse(url).netloc
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = core.create_http_session(self.page, domain)
        self.current_domain = domain

    def _cleanup_browser(self):
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None

        if self.page is not None:
            try:
                self.page.quit()
            except Exception:
                pass
            self.page = None

    def run(self):
        while not self._shutdown:
            try:
                cmd = self.cmd_queue.get(timeout=0.3)
            except queue.Empty:
                continue

            cmd_type = cmd.get("type")
            if cmd_type == "shutdown":
                break

            self.busy_changed.emit(True)
            try:
                if cmd_type == "scan":
                    self._handle_scan(cmd["url"])
                elif cmd_type == "download":
                    self._handle_download(
                        cmd["chapters"],
                        cmd["save_dir"],
                        cmd.get("separate_by_branch", False)
                    )
            except Exception as e:
                self.log_signal.emit(tr("log_unexpected_err", err=e), "error")
                self.task_finished.emit("error")
            finally:
                self.busy_changed.emit(False)

        self._cleanup_browser()

    def _handle_scan(self, url: str):
        if not self._ensure_browser_and_auth(url):
            self.task_finished.emit("stopped")
            return

        chapters = core.extract_chapters_from_main_page(
            self.page,
            url,
            on_log=self.log_signal.emit,
            stop_event=self.stop_event
        )
        self._refresh_session_cookies(url)

        if self.stop_event.is_set():
            self.task_finished.emit("stopped")
            return

        if chapters:
            branches = Counter(core.resolve_team_display_name(ch) for ch in chapters)
            if len(branches) > 1:
                summary = ", ".join(
                    tr("branch_item", team=name, count=cnt)
                    for name, cnt in branches.most_common()
                )
                self.log_signal.emit(
                    tr("log_found_branches", total=len(chapters), branches=len(branches), summary=summary),
                    "success"
                )
            else:
                self.log_signal.emit(
                    tr("log_found_chapters", total=len(chapters), first=chapters[0]['num'], last=chapters[-1]['num']),
                    "success"
                )
            self.chapters_loaded.emit(chapters)
        else:
            self.log_signal.emit(tr("log_no_chapters"), "error")

        self.task_finished.emit("scan")

    def _emit_log_summary(
        self,
        total_chapters: int,
        succeeded_count: int,
        failed_entries: list[dict],
        separate_by_branch: bool,
        stopped: bool
    ):
        self.log_signal.emit(tr("report_header"), "info")
        if stopped:
            self.log_signal.emit(
                tr("report_stats_stopped", succeeded=succeeded_count, total=total_chapters),
                "warn"
            )
        else:
            self.log_signal.emit(
                tr("report_stats_ok", succeeded=succeeded_count, total=total_chapters),
                "success" if not failed_entries else "warn"
            )

        if failed_entries:
            self.log_signal.emit(tr("report_failed_count", failed=len(failed_entries)), "error")
            for idx, entry in enumerate(failed_entries, 1):
                ch = entry["chapter"]
                team_display = core.resolve_team_display_name(ch)
                team_tag = f" [{team_display}]" if separate_by_branch and team_display else ""
                label = tr("chapter_label", num=ch['num'], vol=ch['vol'], team_tag=team_tag)
                reason = tr(entry["reason_key"], **entry["reason_kwargs"])
                self.log_signal.emit(f"  {idx}. {label} — {reason}", "error")

        self.log_signal.emit(tr("report_footer"), "info")

    def _handle_download(self, chapters: list[dict], save_dir: str, separate_by_branch: bool):
        if not chapters:
            self.task_finished.emit("download")
            return

        first_url = chapters[0]["url"]
        if not self._ensure_browser_and_auth(first_url):
            self.task_finished.emit("stopped")
            return

        total_chapters = len(chapters)
        succeeded_count = 0
        failed_entries: list[dict] = []

        self.log_signal.emit(tr("log_start_download", total=total_chapters), "info")

        for idx, ch in enumerate(chapters, 1):
            if self.stop_event.is_set():
                self.log_signal.emit(tr("log_download_stopped"), "warn")
                self._emit_log_summary(total_chapters, succeeded_count, failed_entries, separate_by_branch, stopped=True)
                self.download_report.emit({
                    "total": total_chapters,
                    "succeeded": succeeded_count,
                    "failed_entries": failed_entries,
                    "stopped": True,
                    "save_dir": save_dir,
                    "separate_by_branch": separate_by_branch
                })
                self.task_finished.emit("stopped")
                return

            team_display = core.resolve_team_display_name(ch)
            team_tag = f" [{team_display}]" if separate_by_branch and team_display else ""
            label = tr("chapter_label", num=ch['num'], vol=ch['vol'], team_tag=team_tag)

            self.chapter_progress.emit(idx - 1, total_chapters, f"[{idx}/{total_chapters}] {label}")
            self.page_progress.emit(0, 0)
            self.log_signal.emit(
                tr("log_processing_chapter", idx=idx, total=total_chapters, label=label),
                "info"
            )

            branch_folder = team_display if separate_by_branch else ""
            chapter_slug_override = ""
            if core.is_senkuro_site(ch["url"]) and ch.get("vol") not in ("", "?") and ch.get("num") not in ("", "?"):
                chapter_slug_override = f"v{ch['vol']}-c{ch['num']}"

            result = core.download_single_chapter(
                self.page,
                self.session,
                ch["url"],
                save_dir,
                branch_folder=branch_folder,
                chapter_slug_override=chapter_slug_override,
                on_total_pages=lambda tot: self.page_progress.emit(0, tot),
                on_page_done=lambda done, tot: self.page_progress.emit(done, tot),
                on_log=self.log_signal.emit,
                stop_event=self.stop_event
            )

            if result.get("status") == "stopped" or self.stop_event.is_set():
                self.log_signal.emit(tr("log_download_stopped"), "warn")
                self._emit_log_summary(total_chapters, succeeded_count, failed_entries, separate_by_branch, stopped=True)
                self.download_report.emit({
                    "total": total_chapters,
                    "succeeded": succeeded_count,
                    "failed_entries": failed_entries,
                    "stopped": True,
                    "save_dir": save_dir,
                    "separate_by_branch": separate_by_branch
                })
                self.task_finished.emit("stopped")
                return

            if result.get("ok"):
                succeeded_count += 1
            else:
                reason_key = result.get("reason_key", "fail_reason_unknown")
                reason_kwargs = result.get("reason_kwargs", {})
                reason_text = tr(reason_key, **reason_kwargs)
                self.log_signal.emit(
                    tr("log_chapter_failed_item", label=label, reason=reason_text),
                    "error"
                )
                failed_entries.append({
                    "chapter": ch,
                    "status": result.get("status", "failed"),
                    "reason_key": reason_key,
                    "reason_kwargs": reason_kwargs,
                    "saved": result.get("saved", 0),
                    "expected": result.get("expected", 0)
                })

            self.chapter_progress.emit(idx, total_chapters, f"[{idx}/{total_chapters}] {label}")

            if idx < total_chapters and not self.stop_event.is_set():
                time.sleep(random.uniform(0.6, 1.2))

        self._emit_log_summary(total_chapters, succeeded_count, failed_entries, separate_by_branch, stopped=False)
        if not failed_entries:
            self.log_signal.emit(tr("log_all_done"), "success")

        self.download_report.emit({
            "total": total_chapters,
            "succeeded": succeeded_count,
            "failed_entries": failed_entries,
            "stopped": False,
            "save_dir": save_dir,
            "separate_by_branch": separate_by_branch
        })
        self.task_finished.emit("download")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1000, 750)
        self.setMinimumSize(840, 610)

        self.chapters_data: list[dict] = []
        self.failed_entries: list[dict] = []
        self.last_download_save_dir: str = ""
        self.last_download_separate: bool = False
        self.has_multiple_branches: bool = False
        self.current_status_key: str = "status_idle"
        self.custom_status_active: bool = False
        self.page_scan_in_progress: bool = False
        self.default_save_dir = os.path.join(SCRIPT_DIR, "Downloads")

        self.worker = BrowserWorker(self)
        self._setup_ui()
        self._connect_signals()
        self.retranslate_ui()
        self.worker.start()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(12)

        # --- Шапка ---
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("TitleLabel")
        self.sub_lbl = QLabel()
        self.sub_lbl.setObjectName("SubtitleLabel")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.auth_btn = QPushButton()
        self.auth_btn.setObjectName("AuthBtn")
        self.auth_btn.setVisible(False)
        header_layout.addWidget(self.auth_btn)

        header_layout.addSpacing(8)
        self.lang_lbl = QLabel()
        self.lang_lbl.setObjectName("SubtitleLabel")
        self.lang_combo = QComboBox()
        for code, title in LANGUAGES.items():
            self.lang_combo.addItem(title, code)

        cur_lang = get_language()
        idx = self.lang_combo.findData(cur_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)

        header_layout.addWidget(self.lang_lbl)
        header_layout.addWidget(self.lang_combo)

        root_layout.addLayout(header_layout)

        # --- Картка налаштувань джерела та папки ---
        source_card = QFrame()
        source_card.setObjectName("Card")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(12, 12, 12, 12)
        source_layout.setSpacing(8)

        url_row = QHBoxLayout()
        self.url_lbl = QLabel()
        self.url_lbl.setFixedWidth(90)
        self.url_input = QLineEdit()
        self.scan_btn = QPushButton()
        self.scan_btn.setObjectName("PrimaryBtn")
        self.direct_dl_btn = QPushButton()
        self.direct_dl_btn.setObjectName("SuccessBtn")

        url_row.addWidget(self.url_lbl)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.scan_btn)
        url_row.addWidget(self.direct_dl_btn)
        source_layout.addLayout(url_row)

        dir_row = QHBoxLayout()
        self.dir_lbl = QLabel()
        self.dir_lbl.setFixedWidth(90)
        self.dir_input = QLineEdit(self.default_save_dir)
        self.browse_btn = QPushButton()
        self.open_dir_btn = QPushButton()

        dir_row.addWidget(self.dir_lbl)
        dir_row.addWidget(self.dir_input, 1)
        dir_row.addWidget(self.browse_btn)
        dir_row.addWidget(self.open_dir_btn)
        source_layout.addLayout(dir_row)

        root_layout.addWidget(source_card)

        # --- Сплітер: Список глав + Журнал подій ---
        splitter = QSplitter(Qt.Vertical)

        # Панель списку глав
        chapters_card = QFrame()
        chapters_card.setObjectName("Card")
        chapters_layout = QVBoxLayout(chapters_card)
        chapters_layout.setContentsMargins(12, 10, 12, 10)
        chapters_layout.setSpacing(8)

        branch_row = QHBoxLayout()
        self.sec_lbl = QLabel()
        self.sec_lbl.setObjectName("SectionHeader")
        self.selected_count_lbl = QLabel()
        self.selected_count_lbl.setObjectName("SubtitleLabel")

        self.branch_lbl = QLabel()
        self.branch_lbl.setObjectName("SubtitleLabel")
        self.branch_combo = QComboBox()
        self.branch_combo.setMinimumWidth(240)

        branch_row.addWidget(self.sec_lbl)
        branch_row.addSpacing(8)
        branch_row.addWidget(self.selected_count_lbl)
        branch_row.addStretch()
        branch_row.addWidget(self.branch_lbl)
        branch_row.addWidget(self.branch_combo)
        chapters_layout.addLayout(branch_row)

        toolbar_row = QHBoxLayout()
        self.range_input = QLineEdit()
        self.range_input.setFixedWidth(220)
        self.apply_range_btn = QPushButton()
        self.select_all_btn = QPushButton()
        self.deselect_all_btn = QPushButton()

        toolbar_row.addWidget(self.range_input)
        toolbar_row.addWidget(self.apply_range_btn)
        toolbar_row.addStretch()
        toolbar_row.addWidget(self.select_all_btn)
        toolbar_row.addWidget(self.deselect_all_btn)
        chapters_layout.addLayout(toolbar_row)

        self.chapters_list_widget = QListWidget()
        chapters_layout.addWidget(self.chapters_list_widget, 1)

        action_row = QHBoxLayout()
        self.branch_hint_lbl = QLabel("")
        self.branch_hint_lbl.setObjectName("SubtitleLabel")

        self.retry_failed_btn = QPushButton()
        self.retry_failed_btn.setObjectName("WarnBtn")
        self.retry_failed_btn.setVisible(False)

        self.download_selected_btn = QPushButton()
        self.download_selected_btn.setObjectName("SuccessBtn")
        self.download_selected_btn.setEnabled(False)

        self.stop_btn = QPushButton()
        self.stop_btn.setObjectName("DangerBtn")
        self.stop_btn.setEnabled(False)

        action_row.addWidget(self.branch_hint_lbl)
        action_row.addStretch()
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(self.retry_failed_btn)
        action_row.addWidget(self.download_selected_btn)
        chapters_layout.addLayout(action_row)

        splitter.addWidget(chapters_card)

        # Панель прогресу та логу
        bottom_card = QFrame()
        bottom_card.setObjectName("Card")
        bottom_layout = QVBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(12, 10, 12, 10)
        bottom_layout.setSpacing(6)

        ch_prog_row = QHBoxLayout()
        self.ch_status_lbl = QLabel()
        self.ch_status_lbl.setObjectName("SectionHeader")
        ch_prog_row.addWidget(self.ch_status_lbl)
        bottom_layout.addLayout(ch_prog_row)

        self.chapters_progress_bar = QProgressBar()
        self.chapters_progress_bar.setRange(0, 100)
        self.chapters_progress_bar.setValue(0)
        bottom_layout.addWidget(self.chapters_progress_bar)

        self.pages_progress_bar = QProgressBar()
        self.pages_progress_bar.setObjectName("PageBar")
        self.pages_progress_bar.setRange(0, 100)
        self.pages_progress_bar.setValue(0)
        bottom_layout.addWidget(self.pages_progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        bottom_layout.addWidget(self.log_view, 1)

        splitter.addWidget(bottom_card)
        splitter.setSizes([410, 230])
        root_layout.addWidget(splitter, 1)

    def _connect_signals(self):
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)

        self.browse_btn.clicked.connect(self.choose_directory)
        self.open_dir_btn.clicked.connect(self.open_download_directory)
        self.scan_btn.clicked.connect(self.on_scan_clicked)
        self.direct_dl_btn.clicked.connect(self.on_direct_download_clicked)
        self.download_selected_btn.clicked.connect(self.on_download_selected_clicked)
        self.retry_failed_btn.clicked.connect(self.on_retry_failed_clicked)
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        self.auth_btn.clicked.connect(self.on_confirm_auth_clicked)

        self.branch_combo.currentIndexChanged.connect(self._on_branch_filter_changed)
        self.select_all_btn.clicked.connect(lambda: self._set_visible_checked(True))
        self.deselect_all_btn.clicked.connect(lambda: self._set_visible_checked(False))
        self.apply_range_btn.clicked.connect(self.apply_range_selection)
        self.range_input.returnPressed.connect(self.apply_range_selection)
        self.chapters_list_widget.itemChanged.connect(self._update_selected_counter)

        self.worker.log_signal.connect(self.append_log)
        self.worker.chapters_loaded.connect(self.populate_chapters)
        self.worker.chapter_progress.connect(self.update_chapter_progress)
        self.worker.page_progress.connect(self.update_page_progress)
        self.worker.auth_required.connect(self.on_auth_required)
        self.worker.download_report.connect(self.on_download_report)
        self.worker.task_finished.connect(self.on_task_finished)
        self.worker.busy_changed.connect(self.set_busy_state)

    def _has_branch_selector(self) -> bool:
        """Повертає True лише для сайтів, де є інформація про гілки/команди перекладу."""
        if not self.chapters_data:
            return False
        return any(not ch.get("is_default_team", False) for ch in self.chapters_data)

    def _format_chapter_list_item(self, ch: dict, show_team: bool) -> str:
        if show_team:
            team_name = core.resolve_team_display_name(ch)
            return tr("chapter_item", vol=ch['vol'], num=ch['num'], team=team_name)
        base = tr("chapter_item", vol=ch['vol'], num=ch['num'], team="")
        return base.replace("   []", "").replace("[]", "").strip()

    def _on_language_changed(self):
        lang_code = self.lang_combo.currentData()
        if not lang_code:
            return
        set_language(lang_code, persist=True)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(tr("app_title"))
        self.title_lbl.setText(tr("app_title"))
        self.sub_lbl.setText(tr("subtitle"))
        self.lang_lbl.setText(tr("lang_label"))
        self.auth_btn.setText(tr("btn_confirm_auth"))

        self.url_lbl.setText(tr("lbl_url"))
        self.url_input.setPlaceholderText(tr("ph_url"))
        self.scan_btn.setText(tr("btn_get_chapters"))
        self.direct_dl_btn.setText(tr("btn_dl_chapter"))
        self.direct_dl_btn.setToolTip(tr("tip_dl_chapter"))

        self.dir_lbl.setText(tr("lbl_save_to"))
        self.browse_btn.setText(tr("btn_browse"))
        self.open_dir_btn.setText(tr("btn_open_dir"))

        self.sec_lbl.setText(tr("sec_chapters"))
        self.branch_lbl.setText(tr("lbl_branch"))
        self.range_input.setPlaceholderText(tr("ph_range"))
        self.apply_range_btn.setText(tr("btn_apply_range"))
        self.select_all_btn.setText(tr("btn_select_all"))
        self.deselect_all_btn.setText(tr("btn_deselect_all"))

        self.download_selected_btn.setText(tr("btn_dl_selected"))
        self.retry_failed_btn.setText(tr("btn_retry_failed", count=len(self.failed_entries)))
        self.stop_btn.setText(tr("btn_stop"))

        self.chapters_progress_bar.setFormat(tr("prog_chapters"))
        if self.page_scan_in_progress:
            self.pages_progress_bar.setFormat(tr("prog_scanning_pages"))
        else:
            self.pages_progress_bar.setFormat(tr("prog_pages"))

        if not self.custom_status_active:
            self.ch_status_lbl.setText(tr(self.current_status_key))

        self._refresh_localized_lists()

    def _refresh_localized_lists(self):
        if not self.chapters_data:
            self.branch_combo.blockSignals(True)
            self.branch_combo.clear()
            self.branch_combo.addItem(tr("all_translators", count=0), None)
            self.branch_combo.blockSignals(False)
            self.branch_lbl.setVisible(True)
            self.branch_combo.setVisible(True)
            self.branch_hint_lbl.setText("")
            self._update_selected_counter()
            return

        show_branches = self._has_branch_selector()
        self.branch_lbl.setVisible(show_branches)
        self.branch_combo.setVisible(show_branches)

        current_branch_key = self.branch_combo.currentData()

        branch_counts: Counter = Counter()
        branch_labels: dict[str, str] = {}
        for ch in self.chapters_data:
            b_key = ch.get("branch_key", "")
            branch_counts[b_key] += 1
            if b_key not in branch_labels:
                branch_labels[b_key] = core.resolve_team_display_name(ch)

        sorted_branches = branch_counts.most_common()
        self.has_multiple_branches = show_branches and len(sorted_branches) > 1

        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        self.branch_combo.addItem(tr("all_translators", count=len(self.chapters_data)), None)
        for b_key, cnt in sorted_branches:
            self.branch_combo.addItem(
                tr("branch_item", team=branch_labels[b_key], count=cnt),
                b_key
            )

        if show_branches:
            restored_idx = self.branch_combo.findData(current_branch_key)
            self.branch_combo.setCurrentIndex(restored_idx if restored_idx >= 0 else 0)
        else:
            self.branch_combo.setCurrentIndex(0)
        self.branch_combo.blockSignals(False)

        if self.has_multiple_branches:
            self.branch_hint_lbl.setText(tr("hint_multi_branch", count=len(sorted_branches)))
        else:
            self.branch_hint_lbl.setText("")

        failed_by_url = {e["chapter"]["url"]: e for e in self.failed_entries}

        self.chapters_list_widget.blockSignals(True)
        for i in range(self.chapters_list_widget.count()):
            item = self.chapters_list_widget.item(i)
            ch = item.data(Qt.UserRole)
            base_text = self._format_chapter_list_item(ch, show_team=show_branches)
            fail_entry = failed_by_url.get(ch["url"])
            if fail_entry:
                reason = tr(fail_entry["reason_key"], **fail_entry["reason_kwargs"])
                item.setText(f"{base_text}  ⚠")
                item.setForeground(QBrush(QColor("#fca5a5")))
                item.setToolTip(tr("tip_failed_chapter", reason=reason))
            else:
                item.setText(base_text)
                item.setForeground(QBrush(QColor("#e4e6eb")))
                item.setToolTip("")
        self.chapters_list_widget.blockSignals(False)

        self._update_selected_counter()

    def _clear_failed_state(self):
        self.failed_entries = []
        self.retry_failed_btn.setVisible(False)
        self._refresh_localized_lists()

    def _set_status_key(self, key: str):
        self.current_status_key = key
        self.custom_status_active = False
        self.ch_status_lbl.setText(tr(key))

    def append_log(self, text: str, level: str = "info"):
        colors = {
            "info": "#93c5fd",
            "success": "#34d399",
            "warn": "#fbbf24",
            "error": "#f87171"
        }
        color = colors.get(level, "#e4e6eb")
        self.log_view.setTextColor(QColor(color))
        self.log_view.append(text)
        self.log_view.moveCursor(QTextCursor.End)

    def choose_directory(self):
        folder = QFileDialog.getExistingDirectory(self, tr("dlg_choose_dir"), self.dir_input.text())
        if folder:
            self.dir_input.setText(folder)

    def open_download_directory(self):
        path = self.dir_input.text().strip() or self.default_save_dir
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _validate_url(self) -> str | None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, tr("dlg_empty_title"), tr("dlg_empty_msg"))
            return None
        if not core.is_supported_url(url):
            QMessageBox.critical(
                self,
                tr("dlg_unsupported_title"),
                tr("dlg_unsupported_msg")
            )
            return None
        return url

    def on_scan_clicked(self):
        url = self._validate_url()
        if not url:
            return
        if core.is_chapter_url(url):
            self.append_log(tr("log_direct_chapter"), "info")
            self.on_direct_download_clicked()
            return

        self.chapters_list_widget.clear()
        self.chapters_data = []
        self.failed_entries = []
        self.retry_failed_btn.setVisible(False)
        self.has_multiple_branches = False
        self._refresh_localized_lists()

        self._set_status_key("status_scanning")
        self.worker.enqueue_scan(url)

    def on_direct_download_clicked(self):
        url = self._validate_url()
        if not url:
            return
        if not core.is_chapter_url(url):
            QMessageBox.information(
                self,
                tr("dlg_title_link_title"),
                tr("dlg_title_link_msg")
            )
            return

        self._clear_failed_state()
        save_dir = self.dir_input.text().strip() or self.default_save_dir
        _, ch_slug = core.parse_slugs(url)
        if core.is_madara_site(url):
            ch_num = ch_slug.split("-c")[-1] if "-c" in ch_slug else ch_slug
            single_chapter = [core._make_chapter_entry("1", ch_num, url)]
        else:
            single_chapter = [core._make_chapter_entry("?", ch_slug, url)]
        self.worker.enqueue_download(single_chapter, save_dir, separate_by_branch=False)

    def populate_chapters(self, chapters: list[dict]):
        self.chapters_data = chapters
        self.failed_entries = []
        self.retry_failed_btn.setVisible(False)

        show_branches = self._has_branch_selector()
        self.branch_lbl.setVisible(show_branches)
        self.branch_combo.setVisible(show_branches)

        branch_counts: Counter = Counter()
        branch_labels: dict[str, str] = {}
        for ch in chapters:
            b_key = ch.get("branch_key", "")
            branch_counts[b_key] += 1
            if b_key not in branch_labels:
                branch_labels[b_key] = core.resolve_team_display_name(ch)

        sorted_branches = branch_counts.most_common()
        self.has_multiple_branches = show_branches and len(sorted_branches) > 1

        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        self.branch_combo.addItem(tr("all_translators", count=len(chapters)), None)
        for b_key, cnt in sorted_branches:
            self.branch_combo.addItem(
                tr("branch_item", team=branch_labels[b_key], count=cnt),
                b_key
            )

        primary_branch_key = sorted_branches[0][0] if self.has_multiple_branches else None
        if self.has_multiple_branches:
            self.branch_combo.setCurrentIndex(1)
            self.branch_hint_lbl.setText(tr("hint_multi_branch", count=len(sorted_branches)))
        else:
            self.branch_combo.setCurrentIndex(0)
            self.branch_hint_lbl.setText("")
        self.branch_combo.blockSignals(False)

        self.chapters_list_widget.blockSignals(True)
        self.chapters_list_widget.clear()

        for ch in chapters:
            item = QListWidgetItem(self._format_chapter_list_item(ch, show_team=show_branches))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

            if self.has_multiple_branches:
                is_primary = ch.get("branch_key") == primary_branch_key
                item.setCheckState(Qt.Checked if is_primary else Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)

            item.setData(Qt.UserRole, ch)
            self.chapters_list_widget.addItem(item)

        self.chapters_list_widget.blockSignals(False)
        self._on_branch_filter_changed()

    def _on_branch_filter_changed(self):
        selected_branch = self.branch_combo.currentData() if self._has_branch_selector() else None
        for i in range(self.chapters_list_widget.count()):
            item = self.chapters_list_widget.item(i)
            ch = item.data(Qt.UserRole)
            if selected_branch is None:
                item.setHidden(False)
            else:
                item.setHidden(ch.get("branch_key") != selected_branch)
        self._update_selected_counter()

    def _set_visible_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        self.chapters_list_widget.blockSignals(True)
        for i in range(self.chapters_list_widget.count()):
            item = self.chapters_list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self.chapters_list_widget.blockSignals(False)
        self._update_selected_counter()

    def apply_range_selection(self):
        expr = self.range_input.text().strip()
        if not expr or not self.chapters_data:
            return

        selected_branch = self.branch_combo.currentData() if self._has_branch_selector() else None
        if self.has_multiple_branches and selected_branch is None:
            QMessageBox.information(
                self,
                tr("dlg_select_branch_title"),
                tr("dlg_select_branch_msg")
            )
            return

        matched = core.filter_chapters_by_range(
            self.chapters_data,
            expr,
            branch_key=selected_branch
        )
        if not matched:
            QMessageBox.information(
                self,
                tr("dlg_range_title"),
                tr("dlg_range_not_found", expr=expr)
            )
            return

        matched_urls = {c["url"] for c in matched}
        self.chapters_list_widget.blockSignals(True)
        for i in range(self.chapters_list_widget.count()):
            item = self.chapters_list_widget.item(i)
            if item.isHidden():
                continue
            ch = item.data(Qt.UserRole)
            item.setCheckState(Qt.Checked if ch["url"] in matched_urls else Qt.Unchecked)
        self.chapters_list_widget.blockSignals(False)
        self._update_selected_counter()

    def _update_selected_counter(self):
        total_all = self.chapters_list_widget.count()
        checked_all = 0
        visible_total = 0
        visible_checked = 0

        for i in range(total_all):
            item = self.chapters_list_widget.item(i)
            is_chk = item.checkState() == Qt.Checked
            if is_chk:
                checked_all += 1
            if not item.isHidden():
                visible_total += 1
                if is_chk:
                    visible_checked += 1

        if visible_total != total_all:
            self.selected_count_lbl.setText(
                tr(
                    "counter_filtered",
                    vis_chk=visible_checked,
                    vis_tot=visible_total,
                    all_chk=checked_all
                )
            )
        else:
            self.selected_count_lbl.setText(
                tr("counter_simple", all_chk=checked_all, all_tot=total_all)
            )

        self.download_selected_btn.setEnabled(checked_all > 0 and self.scan_btn.isEnabled())

    def on_download_selected_clicked(self):
        selected = []
        for i in range(self.chapters_list_widget.count()):
            item = self.chapters_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))

        if not selected:
            return

        self._clear_failed_state()
        save_dir = self.dir_input.text().strip() or self.default_save_dir
        self.worker.enqueue_download(
            selected,
            save_dir,
            separate_by_branch=self.has_multiple_branches
        )

    def on_retry_failed_clicked(self):
        if not self.failed_entries:
            return

        chapters_to_retry = [entry["chapter"] for entry in self.failed_entries]
        save_dir = self.last_download_save_dir or self.dir_input.text().strip() or self.default_save_dir
        separate_by_branch = self.last_download_separate

        self.append_log(tr("log_retrying_failed", count=len(chapters_to_retry)), "warn")
        self.retry_failed_btn.setVisible(False)
        self.worker.enqueue_download(
            chapters_to_retry,
            save_dir,
            separate_by_branch=separate_by_branch
        )

    def on_download_report(self, report: dict):
        failed_entries = report.get("failed_entries", [])
        total = report.get("total", 0)
        succeeded = report.get("succeeded", 0)
        stopped = report.get("stopped", False)

        self.failed_entries = failed_entries
        self.last_download_save_dir = report.get("save_dir", "")
        self.last_download_separate = report.get("separate_by_branch", False)

        self._refresh_localized_lists()

        if not failed_entries:
            self.retry_failed_btn.setVisible(False)
            return

        self.retry_failed_btn.setText(tr("btn_retry_failed", count=len(failed_entries)))
        self.retry_failed_btn.setVisible(True)

        failed_urls = {e["chapter"]["url"] for e in failed_entries}
        if self.chapters_list_widget.count() > 0:
            self.chapters_list_widget.blockSignals(True)
            for i in range(self.chapters_list_widget.count()):
                item = self.chapters_list_widget.item(i)
                ch = item.data(Qt.UserRole)
                item.setCheckState(Qt.Checked if ch["url"] in failed_urls else Qt.Unchecked)
            self.chapters_list_widget.blockSignals(False)
            self._update_selected_counter()

        if stopped:
            header_line = tr("report_stats_stopped", succeeded=succeeded, total=total)
        else:
            header_line = tr("report_stats_ok", succeeded=succeeded, total=total)

        lines = [
            header_line,
            "",
            tr("report_failed_count", failed=len(failed_entries))
        ]

        max_preview = 15
        for idx, entry in enumerate(failed_entries[:max_preview], 1):
            ch = entry["chapter"]
            team_display = core.resolve_team_display_name(ch)
            team_tag = f" [{team_display}]" if self.last_download_separate and team_display else ""
            label = tr("chapter_label", num=ch['num'], vol=ch['vol'], team_tag=team_tag)
            reason = tr(entry["reason_key"], **entry["reason_kwargs"])
            lines.append(f"{idx}. {label} — {reason}")

        if len(failed_entries) > max_preview:
            lines.append(tr("report_more_items", count=len(failed_entries) - max_preview))

        lines.append("")
        lines.append(tr("dlg_report_retry_prompt"))

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(tr("dlg_report_title"))
        msg_box.setText("\n".join(lines))

        retry_btn = msg_box.addButton(tr("btn_retry_now"), QMessageBox.AcceptRole)
        msg_box.addButton(tr("btn_close"), QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == retry_btn:
            self.on_retry_failed_clicked()

    def on_stop_clicked(self):
        self.append_log(tr("log_sending_stop"), "warn")
        self.stop_btn.setEnabled(False)
        self.worker.request_stop()

    def on_auth_required(self):
        self.auth_btn.setVisible(True)
        QMessageBox.information(
            self,
            tr("dlg_auth_title"),
            tr("dlg_auth_msg")
        )
        if self.auth_btn.isVisible():
            self.on_confirm_auth_clicked()

    def on_confirm_auth_clicked(self):
        self.auth_btn.setVisible(False)
        self.worker.confirm_auth()

    def update_chapter_progress(self, current: int, total: int, label: str):
        self.custom_status_active = True
        self.ch_status_lbl.setText(label)
        self.chapters_progress_bar.setMaximum(max(total, 1))
        self.chapters_progress_bar.setValue(current)

    def update_page_progress(self, done: int, total: int):
        if total <= 0:
            self.page_scan_in_progress = True
            self.pages_progress_bar.setRange(0, 0)
            self.pages_progress_bar.setFormat(tr("prog_scanning_pages"))
        else:
            self.page_scan_in_progress = False
            self.pages_progress_bar.setRange(0, total)
            self.pages_progress_bar.setValue(min(done, total))
            self.pages_progress_bar.setFormat(tr("prog_pages"))

    def set_busy_state(self, busy: bool):
        self.scan_btn.setEnabled(not busy)
        self.direct_dl_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if busy:
            self.download_selected_btn.setEnabled(False)
            self.retry_failed_btn.setEnabled(False)
        else:
            self.retry_failed_btn.setEnabled(bool(self.failed_entries))
            self._update_selected_counter()

    def on_task_finished(self, kind: str):
        self.auth_btn.setVisible(False)
        if kind == "download":
            self._set_status_key("status_done")
        elif kind == "scan":
            self._set_status_key("status_ready")
        elif kind == "stopped":
            self._set_status_key("status_stopped")
        elif kind == "error":
            self._set_status_key("status_error")

    def closeEvent(self, event):
        self.worker.shutdown()
        self.worker.wait(5000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
