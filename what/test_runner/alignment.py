from collections import Counter

from .types import WORD_RE


def alignment_ops(reference: str, hypothesis: str) -> list[tuple[str, str | None, str | None]]:
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
    ops: list[tuple[str, str | None, str | None]] = []
    while i > 0 or j > 0:
        cur = op[i][j]
        if cur == "eq":
            ops.append(("eq", ref_words[i - 1], hyp_words[j - 1]))
            i -= 1
            j -= 1
        elif cur == "sub":
            ops.append(("sub", ref_words[i - 1], hyp_words[j - 1]))
            i -= 1
            j -= 1
        elif cur == "ins":
            ops.append(("ins", None, hyp_words[j - 1]))
            j -= 1
        else:
            ops.append(("del", ref_words[i - 1], None))
            i -= 1
    ops.reverse()
    return ops


def error_word_stats(reference: str, hypothesis: str, top_n: int = 8) -> dict[str, list[tuple[str, int]]]:
    ops = alignment_ops(reference, hypothesis)
    inserts = Counter()
    deletes = Counter()
    subs = Counter()
    for op, ref_word, hyp_word in ops:
        if op == "ins" and hyp_word:
            inserts[hyp_word] += 1
        elif op == "del" and ref_word:
            deletes[ref_word] += 1
        elif op == "sub" and ref_word and hyp_word:
            subs[f"{ref_word}->{hyp_word}"] += 1
    return {
        "insertions": inserts.most_common(top_n),
        "deletions": deletes.most_common(top_n),
        "substitutions": subs.most_common(top_n),
    }
