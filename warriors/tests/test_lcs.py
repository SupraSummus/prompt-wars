from warriors.lcs import lcs_len, lcs_ranges


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
