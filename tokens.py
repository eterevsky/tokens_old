from enum import Enum
from operator import itemgetter
from typing import Iterable, Self


def str_repr(s: bytes) -> str:
    try:
        return repr(s.decode("utf-8"))
    except UnicodeDecodeError:
        return repr(s)


class TokenType(Enum):
    HEX_DIGIT = -3  # 0..16
    BYTE = -4

    # No value, marks the beginning of the word. Should preceed a letter.
    START_WORD = -5
    # Marks the end of the word. Should follow a letter.
    END_WORD = -6
    # Marks that the following word is capitalized. Should preceed either
    # a letter or START_WORD.
    CAPITALIZE_WORD = -7
    # Marks that the following word is in ALL_CAPS
    ALL_CAPS = -8
    # Byte string
    BYTES = -10
    # Sequence of literal and modifier tokens
    SEQUENCE = -11


class Token(object):
    def __init__(
        self,
        token_type: TokenType,
        id: int,
        value: int = None,
        string: bytes = None,
        tokens: list[Self] = None,
        mandatory: bool = False,
    ):
        self.type: TokenType = token_type
        self.id = id  # ID in the TokenSet
        self.value: int = value  # For BIT, TWO_BITS, HEX_DIGIT, BYTE
        self.string: bytes = string  # For BYTES and BYTE
        self.tokens: list[Self] = tokens
        self.mandatory: bool = mandatory

    def _repr(self):
        if self.type == TokenType.HEX_DIGIT:
            h = hex(self.value)
            return f"<{h}>".encode("utf-8")
        elif self.type in (TokenType.BYTE, TokenType.BYTES):
            return self.string
        elif self.type == TokenType.START_WORD:
            return b"<B>"
        elif self.type == TokenType.END_WORD:
            return b"<E>"
        elif self.type == TokenType.CAPITALIZE_WORD:
            return b"<U>"
        elif self.type == TokenType.ALL_CAPS:
            return b"<C>"
        elif self.type == TokenType.SEQUENCE:
            return b"".join(str(t) for t in self.tokens)
        else:
            raise ValueError

    def __repr__(self):
        return repr(self._repr())


class TokenSet(object):
    def __init__(self):
        self._tokens = []
        self._tokens_by_string = {}
        self._byte_tokens_by_value = [None] * 256
        self._hex_tokens_by_value = [None] * 16

    def add_token(self, token: Token):
        assert token.id is None
        token.id = len(self._tokens)
        self._tokens.append(token)
        if token.string is not None:
            assert token.string not in self._tokens_by_string
            self._tokens_by_string[token.string] = token
        if token.type == TokenType.BYTE:
            assert token.value is not None
            assert 0 <= token.value < 256
            assert self._byte_tokens_by_value[token.value] is None
            self._byte_tokens_by_value[token.value] = token
        elif token.type == TokenType.HEX_DIGIT:
            assert token.value is not None
            assert 0 <= token.value < 16
            assert self._hex_tokens_by_value[token.value] is None
            self._hex_tokens_by_value[token.value] = token

    def add_byte(self, value: int, mandatory: bool = True):
        string = bytes([value])
        token = Token(TokenType.BYTE, None, value, string, mandatory=mandatory)
        self.add_token(token)

    def add_hex(self, value: int, mandatory: bool = True):
        token = Token(
            TokenType.HEX_DIGIT, None, value, None, mandatory=mandatory
        )
        self.add_token(token)

    def has_bytes(self) -> bool:
        return all(t is not None for t in self._byte_tokens_by_value)

    def has_hex(self) -> bool:
        return all(t is not None for t in self._hex_tokens_by_value)

    @property
    def ntokens(self) -> int:
        return len(self._tokens)


def build_bytes_tokenset():
    token_set = TokenSet()
    for i in range(256):
        token_set.add_byte(i)
    return token_set


def build_hex_tokenset():
    token_set = TokenSet()
    for i in range(16):
        token_set.add_hex(i)
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
        print(f"Using TokenSet with tokens_in_set")
        pairs = [(i, count) for i, count in enumerate(self.count) if count > 0]
        pairs.sort(key=itemgetter(1), reverse=True)
        used_tokens = len(pairs)
        total_tokens = sum(self.count)
        print(f"Used {used_tokens} different tokens, total: {total_tokens}")
        if show_tokens:
            for token_id, count in pairs[:200]:
                print(self.token_set._tokens[token_id], " ", count)
            if len(pairs) > 200:
                print(". . .")


class Tokenizer(object):
    def __init__(self, token_set: TokenSet):
        self.token_set = token_set

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        pass

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
        assert self.token_set.has_bytes()

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        for b in stream:
            yield self.token_set._byte_tokens_by_value[b]


class TokenizerHex(Tokenizer):
    def __init__(self, token_set: TokenSet):
        super().__init__(token_set)
        assert self.token_set.has_hex()

    def tokenize(self, stream: Iterable[int]) -> Iterable[Token]:
        for b in stream:
            yield self.token_set._hex_tokens_by_value[b // 16]
            yield self.token_set._hex_tokens_by_value[b % 16]

