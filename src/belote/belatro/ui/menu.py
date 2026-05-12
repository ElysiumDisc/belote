from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    menu_art_fg,
    menu_border_fg,
    move,
    white_fg,
)
from belote.input import Key
from belote.ui.render import get_term_size

from ..core.run_state import BelAtroRun
from ..run.decks import STARTING_DECKS

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..progression.save import Profile

BELATRO_ART: tuple[str, ...] = (
    r" ____  _____ _        _  _____ ____   ___  ",
    r"| __ )| ____| |      / \|_   _|  _ \ / _ \ ",
    r"|  _ \|  _| | |     / _ \ | | | |_) | | | |",
    r"| |_) | |___| |___ / ___ \| | |  _ <| |_| |",
    r"|____/|_____|_____/_/   \_\_| |_| \_\\___/ ",
    r"   Roguelite  Belote   Adventure   ♠♦♣♥   ",
)

SUIT_ROW = "  ♠  ♦  ♣  ♥  ♠  ♦  ♣  ♥  "


class BelAtroMainMenu:
    """The main menu for the roguelite mode."""

    def __init__(self, reader: KeyReader, profile: Profile) -> None:
        self.reader = reader
        self.profile = profile
        self.selected = 0
        self.options: list[str] = []
        self.selected_deck_id = "classique"

    def run(self) -> BelAtroRun | None:
        """Main loop for the menu."""
        self.options = ["Start Run", "Select Deck", "Collection", "Rules", "Quit"]
        sys.stdout.write(hide_cursor())
        while True:
            self._render()
            event = self.reader.read()
            key = event.key
            if key == Key.UP:
                self.selected = (self.selected - 1) % len(self.options)
            elif key == Key.DOWN:
                self.selected = (self.selected + 1) % len(self.options)
            elif key == Key.ENTER:
                choice = self.options[self.selected]
                if choice == "Start Run":
                    return BelAtroRun(deck_id=self.selected_deck_id, profile=self.profile)
                if choice == "Select Deck":
                    self._select_deck()
                elif choice == "Collection":
                    from .collection import show_collection

                    show_collection(self.reader, self.profile)
                elif choice == "Rules":
                    from .rules import show_belatro_rules

                    show_belatro_rules(self.reader)
                elif choice == "Quit":
                    return None

            elif key in (Key.ESC, Key.QUIT, Key.EOF):
                return None

    def _render(self) -> None:
        term_w, term_h = get_term_size()
        out = [clear_screen()]

        # Center the art block
        art_w = 46  # Approx width of BELATRO_ART
        art_col = max(1, (term_w - art_w) // 2)

        for i, line in enumerate(BELATRO_ART):
            out.append(move(3 + i, art_col) + menu_art_fg() + BOLD + line + RESET)

        out.append(move(9, 1) + ansi_center(menu_border_fg() + SUIT_ROW + RESET, term_w))
        out.append(
            move(10, 1) + ansi_center(white_fg() + "A Belote Roguelite Adventure" + RESET, term_w)
        )

        for i, opt in enumerate(self.options):
            row = 12 + i
            if i == self.selected:
                text = " > " + opt + " < "
                out.append(
                    move(row, 1) + ansi_center(REVERSE + gold_fg() + BOLD + text + RESET, term_w)
                )
            else:
                text = "  " + opt + "  "
                out.append(move(row, 1) + ansi_center(white_fg() + text + RESET, term_w))

        # Show selected deck name at bottom
        deck = next((d for d in STARTING_DECKS if d.id == self.selected_deck_id), None)
        if deck:
            out.append(
                move(18, 1) + ansi_center(light_gray_fg() + f"Deck: {deck.name}" + RESET, term_w)
            )

        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def _select_deck(self) -> None:
        """Deck selection submenu — two-panel layout."""
        sel = next((i for i, d in enumerate(STARTING_DECKS) if d.id == self.selected_deck_id), 0)
        while True:
            term_w, term_h = get_term_size()
            deck = STARTING_DECKS[sel]
            out = [clear_screen()]

            out.append(
                move(3, 1) + ansi_center(gold_fg() + BOLD + "Select Starting Deck" + RESET, term_w)
            )
            line_char = "─" * min(term_w - 4, 76)
            out.append(move(4, 1) + ansi_center(menu_border_fg() + line_char + RESET, term_w))

            list_start_col = max(1, (term_w - 70) // 2)
            for i, d in enumerate(STARTING_DECKS):
                row = 5 + i
                color = gold_fg() + REVERSE if i == sel else white_fg()
                text = f"  {d.name}"
                out.append(move(row, list_start_col) + color + text + RESET)

            # Right panel: selected deck info
            info_col = list_start_col + 35
            out.append(move(5, info_col) + gold_fg() + BOLD + deck.name + RESET)
            out.append(move(6, info_col) + menu_border_fg() + "─" * 36 + RESET)
            for i, art_line in enumerate(deck.ascii_art):
                out.append(move(7 + i, info_col) + menu_art_fg() + art_line + RESET)

            desc_start = 7 + len(deck.ascii_art) + 1
            words = deck.description.split()
            line = ""
            r = desc_start
            for w in words:
                if len(line) + len(w) + 1 > 34:
                    out.append(move(r, info_col) + white_fg() + line + RESET)
                    line = w
                    r += 1
                else:
                    line = (line + " " + w).strip()
            if line:
                out.append(move(r, info_col) + white_fg() + line + RESET)

            out.append(
                move(19, 1)
                + ansi_center(
                    light_gray_fg() + "↑↓ Navigate   Enter: Select   Esc: Back" + RESET, term_w
                )
            )

            sys.stdout.write("".join(out))
            sys.stdout.flush()

            event = self.reader.read()
            key = event.key
            if key == Key.UP:
                sel = (sel - 1) % len(STARTING_DECKS)
            elif key == Key.DOWN:
                sel = (sel + 1) % len(STARTING_DECKS)
            elif key == Key.ENTER:
                self.selected_deck_id = STARTING_DECKS[sel].id
                break
            elif key in (Key.ESC, Key.QUIT, Key.EOF):
                break
