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
