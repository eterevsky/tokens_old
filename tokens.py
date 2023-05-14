from typing import Self


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
        is_literal: bool = False,
    ):
        self.id = id  # ID in the TokenSet
        self.value: int = value  # For single-byte tokens
        self.string: bytes = string
        self.length = len(self.string)
        self.mandatory: bool = mandatory
        # The longest other token in the token
        self.suffix_token: Self = None
        self.is_literal: Self = is_literal

    def __repr__(self):
        return repr(self.string)

    def as_json(self):
        assert self.string is not None
        try:
            return self.string.decode("utf-8")
        except UnicodeDecodeError:
            return list(self.string)


VALUE_0 = ord("0")
VALUE_9 = ord("9")
VALUE_a = ord("a")
VALUE_f = ord("f")


class TokenSet(object):
    def __init__(self):
        self.tokens = []

        # Literals are used in suffix_tokens when there is single-byte token.
        self.literals = [
            Token(
                id=None,
                value=i,
                string=bytes([i]),
                mandatory=False,
                is_literal=True,
            )
            for i in range(256)
        ]
        self.tokens_by_string = {}
        self.byte_tokens_by_value = [None] * 256
        self.hex_tokens_by_value = [None] * 16
        self.hex_marker = None
        self.bit0 = None
        self.bit1 = None

    def as_json(self) -> list:
        return list(t.as_json() for t in self.tokens)

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

    def remove_token(self, token: Token):
        assert self.tokens[token.id] is token
        self.tokens.pop(token.id)
        del self.tokens_by_string[token.string]
        if token.value is not None:
            self.byte_tokens_by_value[token.value] = None
            if (VALUE_0 <= token.value <= VALUE_9
                or VALUE_a <= token.value <= VALUE_f):
                if VALUE_0 <= token.value <= VALUE_9:
                    hex_value = token.value - VALUE_0
                else:
                    hex_value = token.value - VALUE_a + 10
                self.hex_tokens_by_value[hex_value] = None
            elif token is self.hex_marker:
                self.hex_marker = None
            elif token is self.bit0:
                self.bit0 = None
            elif token is self.bit1:
                self.bit1 = None

        token.id = None
        self._update_ids()

    def _update_ids(self):
        for i, token in enumerate(self.tokens):
            token.id = i

    def add_byte(self, value: int, mandatory: bool = False):
        if self.byte_tokens_by_value[value] is not None:
            return
        string = bytes([value])
        token = Token(None, value, string, mandatory=mandatory)
        self.add_token(token)

    def add_string(self, string: bytes):
        if string in self.tokens_by_string:
            return
        value = None
        if len(string) == 1:
            value = string[0]
        token = Token(None, value, string)
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
                elif len(substring) == 1:
                    token.suffix_token = self.literals[substring[0]]
                    break

    def sort(self):
        self.tokens.sort(key=lambda t: t.string)
        self._update_ids()


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
