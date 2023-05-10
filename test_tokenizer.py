from unittest import TestCase

from tokens import build_hex_tokenset
from tokenizer import OptimalTokenizer, GreedyTokenizer


class OptimzalTokenizerTest(TestCase):
    def check_tokenization(
        self,
        text: bytes,
        tokens: list[bytes],
        expected: list[bytes],
        tokenizer_type="optimal",
    ):
        token_set = build_hex_tokenset()
        for token_str in tokens:
            token_set.add_string(token_str)

        if tokenizer_type == "optimal":
            tokenizer = OptimalTokenizer(token_set)
        elif tokenizer_type == "greedy":
            tokenizer = GreedyTokenizer(token_set)

        text_tokens = list(t.string for t in tokenizer.tokenize(text))
        self.assertEqual(text_tokens, expected)

    def test_tokenize_opt1(self):
        self.check_tokenization(
            b"ab", [b"a", b"b", b"ab"], [b"ab"], tokenizer_type="optimal"
        )

    def test_tokenize_greed1(self):
        self.check_tokenization(
            b"ab", [b"a", b"b", b"ab"], [b"ab"], tokenizer_type="greedy"
        )

    def test_tokenize_opt1x3(self):
        self.check_tokenization(
            b"ab ab ab",
            [b"a", b"b", b"ab"],
            [b"ab", b"\x10", b"2", b"0", b"ab", b"\x10", b"2", b"0", b"ab"],
            tokenizer_type="optimal",
        )

    def test_tokenize_greed1x3(self):
        self.check_tokenization(
            b"ab ab ab",
            [b"a", b"b", b"ab"],
            [b"ab", b"\x10", b"2", b"0", b"ab", b"\x10", b"2", b"0", b"ab"],
            tokenizer_type="greedy",
        )

    def test_tokenize_opt2(self):
        self.check_tokenization(
            b"xyz",
            [b"x", b"xy", b"yz"],
            [b"x", b"yz"],
            tokenizer_type="optimal",
        )

    def test_tokenize_greed2(self):
        self.check_tokenization(
            b"xyz",
            [b"x", b"xy", b"yz"],
            [b"xy", b"\x10", b"7", b"a"],
            tokenizer_type="greedy",
        )

    def test_tokenize_opt2x3(self):
        self.check_tokenization(
            b"xyz xyz xyz",
            [b"x", b"xy", b"yz"],
            [
                b"x",
                b"yz",
                b"\x10",
                b"2",
                b"0",
                b"x",
                b"yz",
                b"\x10",
                b"2",
                b"0",
                b"x",
                b"yz",
            ],
            tokenizer_type="optimal",
        )

    def test_tokenize_greed2x3(self):
        self.check_tokenization(
            b"xyz xyz xyz",
            [b"x", b"xy", b"yz"],
            [
                b"xy",
                b"\x10",
                b"7",
                b"a",
                b"\x10",
                b"2",
                b"0",
                b"xy",
                b"\x10",
                b"7",
                b"a",
                b"\x10",
                b"2",
                b"0",
                b"xy",
                b"\x10",
                b"7",
                b"a",
            ],
            tokenizer_type="greedy",
        )

    def test_tokenize_opt3(self):
        self.check_tokenization(
            b"xyztuv",
            [b"xy", b"zt", b"uv", b"xyztu"],
            [b"xy", b"zt", b"uv"],
            tokenizer_type="optimal",
        )

    def test_tokenize_opt4(self):
        self.check_tokenization(
            b"xyztuv",
            [b"x", b"y", b"z", b"t", b"u", b"xyztu"],
            [b"xyztu", b"\x10", b"7", b"6"],
            tokenizer_type="optimal",
        )
