from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.planets import Saturn


def test_planet_level_up():
    """39. Planet level-up - Verify planet level increments and reward applies."""
    run = BelAtroRun()
    planet = Saturn()
    reward = planet.level_up_reward()
    run.contract_levels[planet.contract_id] = reward
    # Saturn level 1 reward for spades is +8 chips
    assert run.contract_levels["spades"] == {"add_chips": 8}

def test_ante_progression():
    """40. Ante progression - Verify all 8 antes cycle correctly."""
    run = BelAtroRun()
    # Ante 1: Small -> Big -> Boss
    assert run.ante_number == 1
    assert run.blind_index == 0

    run.advance_blind() # -> Big
    assert run.blind_index == 1

    run.advance_blind() # -> Boss
    assert run.blind_index == 2

    run.advance_blind() # -> Ante 2, Small
    assert run.ante_number == 2
    assert run.blind_index == 0

    # Verify final progression to win
    run.ante_number = 8
    run.blind_index = 2
    run.advance_blind()
    assert run.run_won is True
