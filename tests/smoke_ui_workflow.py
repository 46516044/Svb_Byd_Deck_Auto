import base64
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import QThread, Qt
from PyQt5.QtWidgets import QApplication

from src.app.bootstrap import _command_listener
from src.ui.card_catalog import (
    CardEntry,
    get_card_resource_root,
    load_card_catalog,
    resolve_card_entry,
)
from src.ui.main_window import ShadowverseUI
from src.ui.disclaimer import DisclaimerDialog, request_startup_disclaimer
import src.ui.disclaimer as disclaimer_module
from src.ui.deck_io import MAX_DECK_SIZE
from src.ui.pages.deck_workspace_page import DeckWorkspacePage
import src.ui.pages.deck_workspace_page as workspace_module


class _FakeDeviceState:
    def __init__(self) -> None:
        self.stop_count = 0

    def request_pause(self, reason: str = "") -> None:
        del reason

    def request_resume(self, reason: str = "") -> None:
        del reason

    def request_stop(self, reason: str = "") -> None:
        del reason
        self.stop_count += 1


class _FakeDeviceManager:
    def __init__(self) -> None:
        self.state = _FakeDeviceState()
        self.device_states = {"test": self.state}


class _ShortWorker(QThread):
    def run(self) -> None:
        time.sleep(0.15)


def _process_events(app: QApplication, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.03)


def test_command_listener_lifecycle() -> None:
    commands: "queue.Queue[str]" = queue.Queue()

    old_manager = _FakeDeviceManager()
    old_stop = threading.Event()
    old_thread = threading.Thread(
        target=_command_listener,
        args=(commands, old_manager, logging.getLogger("old-run"), old_stop),
    )
    old_thread.start()
    old_stop.set()
    old_thread.join(2)
    assert not old_thread.is_alive()

    new_manager = _FakeDeviceManager()
    new_stop = threading.Event()
    new_thread = threading.Thread(
        target=_command_listener,
        args=(commands, new_manager, logging.getLogger("new-run"), new_stop),
    )
    new_thread.start()
    commands.put("e")
    new_thread.join(2)

    assert not new_thread.is_alive()
    assert old_manager.state.stop_count == 0
    assert new_manager.state.stop_count == 1


def test_disclaimer_remember_choice() -> None:
    original_check = disclaimer_module.check_consent_file
    original_request = disclaimer_module.request_disclaimer_consent
    original_accept = disclaimer_module.accept_consent_for_session
    original_remove = disclaimer_module.remove_consent
    original_save = disclaimer_module.save_consent
    calls = []
    try:
        disclaimer_module.check_consent_file = lambda: False
        disclaimer_module.request_disclaimer_consent = lambda _parent: (True, False)
        disclaimer_module.accept_consent_for_session = lambda: calls.append("session")
        disclaimer_module.remove_consent = lambda: calls.append("remove") or True
        disclaimer_module.save_consent = lambda **_kwargs: calls.append("save") or True
        assert request_startup_disclaimer(object()) is True
        assert calls == ["remove", "session"]

        calls.clear()
        disclaimer_module.request_disclaimer_consent = lambda _parent: (True, True)
        assert request_startup_disclaimer(object()) is True
        assert calls == ["save"]
    finally:
        disclaimer_module.check_consent_file = original_check
        disclaimer_module.request_disclaimer_consent = original_request
        disclaimer_module.accept_consent_for_session = original_accept
        disclaimer_module.remove_consent = original_remove
        disclaimer_module.save_consent = original_save


def test_deck_apply_is_transactional() -> None:
    page = DeckWorkspacePage.__new__(DeckWorkspacePage)
    page.resource_root = get_card_resource_root()
    catalog = load_card_catalog(page.resource_root)
    entry = resolve_card_entry("1_10201110_1_1.webp", catalog, page.resource_root)
    assert entry is not None

    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "card_cost"
        target.mkdir()
        (target / "old-template.webp").write_bytes(b"old")
        original_get_card_cost_dir = workspace_module.get_card_cost_dir
        original_get_config_path = workspace_module.get_config_path
        try:
            workspace_module.get_card_cost_dir = lambda ensure=False: str(target)
            copied, missing = page._apply_entries([entry], {})
            assert copied >= 2
            assert not missing
            assert not (target / "old-template.webp").exists()
            assert (target / "1_10201110_1_1.webp").exists()
            assert (target / "1_10201110_evo.webp").exists()

            copied, missing = page._apply_entries([entry, entry], {})
            assert copied == 2
            assert not missing

            fake_entry = CardEntry(
                key="fake/99999999",
                card_id="99999999",
                cost=1,
                enhance_costs=(),
                name="missing-card",
                category="中立",
                source_path=str(Path(temp_dir) / "1_99999999.webp"),
                relative_path="中立/1_99999999.webp",
            )
            before = {path.name: path.read_bytes() for path in target.iterdir()}
            try:
                page._apply_entries([fake_entry], {})
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("missing templates must reject the apply")
            after = {path.name: path.read_bytes() for path in target.iterdir()}
            assert after == before

            corrupt_config = Path(temp_dir) / "config.json"
            corrupt_config.write_text("{broken", encoding="utf-8")
            workspace_module.get_config_path = lambda: str(corrupt_config)
            before = {path.name: path.read_bytes() for path in target.iterdir()}
            try:
                page._apply_entries(
                    [entry],
                    {"high_priority_cards": {"test": {"priority": 1}}},
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("corrupt config must reject the apply")
            after = {path.name: path.read_bytes() for path in target.iterdir()}
            assert after == before
            assert corrupt_config.read_text(encoding="utf-8") == "{broken"
        finally:
            workspace_module.get_card_cost_dir = original_get_card_cost_dir
            workspace_module.get_config_path = original_get_config_path


def test_main_window_workflow() -> None:
    app = QApplication.instance() or QApplication([])
    disclaimer = DisclaimerDialog(require_acceptance=True)
    assert disclaimer.acceptance_checkbox is not None
    assert disclaimer.remember_checkbox is not None
    assert disclaimer.remember_checkbox.text() == "同意一次后不再显示此弹窗"
    assert disclaimer.remember_checkbox.isChecked()
    assert not disclaimer.accept_button.isEnabled()
    disclaimer.acceptance_checkbox.setChecked(True)
    _process_events(app, 1)
    assert disclaimer.accept_button.isEnabled()
    disclaimer.close()

    window = ShadowverseUI(lambda **kwargs: None, queue.Queue(), queue.Queue())

    window.resize(1280, 720)
    window.show()
    _process_events(app)

    dashboard = window.dashboard_page
    workspace = window.deck_workspace_page
    assert window.about_button.text() == "关于与免责声明"
    assert dashboard.disclaimer_button.text() == "查看详情"
    assert workspace.workspace_is_applied() is True

    window.state.set_device(connected=False)
    window.state.set_run_status("disconnected")
    dashboard.adb_input.clear()
    assert not dashboard.connect_button.isEnabled()
    assert not dashboard.start_button.isEnabled()
    dashboard.adb_input.setText("device-a")
    dashboard.server_combo.setCurrentText("国际服")
    assert dashboard.connect_button.isEnabled()
    assert dashboard.start_button.isEnabled()

    connect_requests = []
    original_connect_device = window.connect_device
    window.connect_device = lambda *, start_after_connect=False: connect_requests.append(
        bool(start_after_connect)
    )
    try:
        window.start_script()
    finally:
        window.connect_device = original_connect_device
    assert connect_requests == [True]

    window.state.set_run_status("connecting")
    assert not dashboard.adb_input.isEnabled()
    assert not dashboard.start_button.isEnabled()
    window._device_config = {"serial": "device-a", "is_global": False}
    start_requests = []
    original_start_script = window.start_script
    window.start_script = lambda: start_requests.append(True)
    window._start_after_connect = True
    window._on_device_connection_checked(False, "failed", {})
    assert not start_requests
    assert window._start_after_connect is False

    window._start_after_connect = True
    window._on_device_connection_checked(True, "connected", {})
    assert start_requests == [True]
    assert window._start_after_connect is False
    window._start_after_connect = False
    window._on_device_connection_checked(True, "connected", {})
    assert start_requests == [True]
    window.start_script = original_start_script
    assert window.state.device["serial"] == "device-a"
    assert dashboard.adb_input.isEnabled()

    dashboard.cost_curve.set_costs(
        {0: 1, 1: 3, 8: 2, 9: 4, 10: 5, -1: 9, "invalid": 2}
    )
    assert dashboard.cost_curve._costs == {0: 1, 1: 3, 8: 11}
    assert sum(dashboard.cost_curve._costs.values()) == 15
    curve_image = dashboard.cost_curve.grab().toImage()
    assert not curve_image.isNull()
    green_pixels = 0
    for y in range(max(0, curve_image.height() - 36), curve_image.height()):
        for x in range(curve_image.width()):
            color = curve_image.pixelColor(x, y)
            if color.green() > color.red() + 12 and color.green() > color.blue() + 12:
                green_pixels += 1
    assert green_pixels > 40

    for key in ("dashboard", "deck", "cards", "stats", "settings", "logs"):
        window.navigate(key)
        _process_events(app, 2)
        assert window.stacked_widget.currentWidget() is window.pages[key]

    assert all(button.icon().isNull() for button in window.nav_buttons.values())
    settings = window.config_page
    assert settings.restart_note.y() > settings.restart_enabled_checkbox.y()
    background_path = Path(__file__).resolve().parents[1] / "Image" / "ui背景.jpg"
    assert settings._set_background_path(str(background_path))
    settings.background_opacity_slider.setValue(30)
    background_config = settings._background_config()
    assert background_config["path"] == "Image/ui背景.jpg"
    assert window._apply_custom_background({"ui": {"custom_background": background_config}})
    assert window.app_root.has_background()
    assert window.app_root.background_opacity == 30

    assert len(workspace.catalog) == 970
    assert workspace.library_list.count() == 970

    scroll = workspace.library_list.verticalScrollBar()
    scroll.setValue(scroll.maximum())
    workspace.library_list.resize(
        workspace.library_list.width() + 120,
        workspace.library_list.height(),
    )
    _process_events(app)
    visible_items = [
        workspace.library_list.item(index)
        for index in range(workspace.library_list.count())
        if not workspace.library_list.item(index).isHidden()
        and workspace.library_list.visualItemRect(
            workspace.library_list.item(index)
        ).intersects(workspace.library_list.viewport().rect())
    ]
    assert visible_items
    assert all(not item.icon().isNull() for item in visible_items)
    scroll.setValue(0)
    _process_events(app, 2)

    restored_total = workspace._selected_total_count()
    if restored_total > MAX_DECK_SIZE - 2:
        to_remove = restored_total - (MAX_DECK_SIZE - 2)
        for key in list(workspace.selected_entries):
            count = workspace.selected_counts.get(key, 1)
            removed = min(count, to_remove)
            remaining = count - removed
            if remaining > 0:
                workspace.selected_counts[key] = remaining
            else:
                workspace.selected_counts.pop(key, None)
                workspace.selected_entries.pop(key, None)
            to_remove -= removed
            if to_remove <= 0:
                break
        workspace._workspace_is_applied = False
        workspace._refresh_current_list()
    initial_count = len(workspace.selected_entries)
    initial_total = workspace._selected_total_count()
    initial_derived_keys = set(workspace.derived_entries)
    first = next(
        entry
        for entry in workspace.catalog
        if entry.key not in workspace.selected_entries
    )
    workspace._set_category_filter(first.category)
    workspace._set_cost_filter(str(first.cost) if first.cost < 10 else "10+")
    workspace._set_search_filter(first.card_id)
    visible = sum(
        not workspace.library_list.item(index).isHidden()
        for index in range(workspace.library_list.count())
    )
    assert visible >= 1

    workspace.add_card_by_key(first.key)
    workspace.add_card_by_key(first.key)
    assert len(workspace.selected_entries) == initial_count + 1
    assert workspace.selected_counts[first.key] == 2
    assert workspace._selected_total_count() == initial_total + 2
    for index in range(workspace.current_list.count()):
        item = workspace.current_list.item(index)
        if item.data(Qt.UserRole) == first.key:
            workspace.current_list.setCurrentItem(item)
            break
    workspace.remove_selected_current_card()
    assert workspace.selected_counts[first.key] == 1
    workspace.increase_selected_current_card()
    assert workspace.selected_counts[first.key] == 2
    derived = next(
        entry
        for entry in workspace.catalog
        if entry.key not in workspace.derived_entries and entry.key != first.key
    )
    workspace.deck_list_tabs.setCurrentIndex(1)
    workspace.add_card_by_key(derived.key)
    workspace.add_card_by_key(derived.key)
    assert set(workspace.derived_entries) == initial_derived_keys | {derived.key}
    assert workspace._selected_total_count() == initial_total + 2
    workspace.deck_list_tabs.setCurrentIndex(0)
    assert workspace.workspace_is_applied() is False
    assert window.dashboard_page.deck_state_label.text() == "待应用"
    workspace.generate_share_code()
    share_code = workspace.share_output.toPlainText().strip()
    assert share_code
    share_payload = json.loads(
        zlib.decompress(base64.b64decode(share_code.encode("ascii"))).decode("utf-8")
    )
    assert share_payload["version"] == 5
    shared = {record["card_id"]: record["count"] for record in share_payload["cards"]}
    assert shared[first.card_id] == 2
    shared_derived = {
        record["card_id"] for record in share_payload["derived_cards"]
    }
    assert derived.card_id in shared_derived
    assert len(shared_derived) == len(initial_derived_keys) + 1

    expected_cards = workspace._deck_card_records()
    expected_derived = workspace._derived_card_records()
    expected_name = workspace.deck_name_input.text()
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_dir = Path(temp_dir) / "card_cost"
        runtime_dir.mkdir()
        (runtime_dir / "main-template.webp").write_bytes(b"main")
        (runtime_dir / "derived-template.webp").write_bytes(b"derived")
        config_path = Path(temp_dir) / "config.json"
        original_get_card_cost_dir = workspace_module.get_card_cost_dir
        original_get_config_path = workspace_module.get_config_path
        original_get_app_root = workspace_module.get_app_root
        try:
            workspace_module.get_card_cost_dir = lambda ensure=False: str(runtime_dir)
            workspace_module.get_config_path = lambda: str(config_path)
            workspace_module.get_app_root = lambda: temp_dir
            assert workspace._persist_active_deck_snapshot()
            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            snapshot = persisted["ui"]["active_deck_snapshot"]
            assert snapshot["cards"] == expected_cards
            assert snapshot["derived_cards"] == expected_derived

            workspace._set_selected_entries([])
            workspace._set_derived_entries([])
            workspace.deck_name_input.setText("已丢失的界面状态")
            workspace.load_deck()
            assert workspace._deck_card_records() == expected_cards
            assert workspace._derived_card_records() == expected_derived
            assert workspace.deck_name_input.text() == expected_name
            assert workspace.workspace_is_applied() is True

            (runtime_dir / "unexpected.webp").write_bytes(b"changed")
            assert workspace._restore_active_deck_snapshot(str(runtime_dir)) is False

            for path in runtime_dir.iterdir():
                path.unlink()
            runtime_names = workspace._runtime_names_for_entries(
                {
                    entry.key: entry
                    for entry in (
                        *workspace.selected_entries.values(),
                        *workspace.derived_entries.values(),
                    )
                }.values()
            )
            for filename in runtime_names:
                (runtime_dir / filename).write_bytes(b"template")
            decks_dir = Path(temp_dir) / "saved_decks"
            decks_dir.mkdir()
            matched_payload = {
                "version": 5,
                "name": "自动匹配卡组",
                "cards": expected_cards,
                "derived_cards": expected_derived,
            }
            (decks_dir / "matched.json").write_text(
                json.dumps(matched_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            config_path.write_text('{"ui": {}}', encoding="utf-8")
            workspace._set_selected_entries([])
            workspace._set_derived_entries([])
            workspace.load_deck()
            assert workspace._deck_card_records() == expected_cards
            assert workspace._derived_card_records() == expected_derived
            assert workspace.deck_name_input.text() == "自动匹配卡组"
            migrated_config = json.loads(config_path.read_text(encoding="utf-8"))
            assert migrated_config["ui"]["active_deck_snapshot"]["deck_file"] == "matched.json"
        finally:
            workspace_module.get_card_cost_dir = original_get_card_cost_dir
            workspace_module.get_config_path = original_get_config_path
            workspace_module.get_app_root = original_get_app_root

    window.append_log("[ERROR] workflow smoke")
    window.append_log("[对战开始] 第3场对战")
    _process_events(app)
    assert window.state.battle_count == 3
    window.logs_page.set_level_filter("error")
    assert window.logs_page._visible_count == 1

    new_value = not window.dashboard_page.auto_restart_checkbox.isChecked()
    window.config_page.config_saved.emit(
        {"auto_restart": {"enabled": new_value}}
    )
    assert window.dashboard_page.auto_restart_checkbox.isChecked() is new_value

    window.statistics_page.begin_run()
    assert window.statistics_page._pending_run_id is True
    assert window.statistics_page._snapshot.current_run.battle_count == 0

    worker = _ShortWorker(window)
    window._device_check_thread = worker
    worker.start()
    window.close()
    assert window.isVisible()
    assert not window.isEnabled()
    window._close_deadline = time.monotonic() - 1
    window._retry_pending_close()
    assert window.isVisible()
    assert window.isEnabled()
    assert window._close_pending is False

    worker.wait(1000)
    assert not worker.isRunning()
    window.close()
    _process_events(app, 3)
    assert not window.isVisible()


if __name__ == "__main__":
    test_command_listener_lifecycle()
    test_disclaimer_remember_choice()
    test_deck_apply_is_transactional()
    test_main_window_workflow()
    print("smoke_ui_workflow: ok")
