"""Scripted flows through `belote.ui.prompts`: card / bid / coinche /
surcoinche prompts, the help, rules and history overlays."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from belote.deck import Card, Rank, Suit
from belote.game import (
    SANS_ATOUT_BID,
    GameState,
    Phase,
    RoundScore,
    Seat,
    TrickCard,
    legal_cards,
    new_game,
    sort_south_hand,
    start_round,
)
from belote.input import Key
from belote.themes import theme_manager
from belote.ui import prompts
from tests.harness import TUI, keys, raw_char

# ── fixtures ────────────────────────────────────────────────────────────────

_SOUTH_HAND = (
    Card(Suit.SPADES, Rank.SEVEN),
    Card(Suit.HEARTS, Rank.EIGHT),
    Card(Suit.CLUBS, Rank.KING),
    Card(Suit.HEARTS, Rank.ACE),
    Card(Suit.DIAMONDS, Rank.TEN),
    Card(Suit.HEARTS, Rank.NINE),
)


def _following_state() -> GameState:
    """South must follow hearts (West led the King): 3 legal of 6 cards."""
    base = start_round(new_game(), random.Random(3))
    other = tuple(c for c in base.hands[1] if c not in _SOUTH_HAND)[:6]
    hands = (_SOUTH_HAND, other, other, other)
    return replace(
        base,
        hands=hands,
        phase=Phase.PLAYING,
        trump=Suit.SPADES,
        contract="normal",
        taker=Seat.SOUTH,
        leader=Seat.WEST,
        turn=Seat.SOUTH,
        current_trick=(TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),),
    )


def _legal_sorted(state: GameState) -> tuple[list[Card], list[Card]]:
    s = sort_south_hand(state)
    hand = list(s.hand_of(Seat.SOUTH))
    legal = [c for c in hand if c in legal_cards(s, Seat.SOUTH)]
    return hand, legal


def _bidding_state(rnd: int = 1) -> GameState:
    state = start_round(new_game(), random.Random(0))
    return replace(state, bidding_round=rnd)


# ── prompt_card ─────────────────────────────────────────────────────────────


def test_prompt_card_enter_picks_first_legal_card(tui: TUI) -> None:
    state = _following_state()
    _, legal = _legal_sorted(state)
    card, new_state = prompts.prompt_card(state, tui.reader("enter").as_reader())
    assert card == legal[0]
    # The returned state carries the auto-sorted hand.
    assert list(new_state.hand_of(Seat.SOUTH)) == _legal_sorted(state)[0]


def test_prompt_card_navigation_skips_illegal_cards_and_clamps(tui: TUI) -> None:
    state = _following_state()
    _, legal = _legal_sorted(state)
    assert len(legal) == 3
    # LEFT at the first legal card stays put; RIGHT x5 clamps at the last legal.
    r = tui.reader("left", "up", "right", "right", "right", "down", "enter")
    card, _ = prompts.prompt_card(state, r.as_reader())
    assert card == legal[-1]
    # One step back from the end lands on the middle legal card.
    card, _ = prompts.prompt_card(state, tui.reader("right", "right", "left", "enter").as_reader())
    assert card == legal[1]


def test_prompt_card_digit_quick_select_only_accepts_legal(tui: TUI) -> None:
    state = _following_state()
    hand, legal = _legal_sorted(state)
    illegal_idx = next(i for i, c in enumerate(hand) if c not in legal)
    legal_idx = hand.index(legal[1])
    r = tui.reader(raw_char(str(illegal_idx + 1)), raw_char("9"), raw_char(str(legal_idx + 1)))
    card, _ = prompts.prompt_card(state, r.as_reader())
    assert card == legal[1]
    assert r.exhausted


def test_prompt_card_undo_quit_and_eof(tui: TUI) -> None:
    state = _following_state()
    assert prompts.prompt_card(state, tui.reader("z").as_reader())[0] == "UNDO"
    assert prompts.prompt_card(state, tui.reader("Z").as_reader())[0] == "UNDO"
    assert prompts.prompt_card(state, tui.reader("q").as_reader())[0] is None
    assert prompts.prompt_card(state, tui.reader("ctrl-c").as_reader())[0] is None
    # Empty script → EOF → treated as quit, after exactly one read.
    r = tui.reader()
    assert prompts.prompt_card(state, r.as_reader())[0] is None
    assert r.reads == 1


def test_prompt_card_ignores_unbound_keys(tui: TUI) -> None:
    state = _following_state()
    _, legal = _legal_sorted(state)
    r = tui.reader("unknown", "tab", "space", "esc", raw_char("m"), "overlay", "enter")
    card, _ = prompts.prompt_card(state, r.as_reader())
    assert card == legal[0]


def test_prompt_card_help_sort_theme_history_then_play(tui: TUI) -> None:
    state = _following_state()
    _, legal = _legal_sorted(state)
    before = theme_manager.current_name
    # ? → help (any key returns), o → sort, t → theme cycle, h → history.
    r = tui.reader("right", "?", "space", "o", "t", "h", "esc", "enter")
    card, _ = prompts.prompt_card(state, r.as_reader())
    # SORT keeps the selection on the same card.
    assert card == legal[1]
    assert theme_manager.current_name != before
    assert "KEYBOARD SHORTCUTS" in tui.text
    assert "GAME HISTORY" in tui.text


def test_prompt_card_after_display_hook_runs_every_frame(tui: TUI) -> None:
    state = _following_state()
    seen: list[GameState] = []
    prompts.prompt_card(
        state, tui.reader("right", "left", "enter").as_reader(), after_display=seen.append
    )
    assert len(seen) == 3


def test_prompt_card_extension_key_round_trip(tui: TUI) -> None:
    state = _following_state()
    prompts.register_extension_keys(Key.INVENTORY)
    try:
        res, _ = prompts.prompt_card(state, tui.reader("v").as_reader())
    finally:
        prompts.unregister_extension_keys(Key.INVENTORY)
    assert res == prompts.ExtensionKey(Key.INVENTORY)


def test_prompt_card_rejects_empty_hand(tui: TUI) -> None:
    state = replace(_following_state(), hands=((), (), (), ()))
    with pytest.raises(ValueError, match="No cards"):
        prompts.prompt_card(state, tui.reader().as_reader())


def test_prompt_card_paints_the_table(tui: TUI) -> None:
    prompts.prompt_card(_following_state(), tui.reader("enter").as_reader())
    # The frame shows South's cards: the 7 of the trump suit is in hand.
    assert "7" in tui.text and tui.screen.raw.count("\x1b[") > 10


# ── prompt_bid ──────────────────────────────────────────────────────────────


def test_prompt_bid_round1_take_and_pass(tui: TUI) -> None:
    state = _bidding_state(1)
    assert state.up_card is not None
    up = state.up_card.suit
    assert prompts.prompt_bid(state, tui.reader("enter").as_reader()) == up
    # Down → second option (pass), ENTER → None.
    assert prompts.prompt_bid(state, tui.reader("down", "enter").as_reader()) is None
    # Wraps: UP from 0 lands on the last option (pass).
    assert prompts.prompt_bid(state, tui.reader("up", "enter").as_reader()) is None
    assert prompts.prompt_bid(state, tui.reader("p").as_reader()) is None
    assert prompts.prompt_bid(state, tui.reader("1").as_reader()) == up


def test_prompt_bid_round1_ignores_round2_quick_keys(tui: TUI) -> None:
    state = _bidding_state(1)
    # x / n are TA / SA quick keys only in round 2; digit 7 is out of range.
    r = tui.reader("x", "n", "7", "p")
    assert prompts.prompt_bid(state, r.as_reader()) is None
    assert r.reads == 4


def test_prompt_bid_round2_options(tui: TUI) -> None:
    state = _bidding_state(2)
    assert state.up_card is not None
    others = [
        s for s in (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS) if s != state.up_card.suit
    ]
    assert prompts.prompt_bid(state, tui.reader("enter").as_reader()) == others[0]
    assert prompts.prompt_bid(state, tui.reader("right", "right", "enter").as_reader()) == others[2]
    assert prompts.prompt_bid(state, tui.reader("left", "enter").as_reader()) is None
    assert prompts.prompt_bid(state, tui.reader("4").as_reader()) == Suit.TOUT_ATOUT
    assert prompts.prompt_bid(state, tui.reader("5").as_reader()) == SANS_ATOUT_BID
    assert prompts.prompt_bid(state, tui.reader("n").as_reader()) == SANS_ATOUT_BID


def test_prompt_bid_undo_quit_eof_and_overlays(tui: TUI) -> None:
    state = _bidding_state(1)
    assert prompts.prompt_bid(state, tui.reader("z").as_reader()) == "UNDO"
    assert prompts.prompt_bid(state, tui.reader("q").as_reader()) == "QUIT"
    assert prompts.prompt_bid(state, tui.reader().as_reader()) == "QUIT"
    before = theme_manager.current_name
    r = tui.reader("?", "enter", "t", "h", "q", raw_char("m"), "p")
    assert prompts.prompt_bid(state, r.as_reader()) is None
    assert theme_manager.current_name != before
    assert "KEYBOARD SHORTCUTS" in tui.text
    assert "No rounds completed yet." in tui.text


# ── coinche / surcoinche ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (("c",), True),
        (("C",), True),
        (("enter",), False),
        (("esc",), False),
        (("q",), False),
        ((), False),  # EOF
        (("x", "unknown", "c"), True),  # other keys are ignored
    ],
)
def test_prompt_coinche(tui: TUI, script: tuple[str, ...], expected: bool) -> None:
    state = replace(_bidding_state(), taker=Seat.EAST)
    assert prompts.prompt_coinche(state, tui.reader(*script).as_reader()) is expected
    assert "Coinche?" in tui.text
    assert "Press [C] to coinche" in tui.text


@pytest.mark.parametrize("taker", [Seat.EAST, Seat.WEST])
def test_prompt_coinche_labels_ew_taker(tui: TUI, taker: Seat) -> None:
    prompts.prompt_coinche(replace(_bidding_state(), taker=taker), tui.reader().as_reader())
    assert "EW took the bid" in tui.text


def test_prompt_coinche_labels_ns_taker_and_skips_without_taker(tui: TUI) -> None:
    state = replace(_bidding_state(), taker=Seat.NORTH)
    assert prompts.prompt_coinche(state, tui.reader("c").as_reader()) is True
    assert "NS took the bid" in tui.text
    r = tui.reader("c")
    assert prompts.prompt_coinche(replace(state, taker=None), r.as_reader()) is False
    assert r.reads == 0  # never prompts


def test_prompt_coinche_paints_on_bottom_rows(tui: TUI) -> None:
    tui.resize(100, 30)
    prompts.prompt_coinche(replace(_bidding_state(), taker=Seat.EAST), tui.reader().as_reader())
    assert "\x1b[28;1H" in tui.screen.raw


@pytest.mark.parametrize(
    ("script", "expected"),
    [(("s",), True), (("enter",), False), (("esc",), False), ((), False), (("c", "S"), True)],
)
def test_prompt_surcoinche(tui: TUI, script: tuple[str, ...], expected: bool) -> None:
    # "s" is the DOWN alias at the reader layer; the prompt reads raw CHARs.
    events = [raw_char(k) if len(k) == 1 else k for k in script]
    assert prompts.prompt_surcoinche(tui.reader(*events).as_reader(), "EW") is expected
    assert "Surcoinche?" in tui.text
    assert "EW coinched!" in tui.text


@pytest.mark.parametrize("ch", ["s", "S"])
def test_prompt_surcoinche_keyboard_s_key(tui: TUI, ch: str) -> None:
    # keys() applies the real reader alias table, exactly like a keyboard.
    assert prompts.prompt_surcoinche(tui.reader(*keys(ch)).as_reader(), "EW") is True


# ── help / rules / history overlays ─────────────────────────────────────────


def test_show_help_waits_for_one_key(tui: TUI) -> None:
    r = tui.reader("x", "y")
    prompts.show_help(r.as_reader())
    assert r.remaining == 1
    for needle in ("KEYBOARD SHORTCUTS", "Tout Atout (round 2)", "Press any key to return"):
        assert needle in tui.text


def test_show_help_fits_short_terminals_and_shows_live_bindings(tui: TUI) -> None:
    """4.11.0: two columns at 80×24 (the title used to scroll off), and the
    keys shown are the player's own bindings."""
    from belote import input as inp

    tui.resize(80, 24)
    old = inp.current_bindings()
    try:
        inp.set_bindings({"undo": "u"})
        prompts.show_help(tui.reader("x").as_reader())
    finally:
        inp.set_bindings({})
    assert inp.current_bindings() == old
    lines = tui.text.splitlines()
    assert len(lines) <= 24
    assert "KEYBOARD SHORTCUTS" in tui.text and "Surcoinche" in tui.text
    assert any("U" in ln and "Undo last move" in ln for ln in lines)


def test_show_rules_scroll_language_toggle_and_exit(tui: TUI) -> None:
    from belote.rules import RULES_CONTENT

    tui.resize(100, 20)
    r = tui.reader("down", "down", "up", "?", "x", "l", "unknown", "enter")
    prompts.show_rules(r.as_reader())
    assert r.exhausted
    assert RULES_CONTENT["en"]["title"] in tui.text
    assert RULES_CONTENT["fr"]["title"] in tui.text


@pytest.mark.parametrize("exit_key", ["q", "esc", "enter", "eof"])
def test_show_rules_exit_keys(tui: TUI, exit_key: str) -> None:
    r = tui.reader(exit_key, "down")
    prompts.show_rules(r.as_reader())
    assert r.remaining == 1


def test_show_rules_scroll_is_clamped(tui: TUI) -> None:
    tui.resize(100, 12)
    # Scroll way past the end, then back to the top past zero.
    r = tui.reader(*(["down"] * 400), *(["up"] * 400), "q")
    prompts.show_rules(r.as_reader())
    frames = tui.screen.frames()
    assert frames[0] == frames[-1]  # back at the top after the round trip
    assert frames[399] == frames[398]  # pinned at the bottom


def _rs(**kw: object) -> RoundScore:
    base: dict[str, object] = {
        "taker_team": 0,
        "ns_card_pts": 100,
        "ew_card_pts": 62,
        "ns_decl_pts": 0,
        "ew_decl_pts": 0,
        "ns_belote_pts": 0,
        "ew_belote_pts": 0,
        "ns_rebelote": False,
        "ew_rebelote": False,
        "ns_total": 100,
        "ew_total": 62,
        "is_failed": False,
        "is_capot": False,
    }
    base.update(kw)
    return RoundScore(**base)  # type: ignore[arg-type]


_HISTORY = (
    _rs(contract="normal", trump=Suit.HEARTS, taker_seat=Seat.SOUTH, tricks_ns=5, tricks_ew=3),
    _rs(
        contract="sans_atout",
        taker_team=1,
        taker_seat=Seat.EAST,
        is_failed=True,
        decl_summary_ns=("Tierce",),
        decl_summary_ew=("Carré de valets", "Cinquante"),
    ),
    _rs(contract="tout_atout", is_capot=True, decl_summary_ns=("Belote",)),
    _rs(contract="normal", trump=None, is_litige=True, decl_summary_ew=("Tierce",)),
)


def test_show_history_wide_layout_lists_every_round(tui: TUI) -> None:
    state = replace(new_game(), score_history=_HISTORY)
    prompts.show_history(state, tui.reader("down", "up", "q").as_reader())
    text = tui.text
    for needle in ("GAME HISTORY", "DECLARATIONS", "S (NS)", "E (EW)", "SA", "TA", "NORM ?"):
        assert needle in text
    for status in ("CAPOT", "CHUTE", "LITIGE"):
        assert status in text
    assert "…" in text  # long declaration list truncated to its column


def test_show_history_narrow_layout_and_scroll_clamp(tui: TUI) -> None:
    tui.resize(70, 14)
    state = replace(new_game(), score_history=_HISTORY * 3)
    r = tui.reader(*(["down"] * 60), "up", "enter")
    prompts.show_history(state, r.as_reader())
    assert r.exhausted
    text = tui.text
    assert "CON" in text and "decl:" in text
    assert "DECLARATIONS" not in text


def test_show_history_cache_rebuilds_on_resize(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = prompts._build_history_lines

    def spy(state: GameState, term_w: int) -> list[str]:
        calls.append(term_w)
        return real(state, term_w)

    monkeypatch.setattr(prompts, "_build_history_lines", spy)
    tui.term.queue_sizes((120, 40), (120, 40), (70, 40))
    state = replace(new_game(), score_history=_HISTORY)
    prompts.show_history(state, tui.reader("down", "down", "x").as_reader())
    assert calls == [120, 70]


def test_show_history_uses_override_when_installed(tui: TUI) -> None:
    seen: list[object] = []
    prompts.set_history_override(seen.append)
    r = tui.reader("x")
    prompts.show_history(new_game(), r.as_reader())
    assert seen == [r]
    assert r.reads == 0
