from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    visible_len,
    white_fg,
)
from belote.input import Key
from belote.rules import RulesPage
from belote.ui.render import get_term_size, invalidate_diff

if TYPE_CHECKING:
    from belote.input import KeyReader

BELATRO_RULES: dict[str, RulesPage] = {
    "en": {
        "title": "BELATRO — Roguelite Rules",
        "sections": [
            {
                "header": "What is BelAtro?",
                "text": (
                    "BelAtro is a roguelite run-based mode built on top of the classic Belote card game. "
                    "Play through 8 Antes, each with 3 Blinds (Small, Big, Boss). "
                    "Beat each Blind's score target to advance. Fail, and the run ends."
                ),
            },
            {
                "header": "Scoring: Chips & Mult",
                "text": (
                    "Each trick your team wins converts card points into Chips. "
                    "Your final score = Chips × Mult. Jokers and events modify Chips and Mult throughout the round. "
                    "Beat the Blind's target score to proceed."
                ),
            },
            {
                "header": "The Shop",
                "text": (
                    "After each Blind you enter the Shop. Spend money to buy Jokers, Planet cards, and Tarots. "
                    "Jokers trigger during the round for bonus Chips or Mult. "
                    "Planet cards level up your scoring for a specific suit's trump contracts. "
                    "You can also Reroll the shop for $5."
                ),
            },
            {
                "header": "Jokers",
                "text": (
                    "Jokers are persistent cards that activate on game events (tricks won, declarations scored, round end). "
                    "You can hold up to 5 Jokers at once. Partner Jokers trigger based on what your NORTH partner does."
                ),
            },
            {
                "header": "The Trust Track",
                "text": (
                    "Your partner relationship is tracked on a 0–10 Trust scale. "
                    "Win Blinds together to raise Trust; fail to raise it or get Chuted to lower it. "
                    "High Trust unlocks: Void Information (3+), Duo Contracts (5+), Partner Joker doubles (7+), Auto-Capot (9+). "
                    "Low Trust (≤2) degrades partner AI quality."
                ),
            },
            {
                "header": "Boss Blinds",
                "text": (
                    "Every 3rd Blind in each Ante is a Boss Blind. "
                    "Boss Blinds apply a special modifier that changes the rules for that round "
                    "(e.g. La Grande Muette removes Belote/Rebelote, L'Anarchie rotates trump every 2 tricks). "
                    "Boss modifiers are revealed dramatically at the start of the round."
                ),
            },
            {
                "header": "Antes & Progression",
                "text": (
                    "Each Ante has 3 Blinds: Small → Big → Boss. "
                    "Score targets increase with each Ante. "
                    "Complete all 8 Antes to win the run. "
                    "Between Antes, visit the Shop to power up."
                ),
            },
            {
                "header": "Economy",
                "text": (
                    "Earn $1 per blind beaten. "
                    "Interest: +$1 for every $5 held at round end (max +$5). "
                    "Beating the target by a large margin earns bonus cash. "
                    "Spend wisely — some Jokers are expensive but game-changing."
                ),
            },
        ],
    },
    "fr": {
        "title": "BELATRO — Règles Roguelite",
        "sections": [
            {
                "header": "Qu'est-ce que BelAtro?",
                "text": (
                    "BelAtro est un mode roguelite à runs construit sur le jeu de Belote. "
                    "Jouez 8 Antes, chacun avec 3 Donne (Petite, Grande, Boss). "
                    "Battez le score cible de chaque Donne pour avancer. Échouez, et la partie se termine."
                ),
            },
            {
                "header": "Score: Jetons & Mult",
                "text": (
                    "Chaque levée gagnée convertit les points de cartes en Jetons. "
                    "Score final = Jetons × Mult. Les Jokers modifient Jetons et Mult pendant la manche. "
                    "Dépassez la cible de la Donne pour continuer."
                ),
            },
            {
                "header": "La Boutique",
                "text": (
                    "Après chaque Donne, entrez dans la Boutique. Dépensez de l'argent pour acheter Jokers, Planètes et Tarots. "
                    "Les Jokers s'activent pendant la manche pour des bonus. "
                    "Les Planètes améliorent le score pour un atout donné. "
                    "Vous pouvez aussi Relancer la boutique pour 2€."
                ),
            },
            {
                "header": "Jokers",
                "text": (
                    "Les Jokers s'activent sur des événements de jeu (levées, annonces, fin de manche). "
                    "Vous pouvez en posséder jusqu'à 5. "
                    "Les Jokers Partenaire se déclenchent selon les actions de votre partenaire (NORD)."
                ),
            },
            {
                "header": "La Jauge de Confiance",
                "text": (
                    "La relation avec votre partenaire est mesurée sur une échelle 0–10. "
                    "Gagnez des Donnes ensemble pour augmenter la Confiance. "
                    "Haute Confiance débloque: Info Coupe-Sèche (3+), Contrats Duo (5+), Jokers doublés (7+), Auto-Capot (9+). "
                    "Basse Confiance (≤2) dégrade l'IA partenaire."
                ),
            },
            {
                "header": "Donnes Boss",
                "text": (
                    "Chaque 3e Donne est une Donne Boss avec un modificateur spécial "
                    "(ex: La Grande Muette supprime Belote/Rebelote, L'Anarchie fait changer l'atout). "
                    "Les modificateurs Boss sont révélés de façon dramatique en début de manche."
                ),
            },
            {
                "header": "Antes & Progression",
                "text": (
                    "Chaque Ante a 3 Donnes: Petite → Grande → Boss. "
                    "Les cibles augmentent à chaque Ante. "
                    "Complétez les 8 Antes pour gagner la partie."
                ),
            },
            {
                "header": "Économie",
                "text": (
                    "Gagnez 1€ par Donne réussie. "
                    "Intérêts: +1€ par tranche de 5€ en fin de manche (max +5€). "
                    "Dépasser largement la cible rapporte un bonus. "
                    "Gérez votre budget — certains Jokers sont chers mais décisifs."
                ),
            },
        ],
    },
}


def show_belatro_rules(reader: KeyReader) -> None:
    """Display scrollable BelAtro rules in EN/FR."""
    lang = "en"
    scroll = 0

    def get_render(lang_key: str, wrap_at: int) -> list[str]:
        content = BELATRO_RULES[lang_key]
        lines: list[str] = []
        title = content["title"]
        lines.append(BOLD + gold_fg() + title.upper() + RESET)
        lines.append("=" * min(visible_len(title), wrap_at))
        for section in content["sections"]:
            lines.append("")
            lines.append(BOLD + white_fg() + section["header"] + RESET)
            lines.append("-" * len(section["header"]))
            words = section["text"].split()
            line = "  "
            for w in words:
                if len(line) + len(w) + 1 > wrap_at:
                    lines.append(line)
                    line = "  " + w
                else:
                    line = line + " " + w if line.strip() else "  " + w
            if line.strip():
                lines.append(line)
        lines.append("")
        lang_label = "EN" if lang_key == "en" else "FR"
        lines.append(
            DIM + "Press [L] to Toggle Language (" + lang_label + ") | [Q/Enter/Esc] Back" + RESET
        )
        return lines

    from belote.ui.fit_guard import require_minimum

    hide_cursor()
    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        wrap_at = min(80, term_w - 8)
        view_h = term_h - 4

        lines = get_render(lang, wrap_at)
        max_scroll = max(0, len(lines) - view_h)
        scroll = max(0, min(scroll, max_scroll))

        visible_lines = lines[scroll : scroll + view_h]
        output = [clear_screen()]
        for line in visible_lines:
            output.append(ansi_center(line, term_w) + "\r\n")

        sys.stdout.write("".join(output))
        sys.stdout.flush()
        invalidate_diff()

        event = reader.read()
        key = event.key
        if key in (Key.QUIT, Key.ENTER, Key.ESC, Key.EOF):
            break
        if key == Key.UP:
            scroll = max(0, scroll - 1)
        elif key == Key.DOWN:
            scroll = min(max_scroll, scroll + 1)
        elif key == Key.CHAR and event.char.lower() == "l":
            lang = "fr" if lang == "en" else "en"
            scroll = 0
