"""将已保存卡组升级为包含独立衍生物列表的版本 5 格式。"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.json_io import write_json_atomic
from src.ui.card_catalog import get_card_resource_root
from src.ui.deck_io import (
    DECK_SCHEMA_VERSION,
    serialize_deck_card_records,
    serialize_derived_card_records,
)


def _load_deck(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"卡组不是 JSON 对象: {path}")
    return payload


def migrate_saved_decks(project_root: Path, *, apply: bool) -> dict[str, Any]:
    decks_dir = project_root / "saved_decks"
    if not decks_dir.is_dir():
        raise FileNotFoundError(decks_dir)

    migrated: dict[Path, dict[str, Any]] = {}
    resource_root = get_card_resource_root(str(project_root))
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "version": DECK_SCHEMA_VERSION,
        "backup": None,
        "decks": {},
    }
    for path in sorted(decks_dir.glob("*.json")):
        payload = _load_deck(path)
        records = serialize_deck_card_records(
            payload.get("cards") or [],
            resource_root=resource_root,
        )
        output = copy.deepcopy(payload)
        output["version"] = DECK_SCHEMA_VERSION
        output["cards"] = records
        output["derived_cards"] = serialize_derived_card_records(
            payload.get("derived_cards") or [],
            resource_root=resource_root,
        )
        migrated[path] = output
        report["decks"][path.name] = {
            "from_version": int(payload.get("version", 1) or 1),
            "card_types": len(records),
            "card_count": sum(int(record["count"]) for record in records),
        }

    if not apply:
        return report

    backup_root = (
        project_root
        / "migration_backups"
        / time.strftime("deck_schema_v5_%Y%m%d_%H%M%S")
    )
    shutil.copytree(decks_dir, backup_root / "saved_decks")
    report["backup"] = str(backup_root)

    try:
        for path, payload in migrated.items():
            write_json_atomic(str(path), payload, ensure_ascii=False, indent=2)
        for path in migrated:
            payload = _load_deck(path)
            if int(payload.get("version", 0) or 0) != DECK_SCHEMA_VERSION:
                raise RuntimeError(f"写入后版本校验失败: {path.name}")
            serialize_deck_card_records(
                payload.get("cards") or [],
                resource_root=resource_root,
            )
            serialize_derived_card_records(
                payload.get("derived_cards") or [],
                resource_root=resource_root,
            )
    except Exception:
        for path in decks_dir.glob("*.json"):
            path.unlink()
        for source in (backup_root / "saved_decks").glob("*.json"):
            shutil.copy2(source, decks_dir / source.name)
        raise

    write_json_atomic(
        str(backup_root / "migration_report.json"),
        report,
        ensure_ascii=False,
        indent=2,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="升级 saved_decks 为版本 5 格式")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply", action="store_true", help="备份后写入升级结果")
    args = parser.parse_args()
    report = migrate_saved_decks(args.project_root.resolve(), apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
