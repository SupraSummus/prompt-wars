import random

import pytest

from warriors.lcs import lcs_len, lcs_pairs, lcs_ranges
from warriors.warriors import MAX_WARRIOR_LENGTH


def test_lcs_len():
    assert lcs_len('abc', 'abc') == 3
    assert lcs_len('abc', 'def') == 0
    assert lcs_len('abc', 'ab') == 2
    assert lcs_len('abc', 'bc') == 2
    assert lcs_len('abc', 'ac') == 2
    assert lcs_len('abc', 'a') == 1
    assert lcs_len('abc', 'b') == 1
    assert lcs_len('abc', 'c') == 1
    assert lcs_len('abc', '') == 0
    assert lcs_len('', 'abc') == 0
    assert lcs_len('', '') == 0
    assert lcs_len('abc', 'aabc') == 3
    assert lcs_len('abc', 'abbc') == 3
    assert lcs_len('abc', 'abcc') == 3
    assert lcs_len('abc', 'aabbcc') == 3


def test_emoiji():
    # "A" and "pen" look different, but both are in fact two characters long and the second one common.
    # This second char is a "variation selector": b'\xef\xb8\x8f'.
    assert lcs_len('🅰️', '🖋️') == 1

    # So two "A" emoijs have LCS length of 2.
    assert lcs_len('🅰️', '🅰️') == 2


def test_lcs_ranges():
    assert lcs_ranges('', '') == []
    assert lcs_ranges('abc', 'abc') == [(0, 3)]
    assert lcs_ranges('abc', 'def') == []
    assert lcs_ranges('abc', 'ab') == [(0, 2)]
    assert lcs_ranges('abc', 'bc') == [(1, 3)]
    assert lcs_ranges('abc', 'ac') == [(0, 1), (2, 3)]


def test_lcs_ranges_eager():
    """It selects LCS that is at the front"""
    assert lcs_ranges('aaabbbccc', 'abc') == [(0, 1), (3, 4), (6, 7)]


def test_lcs_pairs():
    assert lcs_pairs('', 'abc') == []
    assert lcs_pairs('xaby', 'zab') == [(1, 1), (2, 2)]
    # the "A" of "START" would make two runs of the one "As"
    assert lcs_pairs('START As', 'As') == [(6, 0), (7, 1)]


def reference_fewest_runs(a, b):
    """The fewest runs of any longest common subsequence, by brute force over the matrix's optimal paths."""
    dp = reference_lcs_matrix(a, b)

    def paths(i, j):
        if i == 0 or j == 0:
            yield []
            return
        if a[i - 1] == b[j - 1]:
            for path in paths(i - 1, j - 1):
                yield path + [(i - 1, j - 1)]
        if dp[i - 1][j] == dp[i][j]:
            yield from paths(i - 1, j)
        if dp[i][j - 1] == dp[i][j]:
            yield from paths(i, j - 1)
    return min(runs(path) for path in paths(len(a), len(b)))


def runs(pairs):
    return sum(
        1 for k, (i, j) in enumerate(pairs)
        if k == 0 or pairs[k - 1] != (i - 1, j - 1)
    )


@pytest.mark.parametrize('alphabet', ['ab', 'ab c', 'aaab', 'промпт'])
def test_lcs_pairs_matches_reference(alphabet):
    rng = random.Random(str(alphabet))
    for _ in range(100):
        a = random_text(rng, alphabet, rng.randint(0, 9))
        b = random_text(rng, alphabet, rng.randint(0, 9))
        pairs = lcs_pairs(a, b)
        # a common subsequence, as long as any, in as few runs as any
        assert all(a[i] == b[j] for i, j in pairs), (a, b)
        assert all(i < next_i and j < next_j for (i, j), (next_i, next_j) in zip(pairs, pairs[1:])), (a, b)
        assert len(pairs) == lcs_len(a, b), (a, b)
        assert runs(pairs) == reference_fewest_runs(a, b), (a, b)


def reference_lcs_matrix(a, b):
    """
    The textbook dynamic program the bit-parallel version must agree with:
    m[i][j] = length of lcs of a[:i] and b[:j]
    """
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, a_char in enumerate(a):
        for j, b_char in enumerate(b):
            if a_char == b_char:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
    return dp


def reference_lcs_ranges(a, b):
    """The backtrack over the full matrix, whose tie-breaking marks the front."""
    dp = reference_lcs_matrix(a, b)
    i, j = len(a), len(b)
    a_indexes = []
    while i > 0 and j > 0:
        if dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        elif a[i - 1] == b[j - 1]:
            a_indexes.append(i - 1)
            i -= 1
            j -= 1
        else:
            j -= 1
    a_indexes.reverse()
    ranges = []
    for index in a_indexes:
        if ranges and ranges[-1][1] == index:
            ranges[-1] = (ranges[-1][0], index + 1)
        else:
            ranges.append((index, index + 1))
    return ranges


def random_text(rng, alphabet, length):
    return ''.join(rng.choice(alphabet) for _ in range(length))


@pytest.mark.parametrize('alphabet', [
    # few distinct characters make many equally long subsequences,
    # which is where a backtrack's tie-breaking shows
    'ab',
    'ab c',
    'aaab',
    # astral code points, variation selectors and combining marks
    # are single characters to Python and so to the comparison
    ['🅰', '🖋', '\ufe0f', 'a'],
    'промпт',
    '漢字かなカナ',
    ['e', '\u0301', 'é', ' '],
], ids=['ab', 'ab-space', 'skewed', 'emoji', 'cyrillic', 'cjk', 'combining'])
def test_matches_reference(alphabet):
    rng = random.Random(str(alphabet))
    for _ in range(200):
        a = random_text(rng, alphabet, rng.randint(0, 40))
        b = random_text(rng, alphabet, rng.randint(0, 40))
        assert lcs_len(a, b) == reference_lcs_matrix(a, b)[-1][-1], (a, b)
        assert lcs_ranges(a, b) == reference_lcs_ranges(a, b), (a, b)


def test_matches_reference_at_full_length():
    """Both sides at the longest a warrior or a result can be."""
    rng = random.Random(1000)
    a = random_text(rng, 'abcdefghij klmnop', MAX_WARRIOR_LENGTH)
    b = random_text(rng, 'abcdefghij klmnop', MAX_WARRIOR_LENGTH)
    assert lcs_len(a, b) == reference_lcs_matrix(a, b)[-1][-1]
    assert lcs_ranges(a, b) == reference_lcs_ranges(a, b)
