from typing import Self, Iterable

from tokens import TokenSet, Token


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