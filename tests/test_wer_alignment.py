"""Coverage plan chunk 2: WER and alignment math."""
from __future__ import annotations

import pytest

from what.test_runner.alignment import alignment_ops, error_word_stats
from what.test_runner.wer import edit_stats, word_error_rate


def test_wer_identical_is_zero():
    assert word_error_rate("the quick brown fox", "the quick brown fox") == 0.0


def test_wer_is_case_insensitive():
    assert word_error_rate("Hello World", "hello world") == 0.0


def test_wer_empty_reference():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "unexpected words") == 1.0


def test_wer_single_substitution():
    # one of four words wrong -> 0.25
    assert word_error_rate("a b c d", "a b x d") == pytest.approx(0.25)


def test_wer_counts_insertions_over_reference_length():
    # ref has 2 words, hyp adds 2 -> 2 insertions / 2 ref words = 1.0
    assert word_error_rate("a b", "a b c d") == pytest.approx(1.0)


def test_edit_stats_classifies_each_error_type():
    # ref: a b c d ; hyp: a x c d e  -> 1 sub (b->x), 1 ins (e)
    stats = edit_stats("a b c d", "a x c d e")
    assert stats == {"sub": 1, "ins": 1, "del": 0, "ref_words": 4}


def test_edit_stats_counts_deletion():
    # ref: a b c ; hyp: a c -> 1 deletion (b)
    stats = edit_stats("a b c", "a c")
    assert stats["del"] == 1 and stats["sub"] == 0 and stats["ins"] == 0


def test_alignment_ops_sequence():
    ops = alignment_ops("a b c", "a x c")
    assert ops == [
        ("eq", "a", "a"),
        ("sub", "b", "x"),
        ("eq", "c", "c"),
    ]


def test_alignment_ops_insert_and_delete():
    ins_ops = alignment_ops("a b", "a b c")
    assert ins_ops[-1] == ("ins", None, "c")
    del_ops = alignment_ops("a b c", "a c")
    assert ("del", "b", None) in del_ops


def test_error_word_stats_aggregates_counts():
    ref = "the cat sat on the mat"
    hyp = "the dog sat the mat now"
    stats = error_word_stats(ref, hyp)
    subs = dict(stats["substitutions"])
    assert subs.get("cat->dog") == 1
    dels = dict(stats["deletions"])
    assert dels.get("on") == 1
    ins = dict(stats["insertions"])
    assert ins.get("now") == 1


def test_error_word_stats_top_n_limit():
    ref = "a b c d e f"
    hyp = "x y z w v u"  # six substitutions
    stats = error_word_stats(ref, hyp, top_n=2)
    assert len(stats["substitutions"]) == 2
