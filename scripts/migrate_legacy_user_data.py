from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from src.config.config_repository import _normalize_and_migrate
from src.config.persisted_config import prune_config_for_save
from src.core.json_io import write_json_atomic
from src.ui.card_catalog import (
    CardEntry,
    get_card_resource_root,
    load_card_catalog,
    resolve_card_entry,
)
from src.ui.deck_io import (
    DECK_SCHEMA_VERSION,
    extract_strategy_config,
    serialize_deck_card_records,
)
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


LEGACY_NAME_ALIASES = {
    "智慧光辉（异画）": "智慧光辉",
    "女仆天使·切蕾塔（异画）": "女仆天使·切蕾塔",
    "小栗帽（联动异画）": "小栗帽",
    "混融的祈祷者（异画）": "混融的祈祷者",
    "悬丝傀儡（异画）": "悬丝傀儡",
    "炎之法则·威尔纳斯（异画）": "炎之法则·威尔纳斯",
    "凶鲎战士": "凶鲨战士",
}

# 这些旧显示名在当前 CSV 中存在歧义；映射依据 quanka 提交 92af09d 中的
# 编码卡图变更确定。
LEGACY_CARD_IDS = {
    "智慧光辉（异画）": "10031310@1",
    "暴风破": "10131320",
    "女仆天使·切蕾塔（异画）": "10202110@1",
    "小栗帽（联动异画）": "10204110@1",
    "混融的祈祷者（异画）": "10352110@1",
    "悬丝傀儡（异画）": "90071110@1",
    "炎之法则·威尔纳斯（异画）": "10444110@2",
    "凶鲎战士": "10041130",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _merge_mapping_value(existing: Any, incoming: Any, *, effects: bool) -> Any:
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return copy.deepcopy(existing)
    merged = copy.deepcopy(existing)
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = copy.deepcopy(value)
            continue
        if effects and isinstance(merged[key], list) and isinstance(value, list):
            for step in value:
                if step not in merged[key]:
                    merged[key].append(copy.deepcopy(step))
    return merged


def _normalize_legacy_strategy_names(config: dict[str, Any]) -> None:
    sections: list[tuple[dict[str, Any], bool]] = []
    for key in ("high_priority_cards", "evolve_priority_cards"):
        section = config.get(key)
        if isinstance(section, dict):
            sections.append((section, False))
    strategy = config.get("strategy")
    if isinstance(strategy, dict) and isinstance(strategy.get("effects"), dict):
        sections.append((strategy["effects"], True))

    for section, is_effects in sections:
        for legacy_name, canonical_name in LEGACY_NAME_ALIASES.items():
            if legacy_name not in section:
                continue
            legacy_value = section.pop(legacy_name)
            if canonical_name in section:
                section[canonical_name] = _merge_mapping_value(
                    section[canonical_name],
                    legacy_value,
                    effects=is_effects,
                )
            else:
                section[canonical_name] = copy.deepcopy(legacy_value)


def migrate_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = _normalize_and_migrate(copy.deepcopy(payload))
    _normalize_legacy_strategy_names(migrated)
    return prune_config_for_save(migrated)


class CardReferenceMigrator:
    def __init__(self, resource_root: str):
        self.resource_root = resource_root
        self.catalog = load_card_catalog(resource_root)
        self.by_card_id: dict[str, list[CardEntry]] = {}
        self.by_name: dict[str, list[CardEntry]] = {}
        for entry in self.catalog:
            self.by_card_id.setdefault(entry.card_id, []).append(entry)
            self.by_name.setdefault(entry.name, []).append(entry)

    def _by_explicit_id(self, card_id: str) -> CardEntry | None:
        matches = self.by_card_id.get(card_id, [])
        return matches[0] if len(matches) == 1 else None

    def resolve(self, reference: object) -> tuple[CardEntry | None, str]:
        raw = str(reference or "").strip()
        direct = resolve_card_entry(raw, self.catalog, self.resource_root)
        if direct is not None:
            return direct, "current"

        cost, _enhance, parsed_name = parse_card_filename(raw)
        legacy_name = normalize_card_base_name(parsed_name)
        explicit_id = LEGACY_CARD_IDS.get(legacy_name)
        if explicit_id:
            explicit = self._by_explicit_id(explicit_id)
            if explicit is not None:
                return explicit, "explicit-alias"

        canonical_name = LEGACY_NAME_ALIASES.get(legacy_name, legacy_name)
        name_matches = self.by_name.get(canonical_name, [])
        same_cost = [entry for entry in name_matches if entry.cost == cost]
        if len(same_cost) == 1:
            return same_cost[0], "name-and-cost"

        base_matches = [entry for entry in name_matches if "@" not in entry.card_id]
        if len(base_matches) == 1:
            return base_matches[0], "canonical-name"

        return None, (
            f"unresolved reference={raw!r}, parsed=({cost}, {legacy_name!r}), "
            f"candidates={[entry.card_id for entry in name_matches]}"
        )

    def migrate_cards(self, cards: object) -> tuple[list[dict[str, Any]], Counter[str], list[str]]:
        migrated: list[dict[str, Any]] = []
        positions: dict[str, int] = {}
        methods: Counter[str] = Counter()
        errors: list[str] = []
        for reference in list(cards or []):
            entry, method = self.resolve(reference)
            if entry is None:
                errors.append(method)
                continue
            key = entry.card_id.casefold()
            if key in positions:
                migrated[positions[key]]["count"] += 1
                methods["duplicate-counted"] += 1
                continue
            positions[key] = len(migrated)
            migrated.append({"card_id": entry.card_id, "count": 1})
            methods[method] += 1
        return migrated, methods, errors


def migrate_deck_payload(
    payload: dict[str, Any],
    *,
    fallback_name: str,
    card_migrator: CardReferenceMigrator,
) -> tuple[dict[str, Any], Counter[str], list[str]]:
    cards, methods, errors = card_migrator.migrate_cards(payload.get("cards", []))
    if errors:
        return {}, methods, errors
    cards = serialize_deck_card_records(
        cards,
        resource_root=card_migrator.resource_root,
    )

    strategy_source = payload.get("strategy_config")
    if not isinstance(strategy_source, dict):
        strategy_source = payload.get("config")
    if not isinstance(strategy_source, dict):
        strategy_source = {}
    normalized_strategy = _normalize_and_migrate(copy.deepcopy(strategy_source))
    _normalize_legacy_strategy_names(normalized_strategy)
    strategy_config = extract_strategy_config(normalized_strategy, cards=cards)

    try:
        timestamp = int(payload.get("timestamp", 0) or 0)
    except (TypeError, ValueError):
        timestamp = 0
    migrated = {
        "version": DECK_SCHEMA_VERSION,
        "name": str(payload.get("name") or fallback_name).strip() or fallback_name,
        "cards": cards,
        "derived_cards": [],
        "timestamp": timestamp,
        "strategy_config": strategy_config,
    }
    return migrated, methods, []


def _backup_path(project_root: Path) -> Path:
    base = project_root / "migration_backups" / time.strftime("legacy_config_%Y%m%d_%H%M%S")
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}_{counter}")
        counter += 1
    return candidate


def _create_backup(
    backup_root: Path,
    *,
    config_path: Path,
    config_old_path: Path,
    decks_dir: Path,
) -> None:
    backup_root.mkdir(parents=True)
    shutil.copy2(config_path, backup_root / config_path.name)
    shutil.copy2(config_old_path, backup_root / config_old_path.name)
    shutil.copytree(decks_dir, backup_root / "saved_decks")


def _restore_backup(backup_root: Path, config_path: Path, decks_dir: Path) -> None:
    shutil.copy2(backup_root / config_path.name, config_path)
    backup_decks = backup_root / "saved_decks"
    for path in decks_dir.glob("*.json"):
        path.unlink()
    for path in backup_decks.glob("*.json"):
        shutil.copy2(path, decks_dir / path.name)


def migrate_user_data(project_root: Path, *, apply: bool) -> dict[str, Any]:
    config_path = project_root / "config.json"
    config_old_path = project_root / "config_old.json"
    decks_dir = project_root / "saved_decks"
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    if not config_old_path.is_file():
        raise FileNotFoundError(config_old_path)
    if not decks_dir.is_dir():
        raise FileNotFoundError(decks_dir)

    source_config = _load_json(config_old_path)
    migrated_config = migrate_config_payload(source_config)
    card_migrator = CardReferenceMigrator(get_card_resource_root(str(project_root)))

    migrated_decks: dict[Path, dict[str, Any]] = {}
    deck_reports: dict[str, Any] = {}
    all_errors: list[str] = []
    for deck_path in sorted(decks_dir.glob("*.json")):
        payload = _load_json(deck_path)
        migrated, methods, errors = migrate_deck_payload(
            payload,
            fallback_name=deck_path.stem,
            card_migrator=card_migrator,
        )
        strategy_config = migrated.get("strategy_config", {})
        if not isinstance(strategy_config, dict):
            strategy_config = {}
        deck_reports[deck_path.name] = {
            "cards_before": len(list(payload.get("cards") or [])),
            "cards_after": len(list(migrated.get("cards") or [])),
            "priority_cards": len(strategy_config.get("high_priority_cards", {})),
            "evolve_cards": len(strategy_config.get("evolve_priority_cards", {})),
            "effect_cards": len(strategy_config.get("strategy", {}).get("effects", {})),
            "methods": dict(methods),
            "errors": errors,
        }
        if errors:
            all_errors.extend(f"{deck_path.name}: {error}" for error in errors)
        else:
            migrated_decks[deck_path] = migrated

    if all_errors:
        raise RuntimeError("\n".join(all_errors))

    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "config_source": config_old_path.name,
        "config_priority_cards": len(migrated_config.get("high_priority_cards", {})),
        "config_evolve_cards": len(migrated_config.get("evolve_priority_cards", {})),
        "config_effect_cards": len(migrated_config.get("strategy", {}).get("effects", {})),
        "decks": deck_reports,
        "backup": None,
    }
    if not apply:
        return report

    backup_root = _backup_path(project_root)
    _create_backup(
        backup_root,
        config_path=config_path,
        config_old_path=config_old_path,
        decks_dir=decks_dir,
    )
    try:
        write_json_atomic(
            str(config_path),
            migrated_config,
            ensure_ascii=False,
            indent=2,
        )
        for deck_path, payload in migrated_decks.items():
            write_json_atomic(str(deck_path), payload, ensure_ascii=False, indent=2)

        _load_json(config_path)
        for deck_path in migrated_decks:
            payload = _load_json(deck_path)
            for record in payload.get("cards", []):
                reference = record.get("card_id") if isinstance(record, dict) else record
                if resolve_card_entry(
                    reference,
                    card_migrator.catalog,
                    card_migrator.resource_root,
                ) is None:
                    raise RuntimeError(
                        f"Post-write validation failed: {deck_path.name}: {reference}"
                    )
    except Exception:
        _restore_backup(backup_root, config_path, decks_dir)
        raise

    report["backup"] = str(backup_root)
    write_json_atomic(
        str(backup_root / "migration_report.json"),
        report,
        ensure_ascii=False,
        indent=2,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate config_old.json and saved_decks to the current schemas."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write migrated files after creating a timestamped backup.",
    )
    args = parser.parse_args()
    report = migrate_user_data(args.project_root.resolve(), apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
