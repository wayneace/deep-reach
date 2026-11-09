import pytest


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep cooldowns, health and pacing out of the user's real state file."""
    monkeypatch.setenv("DEEP_REACH_STATE_FILE", str(tmp_path / "state.json"))
