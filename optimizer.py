from tokens import TokenSet, build_hex_tokenset
from top_substrings import get_top_substrings
from util import ChunkProvider


def build_top_substrings_token_set(data: ChunkProvider, ntokens: int) -> TokenSet:
    top_strings = get_top_substrings(data, ntokens)
    token_set = build_hex_tokenset()

    for s, _ in top_strings:
        if token_set.ntokens >= ntokens:
            break
        if s not in token_set.tokens_by_string:
            token_set.add_string(s)

    assert token_set.ntokens == ntokens

    return token_set