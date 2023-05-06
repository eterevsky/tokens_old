import math
from enum import Enum
from operator import itemgetter
from typing import Iterable, Self


def str_repr(s: bytes) -> str:
    try:
        return repr(s.decode("utf-8"))
    except UnicodeDecodeError:
        return repr(s)


class Token(object):
    def __init__(
        self,
        id: int,
        value: int = None,
        string: bytes = None,
        mandatory: bool = False,
    ):
        self.id = id  # ID in the TokenSet
        self.value: int = value  # For single-byte tokens
        self.string: bytes = string  # For BYTES and BYTE
        self.mandatory: bool = mandatory
        # The longest other token in the token
        self.suffix_token: Self = None

    def __repr__(self):
        return repr(self.string)

    @property
    def length(self):
        return len(self.string)


VALUE_0 = ord("0")
VALUE_9 = ord("9")
VALUE_a = ord("a")
VALUE_f = ord("f")


class TokenSet(object):
    def __init__(self):
        self.tokens = []
        self.tokens_by_string = {}
        self.byte_tokens_by_value = [None] * 256
        self.hex_tokens_by_value = [None] * 16
        self.hex_marker = None
        self.bit0 = None
        self.bit1 = None

    def add_token(self, token: Token):
        assert token.id is None
        token.id = len(self.tokens)
        self.tokens.append(token)

        if token.value is not None:
            assert 0 <= token.value < 256
            assert self.byte_tokens_by_value[token.value] is None
            self.byte_tokens_by_value[token.value] = token

            if token.value == 16:
                self.hex_marker = token
            elif token.value == 17:
                self.bit0 = token
            elif token.value == 18:
                self.bit1 = token
            elif (
                VALUE_0 <= token.value <= VALUE_9
                or VALUE_a <= token.value <= VALUE_f
            ):
                if VALUE_0 <= token.value <= VALUE_9:
                    hex_value = token.value - VALUE_0
                else:
                    hex_value = token.value - VALUE_a + 10

                assert 0 <= hex_value < 16
                assert self.hex_tokens_by_value[hex_value] is None
                self.hex_tokens_by_value[hex_value] = token

        assert token.string is not None
        assert token.string not in self.tokens_by_string
        self.tokens_by_string[token.string] = token

    def add_byte(self, value: int, mandatory: bool = True):
        string = bytes([value])
        token = Token(None, value, string, mandatory=mandatory)
        self.add_token(token)

    def add_string(self, string: bytes):
        token = Token(None, None, string)
        self.add_token(token)

    def has_bytes(self) -> bool:
        return all(t is not None for t in self.byte_tokens_by_value)

    def has_hex(self) -> bool:
        return self.hex_marker is not None and all(
            t is not None for t in self.hex_tokens_by_value
        )

    def has_bits(self) -> bool:
        return self.bit0 is not None and self.bit1 is not None

    @property
    def ntokens(self) -> int:
        return len(self.tokens)

    def compute_suffix_tokens(self):
        for token in self.tokens:
            for start in range(1, token.length):
                substring = token.string[start:]
                suffix_token = self.tokens_by_string.get(substring)
                if suffix_token is not None:
                    token.suffix_token = suffix_token
                    break


def build_bits_tokenset():
    token_set = TokenSet()
    token_set.add_byte(17, mandatory=True)
    token_set.add_byte(18, mandatory=True)
    return token_set


def build_hex_tokenset():
    token_set = TokenSet()
    token_set.add_byte(16, mandatory=True)
    for b in range(VALUE_0, VALUE_9 + 1):
        token_set.add_byte(b, mandatory=True)
    for b in range(VALUE_a, VALUE_f + 1):
        token_set.add_byte(b, mandatory=True)

    return token_set


class TokenStats(object):
    def __init__(self, token_set: TokenSet):
        self.token_set = token_set
        self.count = [0] * token_set.ntokens
        self.input_size = 0

    def count_token(self, token: Token):
        self.count[token.id] += 1

    def count_byte(self, byte: int):
        self.input_size += 1

    def report(self, show_tokens=True):
        print(f"Scanned {self.input_size} bytes")
        tokens_in_set = len(self.count)
        print(f"Using TokenSet with {tokens_in_set} tokens")
        pairs = [(i, count) for i, count in enumerate(self.count) if count > 0]
        pairs.sort(key=itemgetter(1), reverse=True)
        used_tokens = len(pairs)
        total_tokens = sum(self.count)
        print(f"Used {used_tokens} different tokens, total: {total_tokens}")
        tokens_per_byte = total_tokens / self.input_size
        bits_per_byte = tokens_per_byte * math.log2(tokens_in_set)
        print(f"Tokens per byte: {tokens_per_byte}, bits per byte: {bits_per_byte}")
        if show_tokens:
            for token_id, count in pairs[:200]:
                print(self.token_set.tokens[token_id], " ", count)
            if len(pairs) > 200:
                print(". . .")


POWERS2 = [128, 64, 32, 16, 8, 4, 2, 1]


class Tokenizer(object):
    def __init__(self, token_set: TokenSet):
        assert token_set.has_bits() or token_set.has_hex()
        self._hex_fallback = token_set.has_hex()
        self.token_set = token_set

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        pass

    def fallback_tokens(self, byte: int) -> Iterable[Token]:
        if self._hex_fallback:
            yield self.token_set.hex_marker
            yield self.token_set.hex_tokens_by_value[byte // 16]
            yield self.token_set.hex_tokens_by_value[byte % 16]
        else:
            for digit in POWERS2:
                if byte & digit:
                    yield self.token_set.bit1
                else:
                    yield self.token_set.bit0

    def tokenize_and_count(
        self, stream: Iterable[int], stats: TokenStats = None
    ) -> TokenStats:
        if stats is None:
            stats = TokenStats(self.token_set)

        def count_input(stream):
            for b in stream:
                stats.count_byte(b)
                yield b

        for token in self.tokenize(count_input(stream)):
            stats.count_token(token)

        return stats


class TokenizerBytes(Tokenizer):
    def __init__(self, token_set: TokenSet):
        super().__init__(token_set)

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        for b in stream:
            byte_token = self.token_set.byte_tokens_by_value[b]
            if byte_token is not None:
                yield byte_token
            else:
                for token in self.fallback_tokens(b):
                    yield token


PARTIAL = "partial"

class GreedyTokenizer(Tokenizer):
    def __init__(self, token_set: TokenSet):
        super().__init__(token_set)
        self._prefix_to_token = {}

        for token in token_set.tokens:
            if token.string is None:
                continue
            self._prefix_to_token[token.string] = token
            for l in range(1, len(token.string)):
                prefix = token.string[:l]
                if prefix not in self._prefix_to_token:
                    self._prefix_to_token[prefix] = PARTIAL

    def tokenize(self, data: Iterable[int]) -> Iterable[Token]:
        data = bytes(data)
        pos = 0
        while pos < len(data):
            longest_match = None
            length = 1

            while length <= len(data) - pos:
                match = self._prefix_to_token.get(data[pos:pos+length])
                if match is None:
                    break

                if match is not PARTIAL:
                    longest_match = match
                length += 1

            if longest_match:
                yield longest_match
                pos += len(longest_match.string)
            else:
                b = data[pos]
                for token in self.fallback_tokens(b):
                    yield token
                pos += 1
