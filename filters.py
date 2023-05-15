from typing import Iterable


CHR_UNKNOWN = "\uE000"
CHR_CAPITALIZE = "\u0014"
CHR_ALL_CAPS = "\u0015"
CHR_END_OF_WORD = "\u0016"


class Filter(object):
    def __init__(self):
        self.name = "unknown"

    def _encode_stream(self, chunk: str) -> Iterable[str]:
        yield chunk

    def encode(self, chunk: str) -> str:
        return "".join(self._encode_stream(chunk))

    def _decode_stream(self, chunk: str) -> Iterable[str]:
        yield chunk

    def decode(self, chunk: str) -> str:
        return chunk


class FilterReserved(Filter):
    """Filter reserved characters that we are going to use in our encoding."""

    def __init__(self):
        self.name = "reserved"

    def _encode_stream(self, chunk: str) -> Iterable[str]:
        for c in chunk:
            if 0x10 <= ord(c) < 0x18:
                yield CHR_UNKNOWN


class FilterCaps(Filter):
    def __init__(self):
        self.name = "caps"

    def _encode_stream(self, chunk: str) -> Iterable[str]:
        word = []
        in_word = False

        for char in chunk:
            if char.isalpha():
                word.append(char)
                in_word = True
            else:
                if in_word:
                    merged = "".join(word)
                    if merged[0].isupper() and merged[1:].islower():
                        yield CHR_CAPITALIZE
                        for c in word:
                            yield c.lower()
                    elif merged.isupper():
                        yield CHR_ALL_CAPS
                        for c in word:
                            yield c.lower()
                    else:
                        for c in word:
                            yield c
                    in_word = False
                    word.clear()
                yield char

        if in_word:
            merged = "".join(word)
            if merged[0].isupper() and merged[1:].islower():
                yield CHR_CAPITALIZE
                for c in word:
                    yield c.lower()
            elif merged.isupper():
                yield CHR_ALL_CAPS
                for c in word:
                    yield c.lower()
            else:
                for c in word:
                    yield c
            in_word = False
            word.clear()


class FilterWords(Filter):
    def __init__(self):
        self.name = "words"

    def _encode_stream(self, chunk: str) -> Iterable[str]:
        prev_letter = False
        prev_end_word_space = False
        for c in chunk:
            if prev_letter:
                if c.isalpha():
                    yield c
                else:
                    yield CHR_END_OF_WORD
                    prev_letter = False
                    if c == " ":
                        prev_end_word_space = True
                    else:
                        yield c
            elif prev_end_word_space:
                prev_end_word_space = False
                if c.isalpha() or c in (CHR_CAPITALIZE, CHR_ALL_CAPS):
                    prev_letter = True
                    yield c
                else:
                    yield " "
                    yield c
            else:
                prev_letter = c.isalpha()
                yield c

        if prev_letter:
            yield CHR_END_OF_WORD
