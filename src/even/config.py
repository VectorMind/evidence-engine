"""Runtime access to repository configuration contracts."""

from __future__ import annotations

from typing import Any

import yaml

from even.contracts import read_contract_text


def load_parser_config() -> dict[str, Any]:
    """Load parser defaults from config/parser.yaml."""

    return yaml.safe_load(read_contract_text("config/parser.yaml"))


def load_embedding_config() -> dict[str, Any]:
    """Load embedding profiles from config/embeddings.yaml."""

    return yaml.safe_load(read_contract_text("config/embeddings.yaml"))


def load_routing_config() -> dict[str, Any]:
    """Load global routing defaults from config/routing.yaml."""

    return yaml.safe_load(read_contract_text("config/routing.yaml"))


def embedding_profile(name: str) -> dict[str, Any] | None:
    config = load_embedding_config()
    for profile in config.get("profiles", []):
        if profile.get("name") == name:
            return profile
    return None
