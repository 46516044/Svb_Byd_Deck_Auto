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
from src.ui.background import resolve_background_path, serialize_background_path
from src.config.config_repository import ConfigRepository
from src.ui.deck_io import (
    build_card_source_index,
    extract_deck_strategy_config,
    normalize_deck_card_records,
    normalize_derived_card_records,
    resolve_source_card_path,
    save_deck_snapshot,
)
from src.ui.statistics import load_statistics
import src.ui.statistics as statistics_module
import src.utils.consent_utils as consent_module
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


def test_card_catalog_contract() -> None:
    resource_root = Path(get_card_resource_root())
    assert resource_root.name == "SV_WB_Cards"
    assert (resource_root / "SV_WB_Cards.csv").is_file()

    catalog = load_card_catalog(str(resource_root))
    assert len(catalog) == 970
    assert len({entry.key for entry in catalog}) == len(catalog)
    assert len({entry.card_id for entry in catalog}) == len(catalog)
    assert all(not entry.filename.lower().endswith("_evo.webp") for entry in catalog)
    assert any(entry.cost >= 10 for entry in catalog)

    base_name = normalize_card_base_name(parse_card_filename("1_10201110_1_1.webp")[2])
    evolved_name = normalize_card_base_name(parse_card_filename("1_10201110_evo.webp")[2])
    assert base_name == evolved_name

    exact_index, stem_index = build_card_source_index(str(resource_root))
    resolved = resolve_source_card_path(
        str(resource_root),
        "10201110",
        exact_index=exact_index,
        stem_index=stem_index,
    )
    assert resolved and Path(resolved).name == "1_10201110_1_1.webp"


def test_background_path_round_trip() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / "Image" / "background.png"
        image_path.parent.mkdir()
        image_path.touch()
        stored = serialize_background_path(str(image_path), temp_dir)
        assert stored == "Image/background.png"
        assert resolve_background_path(stored, temp_dir) == str(image_path.resolve())


def test_background_config_is_persisted() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.json"
        expected = {
            "enabled": True,
            "path": "Image/background.png",
            "opacity": 30,
        }
        result = ConfigRepository(str(config_path)).update(
            {"ui": {"custom_background": expected}}
        )
        assert result.ok
        loaded, parse_ok, error = ConfigRepository(str(config_path)).load_existing()
        assert parse_ok, error
        assert loaded["ui"]["custom_background"] == expected


def test_disclaimer_consent_is_versioned() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.json"
        consent_path = Path(temp_dir) / "consent.txt"
        consent_path.write_text("用户已同意免责声明\n", encoding="utf-8")
        original_get_app_root = consent_module.get_app_root
        original_get_config_path = consent_module.get_config_path
        original_cwd = os.getcwd()
        try:
            consent_module.get_app_root = lambda: temp_dir
            consent_module.get_config_path = lambda: str(config_path)
            os.chdir(temp_dir)
            assert consent_module.check_consent_file() is False
            assert consent_module.save_consent(persist_to_config=True)
            assert consent_module.check_consent_file() is True
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            assert payload["agreed_to_disclaimer"] is True
            assert payload["disclaimer_version"] == consent_module.DISCLAIMER_VERSION
            assert consent_module.remove_consent()
            assert consent_module.check_consent_file() is False
            consent_module.accept_consent_for_session()
            assert consent_module.check_consent_file() is True
            assert consent_module.remove_consent()
        finally:
            os.chdir(original_cwd)
            consent_module.get_app_root = original_get_app_root
            consent_module.get_config_path = original_get_config_path


def test_deck_snapshot_saves_card_ids_and_counts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        deck_path = save_deck_snapshot(
            deck_name="smoke",
            cards=["1_10201110_1_1.webp", "1_10201110_1_1.webp", "1_10201110_evo.webp"],
            derived_cards=[
                "1_90001110_1_2.webp",
                {"card_id": "90001110", "count": 99},
            ],
            decks_dir=temp_dir,
            config_path=None,
        )
        with open(deck_path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)

    assert payload["version"] == 5
    assert payload["cards"] == [{"card_id": "10201110", "count": 2}]
    assert payload["derived_cards"] == [{"card_id": "90001110"}]


def test_deck_card_records_accept_legacy_and_structured_entries() -> None:
    records = normalize_deck_card_records(
        [
            "1_10201110_1_1.webp",
            "1_10201110_1_1.webp",
            {"card_id": "10001110", "count": 3},
        ]
    )
    assert records == [
        {"card_id": "1_10201110_1_1", "count": 2},
        {"card_id": "10001110", "count": 3},
    ]
    assert normalize_derived_card_records(
        [
            "1_10201110_1_1.webp",
            {"card_id": "10201110", "count": 40},
            {"card_id": "90001110"},
        ]
    ) == [
        {"card_id": "1_10201110_1_1"},
        {"card_id": "10201110"},
        {"card_id": "90001110"},
    ]


def test_deck_snapshot_rejects_more_than_three_copies() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            save_deck_snapshot(
                deck_name="invalid-count",
                cards=["1_10201110_1_1.webp"] * 4,
                decks_dir=temp_dir,
            )
        except ValueError as exc:
            assert "最多 3 张" in str(exc)
        else:
            raise AssertionError("four copies must be rejected")


def test_deck_snapshot_combines_base_and_alt_art_copy_limit() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            save_deck_snapshot(
                deck_name="invalid-alt-count",
                cards=[
                    {"card_id": "10204110", "count": 2},
                    {"card_id": "10204110@1", "count": 2},
                ],
                decks_dir=temp_dir,
            )
        except ValueError as exc:
            assert "异画合计" in str(exc)
        else:
            raise AssertionError("base card and alternate art must share the copy limit")


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
            cards=["1_10201110_1_1.webp"],
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
    test_background_path_round_trip()
    test_background_config_is_persisted()
    test_disclaimer_consent_is_versioned()
    test_deck_snapshot_saves_card_ids_and_counts()
    test_deck_card_records_accept_legacy_and_structured_entries()
    test_deck_snapshot_rejects_more_than_three_copies()
    test_deck_snapshot_combines_base_and_alt_art_copy_limit()
    test_legacy_deck_strategy_is_preserved()
    test_explicit_deck_strategy_wins_over_global_config()
    test_statistics_aggregate_contract()
    test_statistics_falls_back_to_launch_directory()
    print("smoke_ui_data: ok")
