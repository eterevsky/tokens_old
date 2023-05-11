from collections import deque
from itertools import islice
import math
from typing import Self, Iterable
from operator import itemgetter

from tokens import TokenSet, Token
from util import ChunkProvider, INF


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
                yield self._token_set.literals[byte]
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

    @property
    def total_tokens(self) -> int:
        return sum(self.count)

    @property
    def used_tokens(self) -> int:
        return sum(1 for count in self.count if count > 0)

    def as_json(self) -> dict:
        return {
            "ntokens": self.token_set.ntokens,
            "scanned_bytes": self.input_size,
            "used_tokens": self.used_tokens,
            "total_tokens": self.total_tokens,
            "bytes_per_token": self.input_size / self.total_tokens,
            "bits_per_byte": self.total_tokens * math.log2(self.token_set.ntokens) / self.input_size
        }

    def report(self, show_tokens=True):
        print(f"Scanned {self.input_size} bytes")
        tokens_in_set = len(self.count)
        print(f"Using TokenSet with {tokens_in_set} tokens")
        pairs = [(i, count) for i, count in enumerate(self.count) if count > 0]
        pairs.sort(key=itemgetter(1), reverse=True)
        print(f"Used {self.used_tokens} different tokens, total: {self.total_tokens}")
        bytes_per_token = self.input_size / self.total_tokens
        bits_per_byte = self.total_tokens * math.log2(tokens_in_set) / self.input_size
        print(
            f"Bytes per token: {bytes_per_token}, bits per byte: {bits_per_byte}"
        )
        if show_tokens:
            for token_id, count in pairs[:200]:
                print(self.token_set.tokens[token_id], " ", count)
            if len(pairs) > 200:
                print(". . .")


POWERS2 = [128, 64, 32, 16, 8, 4, 2, 1]


class Tokenizer(object):
    def __init__(self, token_set: TokenSet):
        assert token_set.has_bits() or token_set.has_hex()
        self.hex_fallback = token_set.has_hex()
        self.token_set = token_set

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        pass

    def fallback_tokens(self, byte: int) -> Iterable[Token]:
        if self.hex_fallback:
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
                match = self._prefix_to_token.get(data[pos : pos + length])
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


class DynState(object):
    def __init__(self):
        self.cost = INF
        # Best token for the first position in the deque
        self.first_token = None
        # Best token ending in the current position
        self.last_token = None

    def __repr__(self):
        return f"DynState({self.cost}, first={self.first_token}, last={self.last_token})"


class OptimalTokenizer(Tokenizer):
    def __init__(self, token_set: TokenSet):
        super().__init__(token_set)
        self.token_set.compute_suffix_tokens()
        self._suffix_scanner = SuffixScanner(token_set)
        self._max_token_length = max(t.length for t in self.token_set.tokens)
        self._literal_cost = 3 if self.hex_fallback else 8

    def _create_new_state(
        self, state_deque: deque[DynState], token: Token
    ) -> DynState:
        state = DynState()

        while token is not None:
            token_cost = self._literal_cost if token.is_literal else 1
            assert token.length <= len(state_deque)
            prev_state = state_deque[-token.length]
            cost = prev_state.cost + token_cost
            if cost < state.cost:
                state.cost = cost
                state.last_token = token
                if token.length == len(state_deque):
                    state.first_token = token
                else:
                    assert prev_state.first_token is not None
                    state.first_token = prev_state.first_token
            token = token.suffix_token

        assert state.cost > 0
        assert state.last_token is not None
        assert state.first_token is not None

        return state

    def _consume_first_token(self, state_deque: deque[DynState], token: Token):
        # print("_consume_first_token", token)
        if token.is_literal:
            for tok in self.fallback_tokens(token.value):
                yield tok
        else:
            yield token

        for _ in range(token.length):
            state_deque.popleft()

        state_deque[0].first_token = None
        state_deque[0].last_token = None

        for i, state in islice(enumerate(state_deque), 1, None):
            last_token = state.last_token
            if last_token.length > i:
                state.first_token = None
            elif last_token.length == i:
                state.first_token = last_token
            else:
                state.first_token = state_deque[
                    i - last_token.length
                ].first_token

    def _update_current_first(
        self, state_deque: deque[DynState]
    ) -> tuple[Token, int]:
        first_token = state_deque[-1].first_token
        if first_token is None:
            return None, 0
        same_first = 1

        for i in range(len(state_deque) - 2, -1, -1):
            state = state_deque[i]
            if state.first_token == first_token:
                same_first += 1
            else:
                break

        return first_token, same_first

    def tokenize(self, data: Iterable[int]) -> Iterable[Token]:
        init_state = DynState()
        init_state.cost = 0
        state_deque = deque([init_state])
        self._suffix_scanner.reset()

        current_first: Token = None
        same_first_token_steps: int = 0

        for token in self._suffix_scanner.scan(data):
            # print(state_deque, token)
            state: DynState = self._create_new_state(state_deque, token)
            state_deque.append(state)

            if state.first_token == current_first:
                same_first_token_steps += 1
            else:
                current_first = state.first_token
                same_first_token_steps = 1

            while same_first_token_steps >= self._max_token_length:
                # print(same_first_token_steps, self._max_token_length)
                for token in self._consume_first_token(
                    state_deque, current_first
                ):
                    yield token
                (
                    current_first,
                    same_first_token_steps,
                ) = self._update_current_first(state_deque)

        while len(state_deque) > 1:
            for token in self._consume_first_token(state_deque, current_first):
                yield token
            (
                current_first,
                same_first_token_steps,
            ) = self._update_current_first(state_deque)
