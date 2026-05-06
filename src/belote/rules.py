from __future__ import annotations

from typing import TypedDict


class RulesSection(TypedDict):
    header: str
    text: str


class RulesPage(TypedDict):
    title: str
    sections: list[RulesSection]


# Rules and History of Belote in English and French

RULES_CONTENT: dict[str, RulesPage] = {
    "en": {
        "title": "BELOTE - RULES & HISTORY",
        "sections": [
            {
                "header": "History",
                "text": (
                    "Belote is a 32-card trick-taking game that appeared in France around 1900. "
                    "A close relative of 'Klaberjass' and 'klaverjas', definitive rules were first "
                    "published in 1921. It is the national card game of France, and variants are "
                    "widely played in countries like Armenia, Bulgaria, Croatia, Cyprus, and Greece. "
                    "The game is traditionally played by four people in two permanent partnerships."
                ),
            },
            {
                "header": "The Deck",
                "text": (
                    "A 32-card piquet deck is used (A, K, Q, J, 10, 9, 8, 7 in four suits). "
                    "The ranking and point values of cards differ between Trump and Non-Trump suits."
                ),
            },
            {
                "header": "Bidding",
                "text": (
                    "Bidding happens in two rounds. 5 cards are dealt, and a 21st card is turned face-up.\n"
                    "• Round 1: Players decide if they want to 'Take' the up-card's suit as trump.\n"
                    "• Round 2: If everyone passes, players can choose any other suit as trump.\n"
                    "The 'Taker' receives the up-card, and remaining cards are dealt so everyone gets 8."
                ),
            },
            {
                "header": "Gameplay",
                "text": (
                    "• Players must follow the lead suit if possible.\n"
                    "• If void in the lead suit, a player must 'cut' with a trump card.\n"
                    "• If the partner is currently winning the trick, cutting is sometimes optional depending on rules.\n"
                    "• When playing trumps, you must 'overtrump' (play a higher trump) if possible."
                ),
            },
            {
                "header": "Declarations (Melds)",
                "text": (
                    "Points can be earned for specific card combinations held in hand:\n"
                    "• Tierce (3-card sequence): 20 pts  |  Quarte (4-card): 50 pts  |  Quinte (5-card): 100 pts\n"
                    "• Carré (4 of a kind): Jacks=200 pts, Nines=150 pts, A/K/Q/10=100 pts.\n"
                    "• Belote: Holding the King and Queen of Trumps awards 20 pts when played."
                ),
            },
            {
                "header": "Scoring",
                "text": (
                    "• Trump Values: J=20, 9=14, A=11, 10=10, K=4, Q=3, 8=0, 7=0.\n"
                    "• Non-Trump Values: A=11, 10=10, K=4, Q=3, J=2, 9=0, 8=0, 7=0.\n"
                    "• Total card points: 152. 'Dix de Der': +10 points for the last trick (Total 162).\n"
                    "• Contract: The Taker must score more than the defenders (points + declarations).\n"
                    "• Litige (Tie): Defenders score their points; Taker's points are held for the next round's winner.\n"
                    "• Chute (Failure): Defenders score 162 + all declarations from both teams.\n"
                    "• Capot (All 8 tricks): Winning team scores 252 + all declarations from both teams.\n"
                    "• Game End: First team to target score wins. Perfect ties trigger a tie-breaker round."
                ),
            },
        ],
    },
    "fr": {
        "title": "LA BELOTE - RÈGLES & HISTOIRE",
        "sections": [
            {
                "header": "Histoire",
                "text": (
                    "La Belote est un jeu de levées à 32 cartes apparu en France vers 1900. "
                    "Dérivé de jeux comme le 'Klaberjass', ses règles définitives ont été publiées "
                    "en 1921. C'est le jeu de cartes national en France, et ses variantes sont jouées "
                    "dans de nombreux pays (Arménie, Bulgarie, etc.). "
                    "Il se joue traditionnellement à quatre joueurs répartis en deux équipes."
                ),
            },
            {
                "header": "Le Jeu",
                "text": (
                    "On utilise un jeu de 32 cartes (As, R, D, V, 10, 9, 8, 7). "
                    "L'ordre et la valeur des cartes diffèrent selon que la couleur est Atout ou non."
                ),
            },
            {
                "header": "Les Enchères",
                "text": (
                    "Le contrat se décide en deux tours. 5 cartes sont distribuées et une 21ème est retournée.\n"
                    "• 1er tour: Les joueurs choisissent de 'Prendre' la couleur de la carte retournée.\n"
                    "• 2ème tour: Si tout le monde passe, on peut choisir n'importe quelle autre couleur.\n"
                    "Le 'Preneur' reçoit la carte, et les autres cartes sont distribuées (8 chacun)."
                ),
            },
            {
                "header": "Le Jeu de la Carte",
                "text": (
                    "• On doit fournir la couleur demandée si possible.\n"
                    "• Si on n'a pas la couleur, on doit 'couper' avec un atout.\n"
                    "• Si le partenaire est maître sur un pli hors-atout, la coupe est facultative.\n"
                    "• À l'atout, on est obligé de 'monter' (jouer un atout plus fort) si possible."
                ),
            },
            {
                "header": "Les Annonces",
                "text": (
                    "Des points supplémentaires sont accordés pour des combinaisons:\n"
                    "• Tierce (3 cartes): 20 pts | Quarte (4 cartes): 50 pts | Quinte (5 cartes): 100 pts\n"
                    "• Carré (4 cartes pareilles): Valets=200 pts, Neufs=150 pts, As/R/D/10=100 pts.\n"
                    "• Belote et Rebelote: Le Roi et la Dame d'atout rapportent 20 pts."
                ),
            },
            {
                "header": "Le Score",
                "text": (
                    "• Valeurs à l'Atout: V=20, 9=14, As=11, 10=10, R=4, D=3, 8=0, 7=0.\n"
                    "• Valeurs sans Atout: As=11, 10=10, R=4, D=3, V=2, 9=0, 8=0, 7=0.\n"
                    "• Total points: 152. 'Dix de Der': +10 pts pour le dernier pli (Total 162).\n"
                    "• Contrat: Le Preneur doit réaliser plus de points que la défense (plis + annonces).\n"
                    "• Litige: En cas d'égalité, la défense marque, les points du preneur sont remis en jeu.\n"
                    "• Chute: La défense marque 162 points + toutes les annonces des deux camps.\n"
                    "• Capot (8 plis): Le camp vainqueur marque 252 points + toutes les annonces.\n"
                    "• Fin de partie: Le premier camp au score cible gagne. En cas d'égalité, on rejoue."
                ),
            },
        ],
    },
}
