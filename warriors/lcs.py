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
    rows = list(_lcs_rows(a, b))

    def prefix_lcs_len(i, j):
        """Length of longest common subsequence of a[:i] and b[:j]"""
        return j - (rows[i] & ((1 << j) - 1)).bit_count()

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
