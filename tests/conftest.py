"""Load real NoneBot with temporary storage and no production configuration."""

import os
from importlib import import_module

import nonebot
from nonebot.adapters.onebot.v11 import Adapter
import pytest


@pytest.fixture(scope="session", autouse=True)
def init_plugin(tmp_path_factory):
    storage = tmp_path_factory.mktemp("bilibili-storage")
    nonebot.init(
        driver="~fastapi",
        command_start={""},
        superusers={"10000"},
        localstore_data_dir=storage / "data",
        localstore_cache_dir=storage / "cache",
        localstore_config_dir=storage / "config",
        analysis_use_on_message=os.environ.get("BILI_TEST_ON_MESSAGE") == "1",
    )
    nonebot.get_driver().register_adapter(Adapter)
    plugin = nonebot.load_plugin("nonebot_plugin_analysis_bilibili")
    assert plugin is not None
    return plugin


@pytest.fixture
def analysis_module():
    return import_module("nonebot_plugin_analysis_bilibili.analysis_bilibili")


@pytest.fixture(autouse=True)
def reset_state(init_plugin, tmp_path, monkeypatch):
    from nonebot_plugin_analysis_bilibili import analysis_bilibili as analysis
    from nonebot_plugin_analysis_bilibili import card_parse_config as cards
    from nonebot_plugin_analysis_bilibili import wbi

    monkeypatch.setattr(analysis, "_cached_spi_cookies", {})
    monkeypatch.setattr(analysis, "analysis_stat", {})
    monkeypatch.setattr(wbi, "_wbi_cache", None)
    monkeypatch.setattr(wbi, "_ticket_cache", None)
    monkeypatch.setattr(cards, "DATA_PATH", tmp_path / "card_parse.json")
    monkeypatch.setattr(cards, "data", cards.build_default_data())
