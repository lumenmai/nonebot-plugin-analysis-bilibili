import json
from pathlib import Path
from typing import Any

from nonebot import logger, require

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

DATA_PATH: Path = store.get_plugin_data_file("card_parse.json")

data: dict[str, Any] = {}


def build_default_data() -> dict[str, Any]:
    return {"global_enabled": False, "enabled_groups": []}


def normalize_data(config: dict[str, Any]) -> bool:
    migrated = False

    if not isinstance(config.get("global_enabled"), bool):
        config["global_enabled"] = False
        migrated = True

    groups = config.get("enabled_groups")
    if not isinstance(groups, list):
        config["enabled_groups"] = []
        migrated = True
    else:
        normalized_groups = []
        for group_id in groups:
            group_id = str(group_id)
            if group_id not in normalized_groups:
                normalized_groups.append(group_id)
        if normalized_groups != groups:
            config["enabled_groups"] = normalized_groups
            migrated = True

    return migrated


def load_data() -> dict[str, Any]:
    global data
    try:
        if DATA_PATH.exists():
            with DATA_PATH.open("r", encoding="utf-8") as f:
                loaded_data = json.load(f)
            data = (
                loaded_data if isinstance(loaded_data, dict) else build_default_data()
            )
        else:
            data = build_default_data()
            save_data()

        if normalize_data(data):
            save_data()
    except Exception as e:
        data = build_default_data()
        logger.error(f"加载B站卡片解析配置失败: {e}")
    return data


def save_data() -> None:
    try:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DATA_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"保存B站卡片解析配置失败: {e}")


def get_data() -> dict[str, Any]:
    if not data:
        load_data()
    return data


def is_global_card_parse_enabled() -> bool:
    return bool(get_data().get("global_enabled", False))


def set_global_card_parse(enabled: bool) -> None:
    config = get_data()
    config["global_enabled"] = enabled
    save_data()


def is_group_card_parse_enabled(group_id: str) -> bool:
    group_id = str(group_id)
    groups = get_data().get("enabled_groups", [])
    return group_id in groups


def set_group_card_parse(group_id: str, enabled: bool) -> None:
    group_id = str(group_id)
    config = get_data()
    groups = config.setdefault("enabled_groups", [])
    if enabled and group_id not in groups:
        groups.append(group_id)
    elif not enabled and group_id in groups:
        groups.remove(group_id)
    save_data()


def can_parse_card(group_id: str | None) -> bool:
    return (
        bool(group_id)
        and is_global_card_parse_enabled()
        and is_group_card_parse_enabled(group_id)
    )


load_data()
