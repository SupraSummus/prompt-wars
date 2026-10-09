"""
Whether an attack copies a boss: the copy check behind the hill's entry rules.

Pure functions over two texts;
`hill.attack` runs them against the current boss and the recent ones.
"""
import unicodedata
from collections import Counter


# An attack carrying this share of a boss is a copy, which would beat it by echoing it:
# the boss plus an extension takes about two thirds of a battle the model answers by echoing.
# Quoting a phrase or two stays allowed.
HILL_BOSS_COPY_THRESHOLD = 0.8
# Shingle length: long enough that a match means shared phrasing, short enough to survive small edits.
HILL_SHINGLE_LENGTH = 5
# A boss skeleton shorter than this has too few shingles to measure.
HILL_SHORT_BOSS = 20
# An attack shorter than this is never judged a fragment of the boss: too little text to tell.
HILL_FRAGMENT_MIN = 50


# Greek capitals whose lowercase passes for another Latin letter (Η, η) or none (Ζ, ζ),
# so they fold before casefolding does.
_CAPITAL_CONFUSABLES = str.maketrans({
    'Η': 'h', 'Μ': 'm', 'Ν': 'n', 'Υ': 'y', 'Ζ': 'z',
})
# Cyrillic and Greek letters that pass for Latin ones, after casefolding.
_CONFUSABLES = str.maketrans({
    'а': 'a', 'в': 'b', 'е': 'e', 'ё': 'e', 'к': 'k', 'м': 'm', 'н': 'h', 'о': 'o',
    'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'і': 'i', 'ј': 'j', 'ѕ': 's',
    'ԁ': 'd', 'һ': 'h', 'ԛ': 'q', 'ԝ': 'w', 'ӏ': 'l',
    'α': 'a', 'β': 'b', 'ε': 'e', 'η': 'n', 'ι': 'i', 'κ': 'k', 'μ': 'u', 'ν': 'v',
    'ο': 'o', 'ρ': 'p', 'τ': 't', 'υ': 'u', 'χ': 'x', 'ϲ': 'c',
})


def skeleton(text):
    """
    What is left of a text once spacing, case, punctuation and disguises go:
    marks, separators, punctuation and control or format characters are dropped after NFKD,
    and lookalike Cyrillic and Greek letters fold to Latin; letters, digits and emoji stay.
    """
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(
        char for char in text
        if unicodedata.category(char)[0] not in 'MZPC'
    )
    return text.translate(_CAPITAL_CONFUSABLES).casefold().translate(_CONFUSABLES)


def _shingles(text_skeleton):
    n = HILL_SHINGLE_LENGTH
    return Counter(
        text_skeleton[i:i + n]
        for i in range(len(text_skeleton) - n + 1)
    )


def containment(a, b):
    """
    The share of `a`'s skeleton found in `b`'s, by multiset of shingles.

    A multiset, so repeating one phrase of the boss many times
    covers no more of the boss than writing it once.
    0.0 when `a` is too short to have a shingle.
    """
    a_shingles = _shingles(skeleton(a))
    total = sum(a_shingles.values())
    if total == 0:
        return 0.0
    b_shingles = _shingles(skeleton(b))
    return sum(
        min(count, b_shingles[shingle])
        for shingle, count in a_shingles.items()
    ) / total


def copied_share(boss, attack):
    """
    How much of `attack` copies `boss`, from 0 to 1.

    Below `HILL_SHORT_BOSS`, only a text with the same skeleton copies a boss.
    Otherwise an attack copies by carrying the boss (the boss plus an extension)
    or, long enough to be judged on its own, by being mostly boss (a fragment).
    Inserting real letters every few characters evades this; a takedown is the backstop.
    """
    boss_skeleton = skeleton(boss)
    if len(boss_skeleton) < HILL_SHORT_BOSS:
        return float(skeleton(attack) == boss_skeleton)
    share = containment(boss, attack)
    if len(skeleton(attack)) >= HILL_FRAGMENT_MIN:
        share = max(share, containment(attack, boss))
    return share
