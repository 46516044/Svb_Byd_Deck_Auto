"""面向界面的配置仓储，也是配置写入的唯一入口。

旧界面曾在多个位置直接写入 ``config.json``，容易造成迁移结果不一致，或在恢复
卡组快照时只覆盖部分结构。本模块将界面所需能力统一为：

- 加载现有配置，并可在解析失败时拒绝覆盖；
- 深度合并补丁，同时保留未知或隐藏字段；
- 写入前按 ``DEFAULT_CONFIG`` 规范化并执行迁移；
- 通过临时文件与 ``os.replace`` 原子落盘。
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.config.io_guard import is_in_battle
from src.config.migrations import (
    migrate_high_priority_cards_priority_fields,
    migrate_runtime_legacy_fields,
    migrate_strategy_name_keys,
    migrate_strategy_effects_schema,
    migrate_strategy_split_attack_times_buff,
    migrate_strategy_effects_to_ops,
    prune_invalid_strategy_effect_ops,
)
from src.config.paths import get_config_path
from src.config.persisted_config import prune_config_for_save
from src.config.settings import DEFAULT_CONFIG
from src.core.json_io import write_json_atomic

logger = logging.getLogger(__name__)


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """返回应用补丁后的副本，字典递归合并。

    字典会递归合并；补丁中的列表和普通值直接替换原值；嵌套容器均深拷贝，
    避免合并结果与调用方共享引用。
    """

    merged: Dict[str, Any] = copy.deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(patch, dict):
        return merged

    for k, v in patch.items():
        if k in merged and isinstance(merged.get(k), dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
            continue
        if isinstance(v, (dict, list)):
            merged[k] = copy.deepcopy(v)
        else:
            merged[k] = v
    return merged


def _normalize_and_migrate(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """与 ``DEFAULT_CONFIG`` 合并并执行结构迁移。"""

    cfg = _deep_merge(DEFAULT_CONFIG, user_config if isinstance(user_config, dict) else {})
    try:
        migrate_high_priority_cards_priority_fields(cfg)
    except Exception:
        pass
    try:
        migrate_strategy_name_keys(cfg)
    except Exception:
        pass
    try:
        migrate_strategy_effects_schema(cfg)
    except Exception:
        pass
    try:
        migrate_strategy_effects_to_ops(cfg)
    except Exception:
        pass
    try:
        migrate_strategy_split_attack_times_buff(cfg)
    except Exception:
        pass
    try:
        prune_invalid_strategy_effect_ops(cfg)
    except Exception:
        pass
    try:
        migrate_runtime_legacy_fields(cfg)
    except Exception:
        pass
    return cfg


@dataclass(frozen=True)
class ConfigWriteResult:
    ok: bool
    parse_ok: bool
    error: Optional[str] = None


class ConfigRepository:
    """供界面使用的 ``config.json`` 仓储式读写器。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = os.path.abspath(config_path or get_config_path())

    def load_existing(
        self, *, allow_default_on_error: bool = True
    ) -> tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
        """从磁盘加载 ``config.json``。

        返回 ``(配置或 None, 解析是否成功, 错误信息)``。文件不存在时返回规范化
        默认值；解析失败且允许回退时返回默认值并标记失败；不允许回退时返回
        ``None``，避免后续误覆盖损坏文件。
        """

        if not os.path.exists(self.config_path):
            return _normalize_and_migrate({}), True, None

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raw = {}
            return _normalize_and_migrate(raw), True, None
        except Exception as e:
            if not allow_default_on_error:
                return None, False, str(e)
            return _normalize_and_migrate({}), False, str(e)

    def save(
        self,
        config: Dict[str, Any],
        *,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> ConfigWriteResult:
        if is_in_battle():
            logger.warning("[IO] battle context: saving config to disk: %s", self.config_path)
        try:
            write_json_atomic(
                self.config_path,
                prune_config_for_save(config),
                indent=indent,
                ensure_ascii=ensure_ascii,
            )
            return ConfigWriteResult(ok=True, parse_ok=True, error=None)
        except Exception as e:
            return ConfigWriteResult(ok=False, parse_ok=True, error=str(e))

    def update(
        self,
        patch: Dict[str, Any],
        *,
        refuse_on_parse_error: bool = False,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> ConfigWriteResult:
        existing, parse_ok, err = self.load_existing(
            allow_default_on_error=not refuse_on_parse_error
        )
        if existing is None:
            return ConfigWriteResult(ok=False, parse_ok=False, error=err or "config.json parse failed")

        merged = _deep_merge(existing, patch if isinstance(patch, dict) else {})
        normalized = _normalize_and_migrate(merged)
        res = self.save(normalized, indent=indent, ensure_ascii=ensure_ascii)
        # 保留首次加载的解析状态，供需要区分“回退后写入”的调用方判断。
        return ConfigWriteResult(ok=res.ok, parse_ok=parse_ok, error=res.error or err)

    def replace_with_snapshot(
        self,
        snapshot_config: Dict[str, Any],
        *,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> ConfigWriteResult:
        normalized = _normalize_and_migrate(snapshot_config if isinstance(snapshot_config, dict) else {})
        return self.save(normalized, indent=indent, ensure_ascii=ensure_ascii)
