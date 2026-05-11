from belote.belatro.progression.save import Profile, SaveManager


def test_unlock_vs_discovery():
    """Verify that unlocking an item does NOT automatically discover it."""
    profile = Profile()
    profile.unlocked_ids = []
    profile.discovered_items = []

    # Unlock an item
    newly_unlocked = profile.unlock("test_item")

    assert newly_unlocked is True
    assert "test_item" in profile.unlocked_ids
    assert "test_item" not in profile.discovered_items  # Should NOT be discovered

def test_manual_discovery():
    """Verify that manual discovery works as expected."""
    profile = Profile()
    profile.discovered_items = []

    profile.discover("test_item")
    assert "test_item" in profile.discovered_items

def test_profile_persistence(tmp_path):
    """Verify profile saving and loading with discovered items."""
    # Custom SaveManager to use tmp_path
    save_manager = SaveManager()
    save_manager._save_path = tmp_path / "profile.json"

    profile = Profile()
    profile.discover("joker_1")
    save_manager.save_profile(profile)

    loaded_profile = save_manager.load_profile()
    assert "joker_1" in loaded_profile.discovered_items


def test_load_profile_missing_unlocked_ids_uses_defaults(tmp_path):
    """H5 regression: a saved profile missing `unlocked_ids` (legacy save,
    manual edit, partial write) must reload with the Profile dataclass
    default starter unlocks — not an empty list."""
    import json

    save_manager = SaveManager()
    save_manager._save_path = tmp_path / "profile.json"
    # Write a save with unlocked_ids omitted entirely.
    save_manager._save_path.write_text(json.dumps({
        "schema_version": 1,
        "discovered_items": ["some_joker"],
        "stats": {"runs_won": 3},
    }))

    loaded = save_manager.load_profile()
    assert loaded.unlocked_ids == ["le_classique", "le_courageux", "l_econome"]
    # Sanity: the other fields read normally.
    assert loaded.discovered_items == ["some_joker"]
    assert loaded.stats["runs_won"] == 3


def test_load_profile_explicit_empty_unlocked_ids_stays_empty(tmp_path):
    """When unlocked_ids is explicitly present but empty (a player who has
    locked themselves out), we honour the data — only a MISSING key triggers
    the default fallback."""
    import json

    save_manager = SaveManager()
    save_manager._save_path = tmp_path / "profile.json"
    save_manager._save_path.write_text(json.dumps({
        "schema_version": 1,
        "unlocked_ids": [],
        "discovered_items": [],
        "stats": {},
    }))

    loaded = save_manager.load_profile()
    assert loaded.unlocked_ids == []
