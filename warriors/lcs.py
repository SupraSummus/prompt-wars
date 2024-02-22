def lcs_len_matrix(a, b):
    """
    Matrix `m` of longest common subsequence lengths
    m[i][j] = length of lcs of a[:i] and b[:j]
    """
    n = len(a)
    m = len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            if a[i] == b[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
    return dp


def lcs_len(a, b):
    """
    Length of longest common subsequence
    """
    dp = lcs_len_matrix(a, b)
    return dp[-1][-1]


def lcs_ranges(a, b):
    """
    Return a list of ranges of matching characters indexed in a.

    For example:
    lcs_ranges("abcde", "xaxdex") -> [(0, 1), (3, 5)]
    """
    dp = lcs_len_matrix(a, b)

    # Reconstruct the LCS
    i = len(a)
    j = len(b)
    a_indexes = []
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            a_indexes.append(i - 1)
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
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
