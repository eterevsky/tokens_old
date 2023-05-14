from typing import Iterable


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


CHR_UNKNOWN = "\uE000"


class FilterReserved(object):
    """Filter reserved characters that we are going to use in our encoding."""

    def __init__(self):
        self.name = "reserved"

    def _encode_stream(self, chunk: str) -> Iterable[str]:
        for c in chunk:
            if 0xE010 <= ord(c) < 0xE020:
                yield CHR_UNKNOWN