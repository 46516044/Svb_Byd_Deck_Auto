"""Shared deck IO helpers.

Saved decks are intended to be portable across machines/emulators, so we only
persist deck cards + strategy/effects (not device/ADB settings).
"""

from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.json_io import write_json_atomic
from src.utils.card_filename import (
    normalize_card_base_name,
    normalize_config_key,
    parse_card_filename,
    split_enhance_key,
)


SUPPORTED_CARD_IMAGE_EXTENSIONS: Tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)


def _card_ref_from_value(value: Any) -> str:
    """Convert card filename/path to a stable deck card reference (stem only)."""

    raw = os.path.basename(str(value or "").strip())
    if not raw:
        return ""

    stem, _ext = os.path.splitext(raw)
    return str(stem or raw)


def normalize_deck_cards(cards: List[str]) -> List[str]:
    """Normalize persisted deck cards to extension-free references."""

    out: List[str] = []
    seen = set()
    for item in list(cards or []):
        ref = _card_ref_from_value(item)
        if not ref:
            continue
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def build_card_source_index(source_dir: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Build exact/stem lookup indices for cards under a source directory."""

    exact: Dict[str, str] = {}
    stem: Dict[str, str] = {}
    if not os.path.isdir(source_dir):
        return exact, stem

    for root, _dirs, files in os.walk(source_dir):
        for fn in files:
            base = os.path.basename(str(fn or ""))
            if not base.lower().endswith(SUPPORTED_CARD_IMAGE_EXTENSIONS):
                continue

            full = os.path.join(root, base)
            exact.setdefault(base.lower(), full)

            name_key = _card_ref_from_value(base).lower()
            if name_key:
                stem.setdefault(name_key, full)

    return exact, stem


def resolve_source_card_path(
    source_dir: str,
    card_ref: str,
    *,
    exact_index: Optional[Dict[str, str]] = None,
    stem_index: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Resolve a card reference to a concrete source image path.

    Supports both legacy filename refs (with extension) and new stem refs.
    """

    raw = os.path.basename(str(card_ref or "").strip())
    if not raw:
        return None

    exact_map = exact_index
    stem_map = stem_index
    if exact_map is None or stem_map is None:
        exact_map, stem_map = build_card_source_index(source_dir)

    exact_hit = exact_map.get(raw.lower())
    if exact_hit:
        return exact_hit

    stem_key = _card_ref_from_value(raw).lower()
    if not stem_key:
        return None
    return stem_map.get(stem_key)


def _deck_base_names(cards: List[str]) -> List[str]:
    names: List[str] = []
    for fn in list(cards or []):
        try:
            _base_cost, _enh, name = parse_card_filename(fn)
        except Exception:
            name = ""
        name = normalize_card_base_name(str(name or "").strip())
        if name and name not in names:
            names.append(name)
    return names


def extract_strategy_config(
    cfg: Dict[str, Any], *, cards: List[str]
) -> Dict[str, Any]:
    """Extract a portable subset of config for a given deck.

    This intentionally excludes:
    - devices/adb settings
    - UI/runtime flags
    - other machine-specific configuration
    """

    if not isinstance(cfg, dict):
        return {}

    base_names = set(_deck_base_names(cards))

    def _filter_by_base_name(d: Any) -> Dict[str, Any]:
        if not isinstance(d, dict) or not base_names:
            return {}
        out: Dict[str, Any] = {}
        for k, v in d.items():
            if not isinstance(k, str):
                continue
            base, _enh = split_enhance_key(k)
            base_norm = normalize_card_base_name(str(base or ""))
            if str(base_norm) in base_names:
                nk = normalize_config_key(k)
                if nk in out and isinstance(out.get(nk), dict) and isinstance(v, dict):
                    merged = copy.deepcopy(out[nk])
                    for mk, mv in v.items():
                        merged[mk] = copy.deepcopy(mv)
                    out[nk] = merged
                else:
                    out[nk] = copy.deepcopy(v)
        return out

    high_priority = _filter_by_base_name(cfg.get("high_priority_cards"))
    evolve_priority = _filter_by_base_name(cfg.get("evolve_priority_cards"))

    effects = {}
    try:
        effects = cfg.get("strategy", {}).get("effects", {})
    except Exception:
        effects = {}
    effects = _filter_by_base_name(effects)

    game = cfg.get("game", {})
    game_subset: Dict[str, Any] = {}
    if isinstance(game, dict):
        if isinstance(game.get("card_replacement_strategy"), str):
            game_subset["card_replacement_strategy"] = str(
                game.get("card_replacement_strategy")
            )

    out: Dict[str, Any] = {
        "high_priority_cards": high_priority,
        "evolve_priority_cards": evolve_priority,
        "strategy": {"effects": effects},
    }
    if game_subset:
        out["game"] = game_subset
    return out


def apply_strategy_config(
    base_config: Dict[str, Any], *, strategy_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply a strategy_config onto an existing config, replacing sections."""

    cfg = copy.deepcopy(base_config) if isinstance(base_config, dict) else {}
    sc = strategy_config if isinstance(strategy_config, dict) else {}

    def _normalize_mapping_keys(d: Any) -> Dict[str, Any]:
        if not isinstance(d, dict):
            return {}
        out: Dict[str, Any] = {}
        for k, v in d.items():
            nk = normalize_config_key(str(k or ""))
            if not nk:
                continue
            if nk in out and isinstance(out.get(nk), dict) and isinstance(v, dict):
                merged = copy.deepcopy(out[nk])
                for mk, mv in v.items():
                    merged[mk] = copy.deepcopy(mv)
                out[nk] = merged
            else:
                out[nk] = copy.deepcopy(v)
        return out

    if isinstance(sc.get("high_priority_cards"), dict):
        cfg["high_priority_cards"] = _normalize_mapping_keys(sc["high_priority_cards"])
    if isinstance(sc.get("evolve_priority_cards"), dict):
        cfg["evolve_priority_cards"] = _normalize_mapping_keys(sc["evolve_priority_cards"])

    # Allow both shapes:
    # - {"strategy": {"effects": {...}}}
    # - {"effects": {...}}
    effects = None
    if isinstance(sc.get("strategy"), dict) and isinstance(sc["strategy"].get("effects"), dict):
        effects = sc["strategy"]["effects"]
    elif isinstance(sc.get("effects"), dict):
        effects = sc.get("effects")

    if effects is not None:
        if not isinstance(cfg.get("strategy"), dict):
            cfg["strategy"] = {}
        cfg["strategy"]["effects"] = _normalize_mapping_keys(effects)

    if isinstance(sc.get("game"), dict):
        if not isinstance(cfg.get("game"), dict):
            cfg["game"] = {}
        for k in ("card_replacement_strategy",):
            if k in sc["game"]:
                cfg["game"][k] = copy.deepcopy(sc["game"][k])

    return cfg


def save_deck_snapshot(
    *,
    deck_name: str,
    cards: List[str],
    decks_dir: str,
    config_path: Optional[str] = None,
) -> str:
    """Save a deck snapshot json and return its file path."""

    name = (deck_name or "").strip()
    if not name:
        raise ValueError("deck_name is empty")

    os.makedirs(decks_dir, exist_ok=True)

    normalized_cards = normalize_deck_cards(list(cards or []))

    deck_data: Dict[str, Any] = {
        "version": 3,
        "name": name,
        "cards": list(normalized_cards or []),
        "timestamp": int(time.time()),
    }

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            sc = extract_strategy_config(cfg, cards=list(normalized_cards or []))
            if sc:
                deck_data["strategy_config"] = sc

    deck_file = os.path.join(decks_dir, f"{name}.json")
    write_json_atomic(deck_file, deck_data, ensure_ascii=False, indent=2)
    return deck_file
