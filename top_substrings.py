from operator import itemgetter
from typing import Iterable

from tokens import Token, TokenSet
from tokenizer import SuffixScanner
from util import ChunkProvider


def get_top_bytes(data: ChunkProvider) -> list[tuple[bytes, int]]:
    counts = [0] * 256
    for chunk in data.chunks():
        for byte in chunk:
            counts[byte] += 1

    pairs = [(i, count) for i, count in enumerate(counts) if count > 0]
    pairs.sort(key=itemgetter(1), reverse=True)
    return pairs


def sort_and_prune(
    counts: dict[bytes, int], nstrings: int
) -> list[tuple[bytes, int]]:
    pairs = [(i, count) for i, count in counts.items()]
    pairs.sort(key=itemgetter(1), reverse=True)
    return pairs[:nstrings]


def get_top_substrings(
    data: ChunkProvider, nstrings: int
) -> list[tuple[bytes, int]]:
    counts: dict[bytes, int] = {}

    for byte, count in get_top_bytes(data):
        if count > 0:
            counts[bytes([byte])] = count

    for length in range(2, 1000):
        max_current_len = max(len(s) for s in counts.keys())
        if max_current_len < length - 1:
            break

        prefixes = TokenSet()
        for s in counts.keys():
            if len(s) == length - 1:
                prefixes.add_string(s)
        print("Length", length - 1, "substrings:", prefixes.ntokens)

        scanner = SuffixScanner(prefixes)

        for chunk in data.chunks():
            scanner.reset()
            for byte in chunk:
                if (
                    scanner.current_state.token is not None
                    and not scanner.current_state.token.is_literal
                ):
                    token_string = scanner.current_state.token.string
                    # print(scanner.current_state.token)
                    assert len(token_string) == length - 1
                    string = token_string + bytes([byte])
                    counts[string] = counts.get(string, 0) + 1
                scanner.consume_byte(byte)

        counts = dict(sort_and_prune(counts, nstrings))

    return sort_and_prune(counts, nstrings)
