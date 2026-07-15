import logging
import os
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication

from src.app.bootstrap import _command_listener
from src.ui.card_catalog import (
    CardEntry,
    get_card_resource_root,
    load_card_catalog,
    resolve_card_entry,
)
from src.ui.main_window import ShadowverseUI
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
    original_dialog = ShadowverseUI.show_startup_dialog
    ShadowverseUI.show_startup_dialog = lambda self: True
    try:
        window = ShadowverseUI(lambda **kwargs: None, queue.Queue(), queue.Queue())
    finally:
        ShadowverseUI.show_startup_dialog = original_dialog

    window.resize(1280, 720)
    window.show()
    _process_events(app)

    window.state.set_run_status("connecting")
    assert not window.dashboard_page.adb_input.isEnabled()
    window._device_config = {"serial": "device-a", "is_global": False}
    window.dashboard_page.adb_input.setText("device-b")
    window._on_device_connection_checked(True, "connected", {})
    assert window.state.device["serial"] == "device-a"
    assert window.dashboard_page.adb_input.isEnabled()

    for key in ("dashboard", "deck", "cards", "stats", "settings", "logs"):
        window.navigate(key)
        _process_events(app, 2)
        assert window.stacked_widget.currentWidget() is window.pages[key]

    workspace = window.deck_workspace_page
    assert len(workspace.catalog) == 957
    assert workspace.library_list.count() == 957
    assert workspace.workspace_is_applied() is True

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

    first = workspace.catalog[0]
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
    assert len(workspace.selected_entries) == 1
    assert workspace.workspace_is_applied() is False
    assert window.dashboard_page.deck_state_label.text() == "待应用"
    workspace.generate_share_code()
    assert workspace.share_output.toPlainText().strip()

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
    test_deck_apply_is_transactional()
    test_main_window_workflow()
    print("smoke_ui_workflow: ok")
