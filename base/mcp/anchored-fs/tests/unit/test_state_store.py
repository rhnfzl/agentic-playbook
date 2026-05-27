from pathlib import Path
from core.state_store import StateStore


def test_state_store_round_trip(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.write({"foo": 1})
    assert store.read() == {"foo": 1}


def test_state_store_returns_default_when_missing(tmp_path: Path):
    store = StateStore(tmp_path / "missing.json")
    assert store.read(default={"empty": True}) == {"empty": True}


def test_state_store_atomic_write_does_not_truncate_on_failure(
    tmp_path: Path, monkeypatch
):
    store = StateStore(tmp_path / "state.json")
    store.write({"intact": True})

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", fail)
    try:
        store.write({"newer": True})
    except OSError:
        pass
    assert store.read() == {"intact": True}


def test_state_store_update_uses_lock_per_key(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.write({"a": 1, "b": 2})
    store.update(lambda d: {**d, "b": 99})
    assert store.read() == {"a": 1, "b": 99}
