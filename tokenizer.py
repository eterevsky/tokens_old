import math
from typing import Self, Iterable
from operator import itemgetter

from tokens import TokenSet, Token
from util import ChunkProvider


class ScannerState(object):
    def __init__(self, suffix: bytes, token: Token):
        self.suffix: bytes = suffix
        self.token: Token = token
        self.next: list[Self] = [None] * 256


class SuffixScanner(object):
    """Maintains the longest token matching the current suffix."""

    def __init__(self, token_set: TokenSet):
        self._token_set: TokenSet = token_set
        self._states: dict[bytes, ScannerState] = {}
        self._add_state(b"")
        for token in self._token_set.tokens:
            for end in range(1, token.length + 1):
                self._add_state(token.string[:end])
        self._populate_next()

        self.current_state = None

    def _add_state(self, suffix: bytes):
        if suffix in self._states:
            return
        token = None
        for start in range(0, len(suffix)):
            suffix_suffix = suffix[start:]
            token = self._token_set.tokens_by_string.get(suffix_suffix)
            if token is not None:
                break
        self._states[suffix] = ScannerState(suffix, token)

    def _populate_next(self):
        for state in self._states.values():
            for next_byte in range(256):
                next_suffix = state.suffix + bytes([next_byte])
                for start in range(len(next_suffix) + 1):
                    suffix_suffix = next_suffix[start:]
                    next_state = self._states.get(suffix_suffix)
                    if next_state is not None:
                        state.next[next_byte] = next_state
                        break
                assert state.next[next_byte] is not None

    def scan(self, input: Iterable[int]) -> Iterable[Token | int]:
        state = self._states[b""]
        for byte in input:
            state = state.next[byte]
            if state.token is None:
                yield byte
            else:
                yield state.token

    def reset(self):
        self.current_state = self._states[b""]

    def consume_byte(self, byte: int):
        self.current_state = self.current_state.next[byte]
        assert self.current_state is not None



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

    def tokenize_chunks(self, data: ChunkProvider) -> TokenStats:
        stats = TokenStats(self.token_set)
        for chunk in data.chunks():
            self.tokenize_and_count(chunk, stats)
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


class OptimalTokenizer(Tokenizer):
    def __init__(self, token_set: TokenSet):
        token_set.compute_suffix_tokens()
        super().__init__(token_set)
        self._suffix_scanner = SuffixScanner(token_set)

    def tokenize(self, data: Iterable[int]) -> Iterable[Token]:
        pass