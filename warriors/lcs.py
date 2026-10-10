from collections import deque


def _lcs_rows(a, b):
    """
    The rows of the LCS length table of `a` against `b`, as bit vectors.

    Row i covers `a[:i]`; its bit j is clear exactly where the table
    steps up between `b[:j]` and `b[:j + 1]`, so
    lcs_len(a[:i], b[:j]) == j - popcount(row & ((1 << j) - 1)).
    This is Hyyrö's form of the bit-vector LCS recurrence (Crochemore et al.):
    one row costs a few big-integer operations
    rather than len(b) Python-level steps,
    which is what keeps a whole battle page's marks cheap to render.
    """
    # bit j of a character's mask is set where b[j] is that character
    masks = {}
    for j, char in enumerate(b):
        masks[char] = masks.get(char, 0) | (1 << j)
    full = (1 << len(b)) - 1
    row = full
    yield row
    for char in a:
        matches = row & masks.get(char, 0)
        row = ((row + matches) | (row - matches)) & full
        yield row


def _prefix_lcs_len(a, b):
    """lcs_len(a[:i], b[:j]) as a function of i and j, from one pass over the table."""
    rows = list(_lcs_rows(a, b))

    def prefix_lcs_len(i, j):
        return j - (rows[i] & ((1 << j) - 1)).bit_count()
    return prefix_lcs_len


def lcs_len(a, b):
    """
    Length of longest common subsequence
    """
    (last_row,) = deque(_lcs_rows(a, b), maxlen=1)
    return len(b) - last_row.bit_count()


def lcs_ranges(a, b):
    """
    Return a list of ranges of matching characters indexed in a.

    For example:
    lcs_ranges("abcde", "xaxdex") -> [(0, 1), (3, 5)]
    lcs_ranges("aaa", "a") -> [(0, 1)]
    """
    prefix_lcs_len = _prefix_lcs_len(a, b)

    # Reconstruct the LCS
    i = len(a)
    j = len(b)
    a_indexes = []
    while i > 0 and j > 0:
        if prefix_lcs_len(i - 1, j) > prefix_lcs_len(i, j - 1):
            i -= 1
        elif a[i - 1] == b[j - 1]:
            a_indexes.append(i - 1)
            i -= 1
            j -= 1
        else:
            j -= 1
    a_indexes = list(reversed(a_indexes))

    # Find the ranges
    result = []
    i = 0
    while i < len(a_indexes):
        start = a_indexes[i]
        while i + 1 < len(a_indexes) and a_indexes[i + 1] == a_indexes[i] + 1:
            i += 1
        end = a_indexes[i]
        result.append((start, end + 1))
        i += 1

    return result


def lcs_pairs(a, b):
    """
    A longest common subsequence of `a` and `b`,
    as the `(i, j)` index pairs where `a[i] == b[j]` is one of its characters.

    Of the subsequences as long as lcs_len, it takes one in the fewest runs,
    the one a reader would draw by hand:
    "As" in both texts pairs up as "As",
    not as the "A" of an earlier "START" and the "s" after it.
    A backtrack's cheaper tie-breaks, like continuing a run whenever one can, still split it.
    The price is a quadratic number of Python steps, which suits a text of a few lines.
    """
    prefix_lcs_len = _prefix_lcs_len(a, b)

    # runs[i][j][joined]: the fewest runs a longest common subsequence
    # of a[:i] and b[:j] can come in,
    # where `joined` says a[i] and b[j] are common,
    # so that a common a[i - 1] and b[j - 1] extend their run rather than start one
    runs = [[(0, 0)] * (len(b) + 1) for _ in range(len(a) + 1)]

    def options(i, j, joined):
        length = prefix_lcs_len(i, j)
        if a[i - 1] == b[j - 1]:
            yield runs[i - 1][j - 1][True] + (not joined), (i - 1, j - 1, True)
        if prefix_lcs_len(i - 1, j) == length:
            yield runs[i - 1][j][False], (i - 1, j, False)
        if prefix_lcs_len(i, j - 1) == length:
            yield runs[i][j - 1][False], (i, j - 1, False)

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            runs[i][j] = tuple(
                min(count for count, _ in options(i, j, joined))
                for joined in (False, True)
            )

    pairs = []
    i, j, joined = len(a), len(b), False
    while i > 0 and j > 0:
        _, (i, j, matched) = min(options(i, j, joined), key=lambda option: option[0])
        if matched:
            pairs.append((i, j))
        joined = matched
    return pairs[::-1]
