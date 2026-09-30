from .types import WORD_RE


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = WORD_RE.findall(reference.lower())
    hyp_words = WORD_RE.findall(hypothesis.lower())
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return _levenshtein(ref_words, hyp_words) / len(ref_words)


def edit_stats(reference: str, hypothesis: str) -> dict[str, int]:
    ref_words = WORD_RE.findall(reference.lower())
    hyp_words = WORD_RE.findall(hypothesis.lower())
    rows = len(ref_words) + 1
    cols = len(hyp_words) + 1
    dp = [[0] * cols for _ in range(rows)]
    op = [[None] * cols for _ in range(rows)]

    for i in range(rows):
        dp[i][0] = i
        op[i][0] = "del" if i > 0 else None
    for j in range(cols):
        dp[0][j] = j
        op[0][j] = "ins" if j > 0 else None

    for i in range(1, rows):
        for j in range(1, cols):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                op[i][j] = "eq"
                continue
            sub = dp[i - 1][j - 1] + 1
            ins = dp[i][j - 1] + 1
            delete = dp[i - 1][j] + 1
            best = min(sub, ins, delete)
            dp[i][j] = best
            if best == sub:
                op[i][j] = "sub"
            elif best == ins:
                op[i][j] = "ins"
            else:
                op[i][j] = "del"

    i = rows - 1
    j = cols - 1
    sub = ins = delete = 0
    while i > 0 or j > 0:
        cur = op[i][j]
        if cur == "eq":
            i -= 1
            j -= 1
        elif cur == "sub":
            sub += 1
            i -= 1
            j -= 1
        elif cur == "ins":
            ins += 1
            j -= 1
        else:
            delete += 1
            i -= 1

    return {
        "sub": sub,
        "ins": ins,
        "del": delete,
        "ref_words": len(ref_words),
    }


def _levenshtein(ref: list[str], hyp: list[str]) -> int:
    rows = len(ref) + 1
    cols = len(hyp) + 1
    dp = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1]
