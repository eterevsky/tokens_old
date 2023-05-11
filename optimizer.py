from tokenizer import OptimalTokenizer
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


def prune_token_set(token_set: TokenSet, data: ChunkProvider, ntokens):
    print("Starting with", token_set.ntokens, "tokens")

    tokenizer = OptimalTokenizer(token_set)
    initial_stats = tokenizer.tokenize_chunks(data)
    unused_tokens = []
    for i, token in enumerate(token_set.tokens):
        if initial_stats.count[i] == 0 and not token.mandatory:
            unused_tokens.append(token)

    print("Removing", len(unused_tokens), "unused tokens")
    for token in unused_tokens:
        token_set.remove_token(token)

    print("Initial total:", initial_stats.total_tokens)
    prev_stats = initial_stats

    while token_set.ntokens > ntokens:
        best_removed = None
        best_stats = None

        for token in token_set.tokens:
            if token.mandatory:
                continue

            token_set.remove_token(token)
            tokenizer = OptimalTokenizer(token_set)

            stats = tokenizer.tokenize_chunks(data)

            if best_removed is None or stats.total_tokens < best_stats.total_tokens:
                best_removed = token
                best_stats = stats

            token_set.add_token(token)

        total_delta = best_stats.total_tokens - prev_stats.total_tokens
        print(f"Removing {best_removed}. Added total tokens: {total_delta}")
        token_set.remove_token(best_removed)

        prev_stats = best_stats

    return token_set