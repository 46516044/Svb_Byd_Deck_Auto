"""Profiles (DeckProfile / StrategyProfile).

This is a minimal foundation:
- represent 'what deck' and 'what strategy' are currently active
- provide a consistent loggable summary

Future steps can extend this to support loading/merging external profile files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DeckProfile:
    name: str = "inline"
    source: str = "config.json"


@dataclass(frozen=True)
class StrategyProfile:
    name: str = "inline"
    source: str = "config.json"


def get_active_deck_profile(config: Dict[str, Any]) -> DeckProfile:
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return DeckProfile()
    deck = profiles.get("deck", {})
    if not isinstance(deck, dict):
        return DeckProfile()
    name = deck.get("name")
    source = deck.get("source") or deck.get("file")
    if isinstance(name, str) and name.strip():
        return DeckProfile(name=name.strip(), source=str(source or "config.json"))
    return DeckProfile()


def get_active_strategy_profile(config: Dict[str, Any]) -> StrategyProfile:
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return StrategyProfile()
    strat = profiles.get("strategy", {})
    if not isinstance(strat, dict):
        return StrategyProfile()
    name = strat.get("name")
    source = strat.get("source") or strat.get("file")
    if isinstance(name, str) and name.strip():
        return StrategyProfile(name=name.strip(), source=str(source or "config.json"))
    return StrategyProfile()


def format_profile_summary(deck: DeckProfile, strategy: StrategyProfile) -> str:
    return (
        f"deck={deck.name}({deck.source}) "
        f"strategy={strategy.name}({strategy.source})"
    )
