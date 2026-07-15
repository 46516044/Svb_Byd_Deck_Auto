from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.card_catalog import load_card_catalog
from src.utils.card_filename import (
    normalize_card_base_name,
    parse_card_filename,
    parse_follower_stat_suffix,
)


IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}
TREASURE_MARKER = "\uff08\u73cd\u85cf\uff09"
MAX_VISUAL_DISTANCE = 5
ENCODED_FILENAME_RE = re.compile(
    r"^(?P<cost>\d+(?:@\d+)*)_"
    r"(?P<card_id>\d{8}(?:@\d+)?)"
    r"(?:(?:_(?P<atk>\d+)_(?P<hp>\d+))|(?:_evo))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MetadataRow:
    card_id: str
    cost: int
    name: str


@dataclass(frozen=True)
class EncodedImage:
    category: str
    cost: int
    card_id: str
    path: Path
    fingerprint: int


@dataclass(frozen=True)
class LegacyImage:
    category: str
    cost: int
    enhance_costs: tuple[int, ...]
    name: str
    path: Path
    fingerprint: int

    @property
    def group_key(self) -> tuple[str, int, tuple[int, ...], str]:
        return self.category, self.cost, self.enhance_costs, self.name


def _image_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _fingerprint(path: Path, size: int = 16) -> int:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        grayscale = Image.alpha_composite(background, rgba).convert("L")
        resized = grayscale.resize((size + 1, size), Image.Resampling.BILINEAR)
        pixels = list(resized.getdata())

    value = 0
    for y in range(size):
        row = y * (size + 1)
        for x in range(size):
            value = (value << 1) | (pixels[row + x] > pixels[row + x + 1])
    return value


def _fingerprints(paths: Iterable[Path]) -> dict[Path, int]:
    items = list(paths)
    workers = min(12, max(1, (os.cpu_count() or 1) + 2))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(items, pool.map(_fingerprint, items)))


def _load_metadata(csv_path: Path) -> list[MetadataRow]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [
            MetadataRow(
                card_id=str(row.get("card_id") or "").strip(),
                cost=int(str(row.get("cost") or "0").strip()),
                name=str(row.get("name") or "").strip(),
            )
            for row in csv.DictReader(stream)
            if str(row.get("card_id") or "").strip()
        ]


def _load_encoded_images(root: Path, fingerprints: dict[Path, int]) -> list[EncodedImage]:
    result: list[EncodedImage] = []
    for path in fingerprints:
        if path.stem.lower().endswith("_evo"):
            continue
        match = ENCODED_FILENAME_RE.fullmatch(path.stem)
        if match is None:
            continue
        result.append(
            EncodedImage(
                category=path.parent.name,
                cost=int(match.group("cost").split("@", 1)[0]),
                card_id=match.group("card_id"),
                path=path,
                fingerprint=fingerprints[path],
            )
        )
    return result


def _load_legacy_images(root: Path, fingerprints: dict[Path, int]) -> list[LegacyImage]:
    result: list[LegacyImage] = []
    for path in fingerprints:
        if path.stem.lower().endswith("_evo"):
            continue
        cost, enhance_costs, parsed_name = parse_card_filename(path.name)
        result.append(
            LegacyImage(
                category=path.parent.name,
                cost=cost,
                enhance_costs=tuple(enhance_costs),
                name=normalize_card_base_name(parsed_name),
                path=path,
                fingerprint=fingerprints[path],
            )
        )
    return result


def _legacy_evolved_images(root: Path) -> dict[tuple[str, int, tuple[int, ...], str], Path]:
    result: dict[tuple[str, int, tuple[int, ...], str], Path] = {}
    for path in _image_files(root):
        if not path.stem.lower().endswith("_evo"):
            continue
        cost, enhance_costs, parsed_name = parse_card_filename(path.name)
        key = (
            path.parent.name,
            cost,
            tuple(enhance_costs),
            normalize_card_base_name(parsed_name),
        )
        result.setdefault(key, path)
    return result


def _copy_image(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == destination.suffix.lower():
        shutil.copy2(source, destination)
        return

    format_by_extension = {
        ".webp": "WEBP",
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
    }
    with Image.open(source) as image:
        image.save(destination, format=format_by_extension[destination.suffix.lower()], quality=95)


def _encoded_evo_name(reference: EncodedImage) -> str:
    match = ENCODED_FILENAME_RE.fullmatch(reference.path.stem)
    if match is None:
        raise ValueError(f"Invalid encoded filename: {reference.path.name}")
    return f"{match.group('cost')}_{reference.card_id}_evo{reference.path.suffix.lower()}"


def _next_style_id(base_id: str, rows: Iterable[MetadataRow]) -> str:
    used = []
    prefix = f"{base_id}@"
    for row in rows:
        if row.card_id.startswith(prefix):
            suffix = row.card_id[len(prefix) :]
            if suffix.isdigit():
                used.append(int(suffix))
    return f"{base_id}@{max(used, default=0) + 1}"


def _treasure_filename(card: LegacyImage, card_id: str, current_cost: int) -> str:
    _, _, parsed_name = parse_card_filename(card.path.name)
    _, atk, hp = parse_follower_stat_suffix(parsed_name)
    enhance_costs = tuple(value for value in card.enhance_costs if value > current_cost)
    costs = "@".join(str(value) for value in (current_cost, *enhance_costs))
    stats = f"_{atk}_{hp}" if atk is not None and hp is not None else ""
    return f"{costs}_{card_id}{stats}.webp"


def _write_metadata(csv_path: Path, rows: Iterable[MetadataRow]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["card_id", "cost", "name"])
        for row in rows:
            writer.writerow([row.card_id, row.cost, row.name])


def _normalize_treasure_costs(root: Path, rows: list[MetadataRow]) -> list[MetadataRow]:
    rows_by_id = {row.card_id: row for row in rows}
    normalized: list[MetadataRow] = []
    for row in rows:
        base_id = row.card_id.split("@", 1)[0]
        base = rows_by_id.get(base_id)
        if TREASURE_MARKER not in row.name or base is None:
            normalized.append(row)
            continue

        normalized.append(MetadataRow(row.card_id, base.cost, row.name))
        for path in _image_files(root):
            match = ENCODED_FILENAME_RE.fullmatch(path.stem)
            if match is None or match.group("card_id") != row.card_id:
                continue
            cost_parts = [int(value) for value in match.group("cost").split("@")]
            corrected_costs = [base.cost, *(value for value in cost_parts[1:] if value > base.cost)]
            corrected_prefix = "@".join(str(value) for value in corrected_costs)
            if corrected_prefix == match.group("cost"):
                continue
            destination = path.with_name(
                f"{corrected_prefix}{path.name[len(match.group('cost')):]}"
            )
            if destination.exists():
                raise RuntimeError(f"Treasure cost correction would overwrite {destination}.")
            path.rename(destination)
    return normalized


def _validate_generated(root: Path, expected_rows: int) -> None:
    catalog = load_card_catalog(str(root))
    if len(catalog) != expected_rows:
        raise RuntimeError(
            f"Generated catalog has {len(catalog)} entries; expected {expected_rows}."
        )
    if len({entry.key for entry in catalog}) != len(catalog):
        raise RuntimeError("Generated catalog contains duplicate category/card_id keys.")
    if any(not Path(entry.source_path).is_file() for entry in catalog):
        raise RuntimeError("Generated catalog references a missing image.")


def encode_catalog(project_root: Path) -> dict[str, object]:
    quanka_root = (project_root / "quanka").resolve()
    legacy_root = (quanka_root / "quanka").resolve()
    current_root = (quanka_root / "SV_WB_Cards").resolve()
    staging_root = (quanka_root / ".SV_WB_Cards.generated").resolve()
    backup_root = (quanka_root / ".SV_WB_Cards.backup").resolve()

    for path in (legacy_root, current_root, staging_root, backup_root):
        if path.parent != quanka_root:
            raise RuntimeError(f"Refusing to operate outside {quanka_root}: {path}")
    if not legacy_root.is_dir():
        raise FileNotFoundError(legacy_root)
    if not (current_root / "SV_WB_Cards.csv").is_file():
        raise FileNotFoundError(current_root / "SV_WB_Cards.csv")
    if staging_root.exists() or backup_root.exists():
        raise RuntimeError("A previous staging/backup directory exists; inspect it first.")

    rows = _load_metadata(current_root / "SV_WB_Cards.csv")
    rows_by_id = {row.card_id: row for row in rows}
    base_rows_by_name: dict[str, list[MetadataRow]] = defaultdict(list)
    for row in rows:
        if "@" not in row.card_id:
            base_rows_by_name[row.name].append(row)

    legacy_paths = _image_files(legacy_root)
    current_paths = _image_files(current_root)
    legacy_fingerprints = _fingerprints(legacy_paths)
    current_fingerprints = _fingerprints(current_paths)
    legacy_images = _load_legacy_images(legacy_root, legacy_fingerprints)
    encoded_images = _load_encoded_images(current_root, current_fingerprints)
    evolved_by_key = _legacy_evolved_images(legacy_root)

    encoded_by_category_cost: dict[tuple[str, int], list[EncodedImage]] = defaultdict(list)
    for image in encoded_images:
        encoded_by_category_cost[(image.category, image.cost)].append(image)

    matched: list[tuple[LegacyImage, EncodedImage]] = []
    unmatched: list[LegacyImage] = []
    for legacy in legacy_images:
        candidates = encoded_by_category_cost[(legacy.category, legacy.cost)]
        visual_matches = [
            (
                (candidate.fingerprint ^ legacy.fingerprint).bit_count(),
                candidate,
            )
            for candidate in candidates
            if (candidate.fingerprint ^ legacy.fingerprint).bit_count()
            <= MAX_VISUAL_DISTANCE
        ]
        if not visual_matches:
            unmatched.append(legacy)
            continue

        visual_matches.sort(
            key=lambda item: (
                item[0],
                rows_by_id.get(item[1].card_id, MetadataRow("", 0, "")).name
                != legacy.name,
                item[1].card_id,
            )
        )
        matched.append((legacy, visual_matches[0][1]))

    treasures = [card for card in unmatched if TREASURE_MARKER in card.name]
    stale = [card for card in unmatched if TREASURE_MARKER not in card.name]

    shutil.copytree(current_root, staging_root)
    for legacy, reference in matched:
        target = staging_root / reference.category / reference.path.name
        _copy_image(legacy.path, target)
        evolved = evolved_by_key.get(legacy.group_key)
        if evolved is not None:
            _copy_image(
                evolved,
                staging_root / reference.category / _encoded_evo_name(reference),
            )

    additions: list[MetadataRow] = []
    for treasure in sorted(
        treasures,
        key=lambda card: (card.category, card.cost, card.name, card.path.name),
    ):
        base_name = treasure.name.replace(TREASURE_MARKER, "").strip()
        candidates = base_rows_by_name.get(base_name, [])
        if len(candidates) != 1:
            raise RuntimeError(
                f"Cannot uniquely map treasure card {treasure.path.name!r} to a base ID."
            )
        card_id = _next_style_id(candidates[0].card_id, [*rows, *additions])
        current_cost = candidates[0].cost
        target = staging_root / treasure.category / _treasure_filename(
            treasure,
            card_id,
            current_cost,
        )
        _copy_image(treasure.path, target)
        additions.append(MetadataRow(card_id=card_id, cost=current_cost, name=treasure.name))

    generated_rows = _normalize_treasure_costs(staging_root, [*rows, *additions])
    _write_metadata(staging_root / "SV_WB_Cards.csv", generated_rows)
    _validate_generated(staging_root, len(generated_rows))

    renamed_current = False
    try:
        current_root.rename(backup_root)
        renamed_current = True
    except PermissionError:
        # Qt 图片读取器或资源管理器缩略图可能短暂占用目录句柄；此时退回到
        # 已通过完整校验的暂存目录，执行就地覆盖。
        shutil.copytree(staging_root, current_root, dirs_exist_ok=True)
        shutil.rmtree(staging_root)

    if renamed_current:
        try:
            staging_root.rename(current_root)
        except Exception:
            backup_root.rename(current_root)
            raise
        shutil.rmtree(backup_root)

    return {
        "matched_legacy_cards": len(matched),
        "added_treasure_cards": len(additions),
        "excluded_stale_cards": [card.path.name for card in stale],
        "catalog_entries": len(generated_rows),
        "catalog_images": len(_image_files(current_root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encode a legacy name-based quanka directory into the ID-based catalog."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root (defaults to the parent of this script directory).",
    )
    args = parser.parse_args()
    report = encode_catalog(args.project_root.resolve())
    print(f"Matched legacy cards: {report['matched_legacy_cards']}")
    print(f"Added treasure cards: {report['added_treasure_cards']}")
    print(f"Catalog entries: {report['catalog_entries']}")
    print(f"Catalog images: {report['catalog_images']}")
    print("Excluded stale cards:")
    for name in report["excluded_stale_cards"]:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
