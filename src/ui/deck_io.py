"""卡组共用 IO 辅助函数。

已保存卡组需要能在不同机器和模拟器间迁移，因此只持久化卡牌、策略与效果，
不保存设备或 ADB 设置。
"""

from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.core.json_io import write_json_atomic
from src.utils.card_filename import (
    is_evo_card_name,
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
DECK_SCHEMA_VERSION = 5
MAX_DECK_SIZE = 40
MAX_CARD_COPIES = 3


def _card_ref_from_value(value: Any) -> str:
    """将卡牌文件名或路径转为只含主文件名的稳定卡组引用。"""

    raw = os.path.basename(str(value or "").strip())
    if not raw:
        return ""

    stem, _ext = os.path.splitext(raw)
    return str(stem or raw)


def normalize_deck_card_records(cards: Iterable[Any]) -> List[Dict[str, Any]]:
    """把新旧卡组条目规范为 ``card_id + count`` 记录。

    旧格式的字符串在此处仍保留为可解析引用，真正保存时再统一解析为卡牌 ID。
    """

    records: List[Dict[str, Any]] = []
    positions: Dict[str, int] = {}
    for item in list(cards or []):
        if isinstance(item, dict):
            reference = (
                item.get("card_id")
                or item.get("card_ref")
                or item.get("file")
                or item.get("filename")
            )
            raw_count = item.get("count", 1)
        else:
            reference = item
            raw_count = 1

        ref = _card_ref_from_value(reference)
        if not ref or is_evo_card_name(ref):
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue

        key = ref.casefold()
        if key in positions:
            records[positions[key]]["count"] += count
            continue
        positions[key] = len(records)
        records.append({"card_id": ref, "count": count})
    return records


def serialize_deck_card_records(
    cards: Iterable[Any],
    *,
    resource_root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """将卡组条目解析成可持久化的稳定卡牌 ID，并校验数量限制。"""

    from src.ui.card_catalog import (
        get_card_resource_root,
        load_card_catalog,
        resolve_card_entry,
    )

    records = normalize_deck_card_records(cards)
    resolved_root = resource_root or get_card_resource_root()
    catalog = load_card_catalog(resolved_root)
    serialized: List[Dict[str, Any]] = []
    positions: Dict[str, int] = {}
    for record in records:
        reference = str(record.get("card_id") or "")
        entry = resolve_card_entry(reference, catalog, resolved_root)
        if entry is None:
            raise ValueError(f"无法解析卡牌引用: {reference}")
        card_id = str(entry.card_id)
        key = card_id.casefold()
        count = int(record.get("count") or 0)
        if key in positions:
            serialized[positions[key]]["count"] += count
        else:
            positions[key] = len(serialized)
            serialized.append({"card_id": card_id, "count": count})

    copy_groups: Dict[str, int] = {}
    for record in serialized:
        count = int(record["count"])
        if count > MAX_CARD_COPIES:
            raise ValueError(
                f"卡牌 {record['card_id']} 数量为 {count}，单卡最多 {MAX_CARD_COPIES} 张"
            )
        base_id = str(record["card_id"]).split("@", 1)[0]
        copy_groups[base_id] = copy_groups.get(base_id, 0) + count
        if copy_groups[base_id] > MAX_CARD_COPIES:
            raise ValueError(
                f"卡牌 {base_id} 及其异画合计超过 {MAX_CARD_COPIES} 张上限"
            )
    total = sum(int(record["count"]) for record in serialized)
    if total > MAX_DECK_SIZE:
        raise ValueError(f"卡组共有 {total} 张，最多允许 {MAX_DECK_SIZE} 张")
    return serialized


def normalize_derived_card_records(cards: Iterable[Any]) -> List[Dict[str, str]]:
    """将衍生物卡牌规范为不含数量的唯一 ``card_id`` 记录。"""

    records: List[Dict[str, str]] = []
    seen = set()
    for item in list(cards or []):
        if isinstance(item, dict):
            reference = (
                item.get("card_id")
                or item.get("card_ref")
                or item.get("file")
                or item.get("filename")
            )
        else:
            reference = item
        ref = _card_ref_from_value(reference)
        key = ref.casefold()
        if not ref or is_evo_card_name(ref) or key in seen:
            continue
        seen.add(key)
        records.append({"card_id": ref})
    return records


def serialize_derived_card_records(
    cards: Iterable[Any],
    *,
    resource_root: Optional[str] = None,
) -> List[Dict[str, str]]:
    """把衍生物解析成稳定卡牌 ID；衍生物不受数量和总张数限制。"""

    from src.ui.card_catalog import (
        get_card_resource_root,
        load_card_catalog,
        resolve_card_entry,
    )

    resolved_root = resource_root or get_card_resource_root()
    catalog = load_card_catalog(resolved_root)
    serialized: List[Dict[str, str]] = []
    seen = set()
    for record in normalize_derived_card_records(cards):
        reference = str(record.get("card_id") or "")
        entry = resolve_card_entry(reference, catalog, resolved_root)
        if entry is None:
            raise ValueError(f"无法解析衍生物卡牌引用: {reference}")
        card_id = str(entry.card_id)
        key = card_id.casefold()
        if key in seen:
            continue
        seen.add(key)
        serialized.append({"card_id": card_id})
    return serialized


def normalize_deck_cards(cards: List[Any]) -> List[str]:
    """将持久化卡牌规范为不带扩展名的引用。"""

    return [
        str(record["card_id"])
        for record in normalize_deck_card_records(cards)
    ]


def filter_non_evo_cards(cards: List[Any]) -> List[str]:
    """返回移除 ``_evo`` 进化变体后的卡牌引用或文件名。"""

    return [
        str(record["card_id"])
        for record in normalize_deck_card_records(cards)
    ]


def extract_deck_strategy_config(deck_data: Any) -> Dict[str, Any]:
    """从当前或旧版卡组数据中读取可迁移的策略配置。"""

    if not isinstance(deck_data, dict):
        return {}

    strategy_config = deck_data.get("strategy_config")
    if isinstance(strategy_config, dict):
        return copy.deepcopy(strategy_config)

    legacy_config = deck_data.get("config")
    if isinstance(legacy_config, dict):
        return extract_strategy_config(
            legacy_config,
            cards=list(deck_data.get("cards") or []),
        )
    return {}


def build_card_variant_index(source_dir: str) -> Dict[Tuple[int, str], Dict[str, List[str]]]:
    """为 ``source_dir`` 下的基础与进化变体建立查询索引。"""

    out: Dict[Tuple[int, str], Dict[str, List[str]]] = {}
    if not os.path.isdir(source_dir):
        return out

    for root, _dirs, files in os.walk(source_dir):
        for fn in files:
            base = os.path.basename(str(fn or ""))
            if not base.lower().endswith(SUPPORTED_CARD_IMAGE_EXTENSIONS):
                continue

            full = os.path.join(root, base)
            try:
                cost, _enhance, parsed_name = parse_card_filename(base)
            except Exception:
                continue

            normalized_name = normalize_card_base_name(str(parsed_name or ""))
            if not normalized_name:
                continue

            key = (int(cost or 0), str(normalized_name))
            row = out.setdefault(key, {"base": [], "evo": []})
            if is_evo_card_name(base):
                row["evo"].append(full)
            else:
                row["base"].append(full)

    return out


def build_card_source_index(source_dir: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """为源目录中的卡牌建立完整文件名和主文件名索引。"""

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

    # v4 卡组只保存 card_id，因此索引还需支持直接按稳定 ID 查找图片。
    try:
        from src.ui.card_catalog import load_card_catalog

        for entry in load_card_catalog(source_dir):
            card_id_key = str(entry.card_id or "").casefold()
            if card_id_key:
                exact.setdefault(card_id_key, entry.source_path)
                stem.setdefault(card_id_key, entry.source_path)
    except Exception:
        pass

    return exact, stem


def resolve_source_card_path(
    source_dir: str,
    card_ref: str,
    *,
    exact_index: Optional[Dict[str, str]] = None,
    stem_index: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """将卡牌引用解析为实际源图片路径。

    同时支持带扩展名的旧文件引用和只含主文件名的新引用。
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


def resolve_runtime_card_paths(
    source_dir: str,
    card_ref: str,
    *,
    exact_index: Optional[Dict[str, str]] = None,
    stem_index: Optional[Dict[str, str]] = None,
    variant_index: Optional[Dict[Tuple[int, str], Dict[str, List[str]]]] = None,
) -> List[str]:
    """解析运行时模板，包括基础图及配套的 ``_evo`` 进化图。"""

    resolved = resolve_source_card_path(
        source_dir,
        card_ref,
        exact_index=exact_index,
        stem_index=stem_index,
    )
    if not resolved:
        return []

    picked_base = resolved
    try:
        cost, _enhance, parsed_name = parse_card_filename(os.path.basename(resolved))
        normalized_name = normalize_card_base_name(str(parsed_name or ""))
    except Exception:
        cost, normalized_name = 0, ""

    out: List[str] = []
    seen = set()

    def _append(path: str) -> None:
        p = str(path or "")
        if not p:
            return
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            return
        seen.add(key)
        out.append(p)

    if normalized_name:
        index = variant_index if isinstance(variant_index, dict) else build_card_variant_index(source_dir)
        row = index.get((int(cost or 0), str(normalized_name)), {}) if isinstance(index, dict) else {}
        base_candidates = [
            p for p in list((row.get("base") if isinstance(row, dict) else []) or []) if isinstance(p, str)
        ]
        evo_candidates = [
            p for p in list((row.get("evo") if isinstance(row, dict) else []) or []) if isinstance(p, str)
        ]

        if base_candidates:
            normalized_resolved = os.path.normcase(os.path.abspath(resolved))
            exact_base = None
            for p in base_candidates:
                if os.path.normcase(os.path.abspath(p)) == normalized_resolved:
                    exact_base = p
                    break
            picked_base = exact_base or sorted(base_candidates)[0]

        _append(picked_base)
        for p in sorted(evo_candidates):
            _append(p)
        return out

    _append(picked_base)
    return out


def _deck_base_names(cards: List[Any]) -> List[str]:
    names: List[str] = []
    for record in normalize_deck_card_records(cards):
        fn = str(record.get("card_id") or "")
        try:
            _base_cost, _enh, name = parse_card_filename(fn)
        except Exception:
            name = ""
        name = normalize_card_base_name(str(name or "").strip())
        if name and name not in names:
            names.append(name)
    return names


def extract_strategy_config(
    cfg: Dict[str, Any], *, cards: List[Any]
) -> Dict[str, Any]:
    """提取指定卡组可迁移的配置子集。

    有意排除设备与 ADB 设置、界面与运行时标记，以及其他机器相关配置。
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
    """将 ``strategy_config`` 应用到现有配置并替换对应区段。"""

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

    # 同时兼容以下两种结构：
    # 完整策略结构：{"strategy": {"effects": {...}}}
    # 仅包含效果的结构：{"effects": {...}}
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
    cards: List[Any],
    derived_cards: Optional[List[Any]] = None,
    decks_dir: str,
    config_path: Optional[str] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
) -> str:
    """保存卡组快照 JSON，并返回文件路径。"""

    name = (deck_name or "").strip()
    if not name:
        raise ValueError("deck_name is empty")

    os.makedirs(decks_dir, exist_ok=True)

    normalized_cards = serialize_deck_card_records(list(cards or []))
    normalized_derived_cards = serialize_derived_card_records(
        list(derived_cards or [])
    )

    deck_data: Dict[str, Any] = {
        "version": DECK_SCHEMA_VERSION,
        "name": name,
        "cards": list(normalized_cards or []),
        "derived_cards": list(normalized_derived_cards or []),
        "timestamp": int(time.time()),
    }

    if isinstance(strategy_config, dict):
        deck_data["strategy_config"] = copy.deepcopy(strategy_config)
    elif config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            sc = extract_strategy_config(cfg, cards=list(normalized_cards or []))
            if sc:
                deck_data["strategy_config"] = sc

    deck_file = os.path.join(decks_dir, f"{name}.json")
    write_json_atomic(deck_file, deck_data, ensure_ascii=False, indent=2)
    return deck_file
