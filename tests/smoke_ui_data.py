import json
import os
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ui.card_catalog import (
    get_card_resource_root,
    load_card_catalog,
)
from src.ui.deck_io import extract_deck_strategy_config, save_deck_snapshot
from src.ui.statistics import load_statistics
import src.ui.statistics as statistics_module
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


def test_card_catalog_contract() -> None:
    resource_root = Path(get_card_resource_root())
    assert resource_root.name == "SV_WB_Cards"
    assert (resource_root / "SV_WB_Cards.csv").is_file()

    catalog = load_card_catalog(str(resource_root))
    assert len(catalog) == 957
    assert len({entry.key for entry in catalog}) == len(catalog)
    assert all(not entry.filename.lower().endswith("_evo.webp") for entry in catalog)
    assert any(entry.cost >= 10 for entry in catalog)

    base_name = normalize_card_base_name(parse_card_filename("1_10201110_1_1.webp")[2])
    evolved_name = normalize_card_base_name(parse_card_filename("1_10201110_evo.webp")[2])
    assert base_name == evolved_name


def test_deck_snapshot_keeps_unique_template_refs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        deck_path = save_deck_snapshot(
            deck_name="smoke",
            cards=["1_10201110_1_1.webp", "1_10201110_1_1.webp", "1_10201110_evo.webp"],
            decks_dir=temp_dir,
            config_path=None,
        )
        with open(deck_path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)

    assert payload["version"] == 3
    assert payload["cards"] == ["1_10201110_1_1"]


def test_legacy_deck_strategy_is_preserved() -> None:
    strategy = extract_deck_strategy_config(
        {
            "cards": ["1_test_card"],
            "config": {
                "high_priority_cards": {"test_card": {"priority": 7}},
                "strategy": {
                    "effects": {"test_card": {"on_play": [{"op": "pass"}]}}
                },
            },
        }
    )

    assert strategy["high_priority_cards"]["test_card"]["priority"] == 7
    assert strategy["strategy"]["effects"]["test_card"]["on_play"]


def test_explicit_deck_strategy_wins_over_global_config() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.json"
        config_path.write_text(
            json.dumps(
                {"high_priority_cards": {"test_card": {"priority": 1}}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        expected = {"high_priority_cards": {"test_card": {"priority": 9}}}
        deck_path = save_deck_snapshot(
            deck_name="explicit-strategy",
            cards=["1_test_card"],
            decks_dir=temp_dir,
            config_path=str(config_path),
            strategy_config=expected,
        )
        with open(deck_path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)

    assert payload["strategy_config"] == expected


def test_statistics_aggregate_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        stats_path = Path(temp_dir) / "round_stats_test.json"
        stats_path.write_text(
            json.dumps(
                [
                    {
                        "date": "2026-07-14 10:00:00",
                        "rounds": 7,
                        "duration": "6分30秒",
                        "run_id": "run-a",
                    },
                    {
                        "date": "2026-07-14 11:00:00",
                        "rounds": 9,
                        "duration": "7:30",
                        "run_id": "run-a",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        snapshot = load_statistics(
            app_root=temp_dir,
            current_run_id="run-a",
        )

    assert snapshot.overall.battle_count == 2
    assert snapshot.current_run.battle_count == 2
    assert snapshot.overall.average_rounds == 8.0
    assert snapshot.overall.average_duration_seconds == 420.0


def test_statistics_falls_back_to_launch_directory() -> None:
    with tempfile.TemporaryDirectory() as app_root, tempfile.TemporaryDirectory() as launch_dir:
        stats_path = Path(launch_dir) / "round_stats_external.json"
        stats_path.write_text(
            json.dumps(
                [
                    {
                        "date": "2026-07-14 12:00:00",
                        "rounds": 5,
                        "duration": "3分0秒",
                        "run_id": "external-run",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        original_get_app_root = statistics_module.get_app_root
        original_cwd = os.getcwd()
        try:
            statistics_module.get_app_root = lambda: app_root
            os.chdir(launch_dir)
            snapshot = statistics_module.load_statistics()
        finally:
            os.chdir(original_cwd)
            statistics_module.get_app_root = original_get_app_root

    assert snapshot.overall.battle_count == 1
    assert snapshot.current_run_id == "external-run"


if __name__ == "__main__":
    test_card_catalog_contract()
    test_deck_snapshot_keeps_unique_template_refs()
    test_legacy_deck_strategy_is_preserved()
    test_explicit_deck_strategy_wins_over_global_config()
    test_statistics_aggregate_contract()
    test_statistics_falls_back_to_launch_directory()
    print("smoke_ui_data: ok")
