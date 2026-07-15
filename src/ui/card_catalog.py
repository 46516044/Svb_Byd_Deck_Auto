"""Card catalog model backed by the external ``quanka`` resources."""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

from src.config.paths import get_app_root


CARD_CATEGORIES: Tuple[str, ...] = (
    "\u4e2d\u7acb",
    "\u5996\u7cbe",
    "\u7687\u5bb6",
    "\u6cd5\u5e08",
    "\u9f99\u65cf",
    "\u68a6\u9b47",
    "\u4e3b\u6559",
    "\u8d85\u8d8a\u8005",
)
SUPPORTED_IMAGE_EXTENSIONS: Tuple[str, ...] = (
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
)

_CARD_FILENAME_RE = re.compile(
    r"^(?P<cost>\d+(?:@\d+)*)_"
    r"(?P<card_id>\d{8}(?:@\d+)?)"
    r"(?:(?:_(?P<atk>\d+)_(?P<hp>\d+))|(?:_evo))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CardEntry:
    """One selectable, non-evolved card image in the catalog."""

    key: str
    card_id: str
    cost: int
    enhance_costs: Tuple[int, ...]
    name: str
    category: str
    source_path: str
    relative_path: str

    @property
    def filename(self) -> str:
        """Return the concrete source filename used by deck IO."""

        return os.path.basename(self.source_path)


def _looks_like_resource_root(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    if os.path.isfile(os.path.join(path, "SV_WB_Cards.csv")):
        return True
    return any(os.path.isdir(os.path.join(path, category)) for category in CARD_CATEGORIES)


def get_card_resource_root(app_root: Optional[str] = None) -> str:
    """Return the card resource root for source and packaged runs.

    The current submodule layout is ``quanka/SV_WB_Cards``. Older releases
    placed the CSV and category directories directly under ``quanka``; that
    location is used only when the current layout is absent.
    """

    root = os.path.abspath(app_root or get_app_root())
    current = os.path.join(root, "quanka", "SV_WB_Cards")
    if os.path.isdir(current):
        return current

    legacy = os.path.join(root, "quanka")
    if _looks_like_resource_root(legacy):
        return legacy
    return current


def _load_card_metadata(resource_root: str) -> Dict[str, Tuple[int, str]]:
    csv_path = os.path.join(resource_root, "SV_WB_Cards.csv")
    if not os.path.isfile(csv_path):
        return {}

    metadata: Dict[str, Tuple[int, str]] = {}
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                card_id = str(row.get("card_id") or "").strip()
                name = str(row.get("name") or "").strip()
                if not card_id:
                    continue
                try:
                    cost = int(str(row.get("cost") or "0").strip())
                except (TypeError, ValueError):
                    cost = 0
                metadata[card_id] = (cost, name or card_id)
    except (OSError, csv.Error, UnicodeError):
        return {}
    return metadata


def _category_sort_key(category: str) -> Tuple[int, str]:
    try:
        return CARD_CATEGORIES.index(category), ""
    except ValueError:
        return len(CARD_CATEGORIES), category.casefold()


def load_card_catalog(resource_root: Optional[str] = None) -> List[CardEntry]:
    """Read metadata and return all selectable, non-evolved card images."""

    root = os.path.abspath(resource_root or get_card_resource_root())
    if not os.path.isdir(root):
        return []

    metadata = _load_card_metadata(root)
    entries: List[CardEntry] = []

    try:
        category_names = [
            item.name
            for item in os.scandir(root)
            if item.is_dir(follow_symlinks=False)
        ]
    except OSError:
        return []

    category_names.sort(key=_category_sort_key)
    for category in category_names:
        category_path = os.path.join(root, category)
        try:
            files = sorted(os.scandir(category_path), key=lambda item: item.name.casefold())
        except OSError:
            continue

        for item in files:
            if not item.is_file(follow_symlinks=False):
                continue
            stem, extension = os.path.splitext(item.name)
            if extension.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            if stem.lower().endswith("_evo"):
                continue

            match = _CARD_FILENAME_RE.fullmatch(stem)
            if match is None:
                continue

            cost_parts = tuple(int(part) for part in match.group("cost").split("@"))
            filename_cost = cost_parts[0]
            enhance_costs = tuple(
                sorted({cost for cost in cost_parts[1:] if cost > filename_cost})
            )
            card_id = match.group("card_id")
            csv_cost, name = metadata.get(
                card_id,
                metadata.get(card_id.split("@", 1)[0], (filename_cost, card_id)),
            )
            relative_path = os.path.relpath(item.path, root).replace(os.sep, "/")
            entries.append(
                CardEntry(
                    key=f"{category}/{card_id}",
                    card_id=card_id,
                    cost=csv_cost,
                    enhance_costs=enhance_costs,
                    name=name,
                    category=category,
                    source_path=os.path.abspath(item.path),
                    relative_path=relative_path,
                )
            )

    entries.sort(
        key=lambda entry: (
            _category_sort_key(entry.category),
            entry.cost,
            entry.name.casefold(),
            entry.card_id.casefold(),
            entry.relative_path.casefold(),
        )
    )
    return entries


def _reference_forms(reference: str) -> Tuple[str, str, str, str]:
    raw = str(reference or "").strip()
    slash_path = raw.replace("\\", "/").strip("/")
    basename = slash_path.rsplit("/", 1)[-1]
    stem = os.path.splitext(basename)[0]
    return raw, slash_path.casefold(), basename.casefold(), stem.casefold()


def resolve_card_entry(
    reference: Union[str, CardEntry],
    catalog: Optional[Iterable[CardEntry]] = None,
    resource_root: Optional[str] = None,
) -> Optional[CardEntry]:
    """Resolve a persisted/UI card reference to one catalog entry.

    Stable keys, relative paths, absolute source paths, filenames, filename
    stems, and card IDs are accepted. Ambiguous display names are deliberately
    not used as references.
    """

    if isinstance(reference, CardEntry):
        return reference

    raw, slash_path, basename, stem = _reference_forms(reference)
    if not raw:
        return None

    entries = list(catalog) if catalog is not None else load_card_catalog(resource_root)
    normalized_absolute = os.path.normcase(os.path.abspath(raw))

    for entry in entries:
        if slash_path in (entry.key.casefold(), entry.relative_path.casefold()):
            return entry
        if normalized_absolute == os.path.normcase(os.path.abspath(entry.source_path)):
            return entry

    filename_matches = [
        entry
        for entry in entries
        if basename == entry.filename.casefold()
        or stem == os.path.splitext(entry.filename)[0].casefold()
    ]
    if len(filename_matches) == 1:
        return filename_matches[0]

    card_id_matches = [entry for entry in entries if slash_path == entry.card_id.casefold()]
    if len(card_id_matches) == 1:
        return card_id_matches[0]
    return None
