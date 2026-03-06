#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card effects editor (Step3A 2nd-level UI).

This dialog edits `strategy.effects` using the Step3A op schema.
It only depends on lightweight config registries (no cv/u2/game imports).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config.config_repository import ConfigRepository
from src.config.effects_registry import (
    CONTEXT_FOLLOWER,
    CONTEXT_HAND_CARD,
    get_operation,
    get_operations,
    get_target_kind,
    get_target_kinds,
    get_triggers,
)
from src.config.paths import get_config_path
from src.config.strategy_effects import get_card_effect_steps


# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _norm_select_option(v: Any) -> Optional[int]:
    if v in (1, "1", "选项1", "Option1", "option1"):
        return 1
    if v in (2, "2", "选项2", "Option2", "option2"):
        return 2
    return None


class TargetSpecEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._param_widgets: Dict[str, Any] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("目标:"))

        self.kind_combo = QComboBox()
        for kd in get_target_kinds():
            self.kind_combo.addItem(str(kd.get("label") or kd.get("kind") or ""), str(kd.get("kind") or ""))
        self.kind_combo.currentIndexChanged.connect(self._rebuild_selector)
        layout.addWidget(self.kind_combo)

        self.selector_combo = QComboBox()
        self.selector_combo.currentIndexChanged.connect(self._rebuild_params)
        layout.addWidget(self.selector_combo)

        self.params_container = QWidget()
        self.params_layout = QHBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_container)

        layout.addStretch()

        self._rebuild_selector()

    def _current_kind(self) -> str:
        return str(self.kind_combo.currentData() or "")

    def _current_selector(self) -> str:
        return str(self.selector_combo.currentData() or "")

    def _rebuild_selector(self) -> None:
        kind = self._current_kind()
        kd = get_target_kind(kind)
        selectors = []
        if isinstance(kd, dict):
            selectors = kd.get("selectors") or []

        self.selector_combo.blockSignals(True)
        self.selector_combo.clear()
        for sd in selectors:
            if not isinstance(sd, dict):
                continue
            self.selector_combo.addItem(str(sd.get("label") or sd.get("id") or ""), str(sd.get("id") or ""))
        self.selector_combo.blockSignals(False)

        self._rebuild_params()

    def _clear_params(self) -> None:
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._param_widgets = {}

    def _rebuild_params(self) -> None:
        self._clear_params()

        kind = self._current_kind()
        selector = self._current_selector()
        kd = get_target_kind(kind)
        params_schema = []
        if isinstance(kd, dict):
            for sd in kd.get("selectors") or []:
                if not isinstance(sd, dict):
                    continue
                if str(sd.get("id") or "") == selector:
                    params_schema = sd.get("params_schema") or []
                    break

        for p in params_schema:
            if not isinstance(p, dict):
                continue
            w = _build_param_widget(p)
            if w is None:
                continue
            name = str(p.get("name") or "")
            if name:
                self._param_widgets[name] = (p, w)
            self.params_layout.addWidget(w)

        self.params_layout.addStretch()

    def load(self, target_spec: Any) -> None:
        if not isinstance(target_spec, dict):
            target_spec = {}
        kind = str(target_spec.get("kind") or "")
        selector = str(target_spec.get("selector") or "")
        params = target_spec.get("params")
        if not isinstance(params, dict):
            params = {}

        idx = self.kind_combo.findData(kind)
        if idx >= 0:
            self.kind_combo.setCurrentIndex(idx)
        else:
            self.kind_combo.setCurrentIndex(0)
        self._rebuild_selector()

        sidx = self.selector_combo.findData(selector)
        if sidx >= 0:
            self.selector_combo.setCurrentIndex(sidx)
        else:
            self.selector_combo.setCurrentIndex(0)
        self._rebuild_params()

        for name, (spec, w) in list(self._param_widgets.items()):
            if name in params:
                _set_param_widget_value(spec, w, params.get(name))

    def value(self) -> Dict[str, Any]:
        kind = self._current_kind()
        selector = self._current_selector()

        params: Dict[str, Any] = {}
        for name, (spec, w) in list(self._param_widgets.items()):
            params[name] = _get_param_widget_value(spec, w)

        return {"kind": kind, "selector": selector, "params": params}


def _build_param_widget(param_spec: Dict[str, Any]) -> Optional[QWidget]:
    ptype = str(param_spec.get("type") or "")
    label = str(param_spec.get("label") or param_spec.get("name") or "")

    if ptype == "bool":
        cb = QCheckBox(label)
        cb.setChecked(bool(param_spec.get("default", False)))
        return cb

    if ptype == "int":
        box = QSpinBox()
        box.setPrefix(f"{label}:" if label else "")
        box.setRange(_safe_int(param_spec.get("min", -10**9), -10**9), _safe_int(param_spec.get("max", 10**9), 10**9))
        box.setValue(_safe_int(param_spec.get("default", 0), 0))
        box.setMaximumWidth(150)
        return box

    if ptype == "float":
        box = QDoubleSpinBox()
        box.setPrefix(f"{label}:" if label else "")
        box.setDecimals(3)
        box.setRange(_safe_float(param_spec.get("min", -10**9), -10**9), _safe_float(param_spec.get("max", 10**9), 10**9))
        box.setValue(_safe_float(param_spec.get("default", 0.0), 0.0))
        box.setMaximumWidth(170)
        return box

    if ptype == "str":
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(QLabel(f"{label}:"))
        le = QLineEdit()
        le.setText(str(param_spec.get("default", "") or ""))
        le.setMaximumWidth(220)
        lay.addWidget(le)
        return w

    if ptype == "enum":
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(QLabel(f"{label}:"))
        combo = QComboBox()
        for opt in param_spec.get("options") or []:
            if not isinstance(opt, dict):
                continue
            combo.addItem(str(opt.get("label") or opt.get("value") or ""), opt.get("value"))
        default = param_spec.get("default")
        didx = combo.findData(default)
        if didx >= 0:
            combo.setCurrentIndex(didx)
        lay.addWidget(combo)
        return w

    if ptype == "target_spec":
        return TargetSpecEditor()

    return None


def _find_inner_widget(container: QWidget, widget_type: Any) -> Optional[Any]:
    try:
        return container.findChild(widget_type)
    except Exception:
        return None


def _set_param_widget_value(param_spec: Dict[str, Any], widget: QWidget, value: Any) -> None:
    ptype = str(param_spec.get("type") or "")
    if ptype == "bool" and isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
        return
    if ptype == "int" and isinstance(widget, QSpinBox):
        widget.setValue(_safe_int(value, widget.value()))
        return
    if ptype == "float" and isinstance(widget, QDoubleSpinBox):
        widget.setValue(_safe_float(value, widget.value()))
        return
    if ptype == "str":
        le = _find_inner_widget(widget, QLineEdit)
        if le is not None:
            le.setText(str(value or ""))
        return
    if ptype == "enum":
        combo = _find_inner_widget(widget, QComboBox)
        if combo is not None:
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return
    if ptype == "target_spec" and isinstance(widget, TargetSpecEditor):
        widget.load(value)
        return


def _get_param_widget_value(param_spec: Dict[str, Any], widget: QWidget) -> Any:
    ptype = str(param_spec.get("type") or "")
    if ptype == "bool" and isinstance(widget, QCheckBox):
        return bool(widget.isChecked())
    if ptype == "int" and isinstance(widget, QSpinBox):
        return int(widget.value())
    if ptype == "float" and isinstance(widget, QDoubleSpinBox):
        return float(widget.value())
    if ptype == "str":
        le = _find_inner_widget(widget, QLineEdit)
        return str(le.text()) if le is not None else ""
    if ptype == "enum":
        combo = _find_inner_widget(widget, QComboBox)
        return combo.currentData() if combo is not None else None
    if ptype == "target_spec" and isinstance(widget, TargetSpecEditor):
        return widget.value()
    return None


class StepRow(QWidget):
    def __init__(
        self,
        *,
        context_kind: str,
        step: Dict[str, Any],
        on_move_up,
        on_move_down,
        on_delete,
        parent=None,
    ):
        super().__init__(parent)
        self.context_kind = str(context_kind or "")
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_delete = on_delete

        self._param_widgets: Dict[str, Any] = {}

        self.op_spec: Dict[str, Any] = dict(step or {})
        if "op" not in self.op_spec:
            self.op_spec["op"] = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("操作:"))
        self.op_combo = QComboBox()
        for op_def in get_operations(context_kind=self.context_kind):
            self.op_combo.addItem(str(op_def.get("label") or op_def.get("op_id") or ""), str(op_def.get("op_id") or ""))

        layout.addWidget(self.op_combo)

        self.params_container = QWidget()
        self.params_layout = QHBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_container)
        layout.addStretch()

        btn_up = QPushButton("↑")
        btn_up.setMaximumWidth(30)
        btn_up.clicked.connect(lambda: self._on_move_up(self))
        layout.addWidget(btn_up)

        btn_down = QPushButton("↓")
        btn_down.setMaximumWidth(30)
        btn_down.clicked.connect(lambda: self._on_move_down(self))
        layout.addWidget(btn_down)

        btn_del = QPushButton("删除")
        btn_del.setMaximumWidth(60)
        btn_del.clicked.connect(lambda: self._on_delete(self))
        layout.addWidget(btn_del)

        # Init selection
        op_id = str(self.op_spec.get("op") or "")
        idx = self.op_combo.findData(op_id)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)
        else:
            self.op_combo.setCurrentIndex(0)
            self.op_spec["op"] = str(self.op_combo.currentData() or "")

        self.op_combo.currentIndexChanged.connect(self._on_op_changed)
        self._rebuild_params()

    def _on_op_changed(self) -> None:
        self.op_spec["op"] = str(self.op_combo.currentData() or "")
        # Reset params to defaults when op changes.
        self.op_spec = {"op": self.op_spec["op"]}
        self._rebuild_params()

    def _clear_params(self) -> None:
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._param_widgets = {}

    def _rebuild_params(self) -> None:
        self._clear_params()
        op_id = str(self.op_combo.currentData() or "")
        op_def = get_operation(op_id)
        params_schema = []
        if isinstance(op_def, dict):
            params_schema = op_def.get("params_schema") or []

        for p in params_schema:
            if not isinstance(p, dict):
                continue
            w = _build_param_widget(p)
            if w is None:
                continue
            name = str(p.get("name") or "")
            if name:
                self._param_widgets[name] = (p, w)

            # Load default / current
            if name in self.op_spec:
                _set_param_widget_value(p, w, self.op_spec.get(name))
            elif "default" in p:
                _set_param_widget_value(p, w, p.get("default"))
            self.params_layout.addWidget(w)

        self.params_layout.addStretch()

    def value(self) -> Dict[str, Any]:
        op_id = str(self.op_combo.currentData() or "")
        out: Dict[str, Any] = {"op": op_id}
        for name, (spec, w) in list(self._param_widgets.items()):
            out[name] = _get_param_widget_value(spec, w)
        return out


class RawStepRow(QWidget):
    def __init__(self, *, raw_step: Dict[str, Any], on_delete, parent=None):
        super().__init__(parent)
        self.raw_step = dict(raw_step or {})
        self._on_delete = on_delete

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("未知Step:"))
        preview = json.dumps(self.raw_step, ensure_ascii=False, sort_keys=True)
        lab = QLabel(preview)
        lab.setToolTip(preview)
        lab.setStyleSheet("color: #FFCC88;")
        layout.addWidget(lab)
        layout.addStretch()

        btn_del = QPushButton("删除")
        btn_del.setMaximumWidth(60)
        btn_del.clicked.connect(lambda: self._on_delete(self))
        layout.addWidget(btn_del)

    def value(self) -> Dict[str, Any]:
        return dict(self.raw_step)


class TriggerEditor(QWidget):
    def __init__(self, *, trigger_id: str, context_kind: str, parent=None):
        super().__init__(parent)
        self.trigger_id = str(trigger_id or "")
        self.context_kind = str(context_kind or "")
        self.rows: List[QWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rows_container)

        btn_add = QPushButton("添加步骤")
        btn_add.clicked.connect(self.add_step)
        layout.addWidget(btn_add)

    def _move_row(self, row: QWidget, delta: int) -> None:
        try:
            idx = self.rows.index(row)
        except Exception:
            return
        new_idx = idx + int(delta)
        if new_idx < 0 or new_idx >= len(self.rows):
            return
        self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
        self._rebuild_layout()

    def _delete_row(self, row: QWidget) -> None:
        try:
            self.rows.remove(row)
        except Exception:
            return
        try:
            row.deleteLater()
        except Exception:
            pass
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)

        for r in self.rows:
            self.rows_layout.addWidget(r)
        self.rows_layout.addStretch()

    def clear(self) -> None:
        for r in list(self.rows):
            try:
                r.deleteLater()
            except Exception:
                pass
        self.rows = []
        self._rebuild_layout()

    def add_step(self, step: Optional[Dict[str, Any]] = None) -> None:
        step = dict(step or {})
        op_id = str(step.get("op") or "")
        op_def = get_operation(op_id) if op_id else None
        if not op_id or not isinstance(op_def, dict):
            # default to first op for this context
            ops = get_operations(context_kind=self.context_kind)
            if ops:
                step = {"op": str(ops[0].get("op_id") or "")}
        row = StepRow(
            context_kind=self.context_kind,
            step=step,
            on_move_up=lambda r: self._move_row(r, -1),
            on_move_down=lambda r: self._move_row(r, 1),
            on_delete=self._delete_row,
        )
        self.rows.append(row)
        self._rebuild_layout()

    def add_raw_step(self, raw_step: Dict[str, Any]) -> None:
        row = RawStepRow(raw_step=raw_step, on_delete=self._delete_row)
        self.rows.append(row)
        self._rebuild_layout()

    def load_steps(self, steps: List[Dict[str, Any]]) -> None:
        self.clear()
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            op_id = step.get("op")
            if isinstance(op_id, str) and op_id:
                op_def = get_operation(op_id)
                if isinstance(op_def, dict):
                    self.add_step(step)
                else:
                    self.add_raw_step(step)
                continue

            # Legacy Step2B dict: expand to ops but preserve unknown keys.
            used_any = False
            if "select_option" in step:
                opt = _norm_select_option(step.get("select_option"))
                if opt is not None:
                    self.add_step({"op": "select_option", "index": int(opt)})
                    used_any = True
            if "target_type" in step:
                tt = step.get("target_type")
                if isinstance(tt, str) and tt:
                    self.add_step({"op": "legacy_target_type", "target_type": str(tt)})
                    used_any = True
            if "action" in step:
                act = step.get("action")
                if isinstance(act, str) and act:
                    self.add_step({"op": "legacy_action", "action": str(act)})
                    used_any = True

            if not used_any:
                self.add_raw_step(step)

    def value(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in self.rows:
            try:
                out.append(r.value())
            except Exception:
                continue
        return [s for s in out if isinstance(s, dict) and s]


class CardEffectsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        base_name: str,
        config_key: str,
        display_name: str,
        is_enhance: bool,
    ):
        super().__init__(parent)
        self.base_name = str(base_name or "")
        self.config_key = str(config_key or base_name or "")
        self.display_name = str(display_name or base_name or "")
        self.is_enhance = bool(is_enhance)

        self.setWindowTitle(f"特殊效果 - {self.display_name}")
        self.resize(920, 520)

        self.repo = ConfigRepository(get_config_path())

        main = QVBoxLayout(self)

        hint = QLabel(
            "选择触发时机，并为每个触发时机配置操作序列。\n"
            "提示：基础卡可配置通用触发；爆能档位可配置仅该档位生效的触发。\n"
            "提示：爆能档位默认继承本体同触发效果；若配置了同类效果（如同一BUFF类型）则以爆能档位覆盖。\n"
            "提示：BUFF请先选操作“BUFF”，再在第二个下拉选择“其他友方/自身”，并分别填写攻击变化X与生命变化Y。"
        )
        hint.setStyleSheet("color: #AACCFF;")
        main.addWidget(hint)

        if self.is_enhance:
            enhance_notice = QLabel("当前为爆能档位配置：可设置该爆能档位专属的出牌/攻击/进化触发效果。")
            enhance_notice.setStyleSheet("color: #FFCC88;")
            main.addWidget(enhance_notice)

        # Trigger multi-select
        trig_bar = QHBoxLayout()
        trig_bar.addWidget(QLabel("触发时机:"))
        self.trig_checks: Dict[str, QCheckBox] = {}
        self.trig_groups: Dict[str, QGroupBox] = {}
        self.trig_editors: Dict[str, TriggerEditor] = {}

        allowed = []
        for t in get_triggers():
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or "")
            if not tid:
                continue
            allowed.append(t)

        for t in allowed:
            tid = str(t.get("id") or "")
            cb = QCheckBox(str(t.get("label") or tid))
            cb.stateChanged.connect(lambda _v, x=tid: self._toggle_trigger(x))
            trig_bar.addWidget(cb)
            self.trig_checks[tid] = cb
        trig_bar.addStretch()
        main.addLayout(trig_bar)

        # Scroll content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        main.addWidget(scroll)

        # Build per-trigger editors
        for t in allowed:
            tid = str(t.get("id") or "")
            ck = str(t.get("context_kind") or "")

            group = QGroupBox(str(t.get("label") or tid))
            group_lay = QVBoxLayout(group)
            editor = TriggerEditor(trigger_id=tid, context_kind=ck)
            group_lay.addWidget(editor)

            self.scroll_layout.addWidget(group)
            self.trig_groups[tid] = group
            self.trig_editors[tid] = editor

        self.scroll_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)

        self._load_existing()

    def _key_for_trigger(self, trigger_id: str) -> str:
        if self.is_enhance:
            return self.config_key

        t = None
        for d in get_triggers():
            if str(d.get("id") or "") == str(trigger_id or ""):
                t = d
                break
        ck = str(t.get("context_kind") or "") if isinstance(t, dict) else ""
        if ck == CONTEXT_HAND_CARD:
            return self.config_key
        return self.base_name

    def _load_existing(self) -> None:
        cfg, parse_ok, err = self.repo.load_existing(allow_default_on_error=False)
        if cfg is None:
            QMessageBox.warning(self, "加载失败", f"config.json解析失败: {str(err or '')}")
            return

        effects = cfg.get("strategy", {}).get("effects", {})
        if not isinstance(effects, dict):
            effects = {}

        for tid, cb in list(self.trig_checks.items()):
            key = self._key_for_trigger(tid)
            card_eff = effects.get(key)
            if not isinstance(card_eff, dict):
                card_eff = {}
            steps = card_eff.get(tid)
            enabled = isinstance(steps, list) and any(isinstance(s, dict) for s in steps)
            cb.setChecked(bool(enabled))

            editor = self.trig_editors.get(tid)
            if editor is None:
                continue
            raw_steps = get_card_effect_steps(cfg, card_name=key, trigger=tid)
            editor.load_steps(list(raw_steps or []))

        for tid in list(self.trig_checks.keys()):
            self._toggle_trigger(tid)

    def _toggle_trigger(self, trigger_id: str) -> None:
        cb = self.trig_checks.get(trigger_id)
        group = self.trig_groups.get(trigger_id)
        if cb is None or group is None:
            return
        enabled = bool(cb.isChecked())
        group.setVisible(enabled)

        # UX: when a trigger is enabled, prefill one default step so users don't
        # have to manually click "添加步骤" every time.
        if enabled:
            editor = self.trig_editors.get(trigger_id)
            if editor is not None and not getattr(editor, "rows", None):
                try:
                    editor.add_step()
                except Exception:
                    pass

    def _save(self) -> None:
        cfg, parse_ok, err = self.repo.load_existing(allow_default_on_error=False)
        if cfg is None:
            QMessageBox.warning(self, "保存失败", f"config.json解析失败: {str(err or '')}")
            return

        strategy = cfg.get("strategy")
        if not isinstance(strategy, dict):
            strategy = {}
            cfg["strategy"] = strategy
        effects = strategy.get("effects")
        if not isinstance(effects, dict):
            effects = {}
            strategy["effects"] = effects

        for tid, cb in list(self.trig_checks.items()):
            key = self._key_for_trigger(tid)
            card_eff = effects.get(key)
            if not isinstance(card_eff, dict):
                card_eff = {}

            if cb.isChecked():
                editor = self.trig_editors.get(tid)
                steps = editor.value() if editor is not None else []
                # Clean empty
                steps = [s for s in steps if isinstance(s, dict) and s]
                if steps:
                    card_eff[tid] = steps
                elif tid in card_eff:
                    del card_eff[tid]
            else:
                if tid in card_eff:
                    del card_eff[tid]

            if card_eff:
                effects[key] = card_eff
            else:
                if key in effects:
                    del effects[key]

        res = self.repo.replace_with_snapshot(cfg, indent=4, ensure_ascii=False)
        if not res.ok:
            QMessageBox.warning(self, "保存失败", f"保存失败: {str(res.error or '')}")
            return

        QMessageBox.information(self, "成功", "特殊效果已保存")
        self.accept()
