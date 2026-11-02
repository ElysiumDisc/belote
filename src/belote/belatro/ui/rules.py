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
from belote.input import Key, KeyEvent
from belote.rules import RulesPage
from belote.ui.render import get_term_size, invalidate_diff
from belote.ui.text import wrap_words

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
                    "You can also Reroll the shop for $5, Fuse Jokers, or skip the next blind (K)."
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
                    "High Trust unlocks: Void Information (3+), Duo Contracts (5+), Partner Joker doubles (7+). "
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
            {
                "header": "L'Atelier: card enhancements & seals",
                "text": (
                    "Every shop offers one Atelier upgrade for a single card of the 32. "
                    "Enhancements: Verre (its points count twice; 1 in 4 it shatters and the "
                    "trick scores 0), Acier (your trick Jokers trigger again), Chance (a random "
                    "reward). Seals: Rouge (+2 Mult when it takes a trick), Bleu (round-end "
                    "Jokers trigger again), Or (+$1). The twist: they trigger when your team "
                    "CAPTURES the card — whoever held it. An enhanced card in an opponent's "
                    "hand is a prize to take."
                ),
            },
            {
                "header": "Le Serment: fusing Jokers",
                "text": (
                    "Copies of a Joker are safe to own, and the shop sometimes offers one of "
                    "yours. Own three copies and Fuse them into one Juré Joker (✦) whose every "
                    "Chips, Mult and $ is doubled. Some pairs of Jokers fuse into a unique one "
                    "(Le Maréchal + Le Capitaine → Le Général…) — find the recipes in the "
                    "Collection."
                ),
            },
            {
                "header": "Médailles",
                "text": (
                    "Press K in the shop to skip the next Small or Big Blind: no round, no "
                    "payout and no shop, but you take its Médaille. A capot, crushing a Boss "
                    "Blind (target reached by trick 4) or surviving on Capot Insurance earns "
                    "one too (one such feat per Ante). "
                    "Médailles bend the next shop: free rerolls, extra Jokers, a free Tarot, "
                    "copies of your Jokers…"
                ),
            },
            {
                "header": "Contrat Capot & Grand Chelem",
                "text": (
                    "From Ante 2 some Big Blinds are contract blinds. When your team takes the "
                    "contract you may declare it after seeing your hand. Contrat Capot: take "
                    "all 8 tricks — the blind is won whatever the score, plus $10 and a "
                    "Médaille. Grand Chelem (Ante 5+): all 8, and you win at least 5 yourself — "
                    "+$25, +1 Joker slot, two Médailles. Miss, and the blind is lost (Capot "
                    "Insurance covers it once)."
                ),
            },
            {
                "header": "Your partner's story",
                "text": (
                    "Your partner has things to say. Betrayals, reconciliations, a first capot, "
                    "a sulk behind the newspaper: a dozen café scenes fire on the moments that "
                    "matter, once per run each, and every one leaves you a small gift."
                ),
            },
            {
                "header": "L'Usurier",
                "text": (
                    "From Ante 2 the moneylender visits some shops: borrow $30 at 20% per "
                    "Ante, compounding (one loan at a time). Repay any part, any time, in "
                    "the shop. The cash feeds La Voûte's interest, but the debt outgrows "
                    "it — owe $90 and he seizes your money, then your Jokers."
                ),
            },
            {
                "header": "La Gangrène",
                "text": (
                    "A boss whose curse outlives its blind: it rots one of your Jokers into a "
                    "corrupted one, for good, and the rot takes another Joker at the start of "
                    "every Ante until your team wins a round by capot."
                ),
            },
            {
                "header": "Boss Rush & Ghost Runs",
                "text": (
                    "Boss Rush starts a practice run from any Ante with a chosen boss, deck "
                    "and seed; it doesn't count toward unlocks. With Ghost run recording on "
                    "(Settings), every run is saved: Watch Ghost Run replays it round by "
                    "round (+/- speed, Space pause, N skip round, Esc quit)."
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
                    "Haute Confiance débloque: Info Coupe-Sèche (3+), Contrats Duo (5+), Jokers doublés (7+). "
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
            {
                "header": "L'Atelier : améliorations et sceaux",
                "text": (
                    "Chaque boutique propose une amélioration de l'Atelier pour une des 32 cartes. "
                    "Améliorations : Verre (ses points comptent double ; 1 fois sur 4 il se brise "
                    "et la levée vaut 0), Acier (vos Jokers de levée se déclenchent à nouveau), "
                    "Chance (une récompense au hasard). Sceaux : Rouge (+2 Mult quand elle fait "
                    "la levée), Bleu (les Jokers de fin de manche se redéclenchent), Or (+1€). "
                    "Elles se déclenchent quand votre équipe CAPTURE la carte — peu importe qui "
                    "la tenait."
                ),
            },
            {
                "header": "Le Serment : fusionner des Jokers",
                "text": (
                    "Posséder plusieurs exemplaires d'un Joker est sans danger, et la boutique en "
                    "propose parfois. Avec trois exemplaires, fusionnez-les en un Joker Juré (✦) "
                    "dont chaque Jeton, Mult et € est doublé. Certaines paires fusionnent en un "
                    "Joker unique (Le Maréchal + Le Capitaine → Le Général…) : les recettes sont "
                    "dans la Collection."
                ),
            },
            {
                "header": "Médailles",
                "text": (
                    "Touche K en boutique : sautez la prochaine Petite ou Grande Donne — ni "
                    "manche, ni gain, ni boutique — et prenez sa Médaille. Un capot, une Donne "
                    "Boss écrasée (cible atteinte à la 4e levée) ou un sauvetage par l'Assurance "
                    "Capot en rapportent aussi (un exploit par Ante). Les Médailles modifient la boutique suivante."
                ),
            },
            {
                "header": "Contrat Capot & Grand Chelem",
                "text": (
                    "Dès l'Ante 2, certaines Grandes Donnes sont des donnes à contrat. Quand votre "
                    "équipe prend, vous pouvez l'annoncer après avoir vu votre main. Contrat "
                    "Capot : les 8 levées — la Donne est gagnée quel que soit le score, +10€ et "
                    "une Médaille. Grand Chelem (Ante 5+) : les 8 levées dont au moins 5 pour "
                    "vous — +25€, +1 emplacement de Joker, deux Médailles. Raté : la Donne est "
                    "perdue (l'Assurance Capot vous couvre une fois)."
                ),
            },
            {
                "header": "L'histoire de votre partenaire",
                "text": (
                    "Trahisons, réconciliations, premier capot, bouderie derrière le journal : "
                    "une douzaine de scènes de café ponctuent les moments forts, une fois par "
                    "partie chacune, et chacune vous laisse un petit cadeau."
                ),
            },
            {
                "header": "L'Usurier",
                "text": (
                    "Dès l'Ante 2, l'usurier passe dans certaines boutiques : empruntez 30€ à "
                    "20% par Ante, intérêts composés (un prêt à la fois). Remboursez quand vous "
                    "voulez, en partie ou en totalité. L'argent nourrit les intérêts de La "
                    "Voûte, mais la dette grandit plus vite — à 90€ il saisit votre argent, "
                    "puis vos Jokers."
                ),
            },
            {
                "header": "La Gangrène",
                "text": (
                    "Un boss dont la malédiction survit à sa Donne : il pourrit un de vos Jokers "
                    "en Joker corrompu, pour de bon, puis en pourrit un autre à chaque Ante "
                    "jusqu'à ce que votre équipe gagne une manche par capot."
                ),
            },
            {
                "header": "Boss Rush & Parties fantômes",
                "text": (
                    "Le Boss Rush lance une partie d'entraînement depuis n'importe quel Ante, "
                    "avec le boss, le deck et la graine de votre choix ; elle ne compte pas "
                    "pour les déblocages. Avec l'enregistrement fantôme activé (Réglages), "
                    "chaque partie est sauvegardée : « Watch Ghost Run » la rejoue manche par "
                    "manche (+/- vitesse, Espace pause, N manche suivante, Échap quitter)."
                ),
            },
        ],
    },
}


def rules_lines(lang_key: str, wrap_at: int) -> list[str]:
    """Pure line-builder for the BelAtro rules screen (one language)."""
    content = BELATRO_RULES[lang_key]
    title = content["title"]
    lines: list[str] = [
        BOLD + gold_fg() + title.upper() + RESET,
        "=" * min(visible_len(title), wrap_at),
    ]
    for section in content["sections"]:
        lines.append("")
        lines.append(BOLD + white_fg() + section["header"] + RESET)
        lines.append("-" * len(section["header"]))
        lines.extend(wrap_words(section["text"], wrap_at, indent="  "))
    lines.append("")
    lang_label = "EN" if lang_key == "en" else "FR"
    lines.append(
        DIM + "Press [L] to Toggle Language (" + lang_label + ") | [Q/Enter/Esc] Back" + RESET
    )
    return lines


_FOOTER_TARGETS: list[tuple[str, object]] = [
    ("[L] to Toggle Language", "lang"),
    ("[Q/Enter/Esc] Back", "back"),
]


def show_belatro_rules(reader: KeyReader) -> None:
    """Display scrollable BelAtro rules in EN/FR."""
    lang = "en"
    scroll = 0

    from belote.ui.fit_guard import require_minimum

    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        wrap_at = min(80, term_w - 8)
        view_h = term_h - 4

        lines = rules_lines(lang, wrap_at)
        max_scroll = max(0, len(lines) - view_h)
        scroll = max(0, min(scroll, max_scroll))

        visible_lines = [ansi_center(line, term_w) for line in lines[scroll : scroll + view_h]]
        # hide_cursor() returns the escape string; pre-4.10.0 it was called
        # bare (a no-op) instead of being written with the frame.
        output = [clear_screen(), hide_cursor()]
        for line in visible_lines:
            output.append(line + "\r\n")

        sys.stdout.write("".join(output))
        sys.stdout.flush()
        invalidate_diff()

        from belote.ui import hitmap

        # 5.0.0 mouse: the footer's two actions (the wheel scrolls).
        hitmap.targets_from_lines("menu", visible_lines, _FOOTER_TARGETS, pad=0)
        event = reader.read()
        key = event.key
        if key == Key.MOUSE:
            clicked = hitmap.hit("menu", event.pos)
            if clicked == "back":
                break
            if clicked == "lang":
                key, event = Key.CHAR, KeyEvent(Key.CHAR, "l")
        if key in (Key.QUIT, Key.ENTER, Key.ESC, Key.EOF):
            break
        if key == Key.UP:
            scroll = max(0, scroll - 1)
        elif key == Key.DOWN:
            scroll = min(max_scroll, scroll + 1)
        elif key == Key.CHAR and (event.char or "").lower() == "l":
            lang = "fr" if lang == "en" else "en"
            scroll = 0
