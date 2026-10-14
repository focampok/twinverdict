import pytest

from search.config import PROFILES, SearchConfig


def test_default_profile_uses_sustained_k() -> None:
    config = SearchConfig()
    assert config.profile == "default"
    assert (config.N, config.K, config.R) == (48, 180, 8)
    assert config.K == PROFILES["default"]["K"]


def test_final_profile_is_the_long_run() -> None:
    config = SearchConfig.from_profile("final")
    assert config.profile == "final"
    assert (config.N, config.K, config.R) == (48, 300, 8)


def test_smoke_profile_is_the_test_size() -> None:
    config = SearchConfig.from_profile("smoke")
    assert config.profile == "smoke"
    assert (config.N, config.K, config.R, config.TOP_K) == (2, 2, 2, 2)
    assert config.HOLDOUT_SEEDS == 0


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="perfil desconocido"):
        SearchConfig.from_profile("no-existe")
