from warriors.lcs import lcs_len


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
