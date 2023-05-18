from tokenizer import OptimalTokenizer, TokenStats
from tokens import TokenSet, build_hex_tokenset
from top_substrings import get_top_substrings
from util import ChunkProvider
from operator import itemgetter
from filters import Filter


def build_top_substrings_token_set(
    data: ChunkProvider, ntokens: int
) -> TokenSet:
    top_strings = get_top_substrings(data, ntokens)
    token_set = build_hex_tokenset()

    for s, _ in top_strings:
        if token_set.ntokens >= ntokens:
            break
        if s not in token_set.tokens_by_string:
            token_set.add_string(s)

    assert token_set.ntokens == ntokens

    return token_set


def prune_token_set(
    token_set: TokenSet,
    data: ChunkProvider,
    ntokens: int,
    filters: list[Filter],
    top_to_remove: int = None,
):
    print("Starting with", token_set.ntokens, "tokens")

    tokenizer = OptimalTokenizer(token_set, filters)
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

        if top_to_remove:
            tokenizer = OptimalTokenizer(token_set, filters)
            stats = tokenizer.tokenize_chunks(data)
            tokens_to_remove = []
            for idx, _ in sorted(enumerate(stats.count), key=itemgetter(1)):
                token = token_set.tokens[idx]
                if len(tokens_to_remove) >= top_to_remove:
                    break
                if not token.mandatory:
                    tokens_to_remove.append(token)
        else:
            tokens_to_remove = token_set.tokens

        for token in tokens_to_remove:
            if token.mandatory:
                continue

            token_set.remove_token(token)
            tokenizer = OptimalTokenizer(token_set, filters)

            stats = tokenizer.tokenize_chunks(data)

            if (
                best_removed is None
                or stats.total_tokens < best_stats.total_tokens
            ):
                best_removed = token
                best_stats = stats

            token_set.add_token(token)

        total_delta = best_stats.total_tokens - prev_stats.total_tokens
        print(f"Removing {best_removed}. New total tokens: {best_stats.total_tokens}")
        token_set.remove_token(best_removed)

        prev_stats = best_stats

    return token_set


def prune_token_set_simple(token_set: TokenSet, data: ChunkProvider, ntokens, filters):
    print("Starting with", token_set.ntokens, "tokens")

    tokenizer = OptimalTokenizer(token_set, filters)
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
        tokenizer = OptimalTokenizer(token_set, filters)
        stats = tokenizer.tokenize_chunks(data)
        print("Total tokens:", stats.total_tokens)

        pairs = [(i, count) for i, count in enumerate(stats.count)]
        pairs.sort(key=itemgetter(1))

        for idx, _ in pairs:
            token = token_set.tokens[idx]
            if not token.mandatory:
                break

        print("Removing token", token, "with", stats.count[idx], "appearances")

        token_set.remove_token(token)
        prev_stats = stats

    return token_set


def optimize_bpe(
    token_set: TokenSet, data: ChunkProvider, ntokens: int, literal_cost: int, filters: list[Filter]
):
    """BPE token optimization.

    Iteratively:

    1. Find the most common a) pair of subsequent tokens or b) literal that is
       not a token.

    2. Add a new token for the best pair or literal, found in 1.

    3. If the number of tokens is below the target, go to 1.

    4. Tokenize the text with the new set of tokens.

    5. Iterate through tokens from the most rare, try to remove the token from
       the set and see whether the total number of tokens is lower than before
       step 1.

    6. If the number of tokens in the text has reduced, then go to 1. Otherwise,
       revert the changes in the last iteration and return the set.

    Inspired by https://aclanthology.org/P16-1162.pdf
    """

    while True:
        tokenizer = OptimalTokenizer(token_set, filters)

        pair_count = {}
        total_count = 0
        prev_token = None

        for chunk in data.chunks_str():
            for token in tokenizer.tokenize_str(chunk, expand_literals=False):
                if token.is_literal:
                    total_count += literal_cost
                    pair_count[token.string] = (
                        pair_count.get(token.string, 0) + literal_cost - 1
                    )
                    prev_token = None
                else:
                    total_count += 1
                    if prev_token is not None:
                        s = prev_token.string + token.string
                        pair_count[s] = pair_count.get(s, 0) + 1
                    prev_token = token

        added_token, count = max(pair_count.items(), key=itemgetter(1))

        print(f"{total_count} Adding token {added_token} with count {count}")

        token_set.add_string(added_token)

        if token_set.ntokens <= ntokens:
            continue

        tokenizer = OptimalTokenizer(token_set, filters)
        stats = tokenizer.tokenize_chunks(data)

        pre_remove_count = stats.total_tokens

        token_counts = [(i, count) for i, count in enumerate(stats.count)]
        token_counts.sort(key=itemgetter(1))

        tries = 0
        found = False

        for idx, _ in token_counts:
            token = token_set.tokens[idx]
            if token.mandatory or token.string == added_token:
                continue
            tries += 1
            token_set.remove_token(token)

            tokenizer = OptimalTokenizer(token_set, filters)
            stats: TokenStats = tokenizer.tokenize_chunks(data)

            if stats.total_tokens < total_count:
                print(
                    f"{pre_remove_count} Removing token {token.string} after {tries} tries."
                )
                found = True
                break
            else:
                token_set.add_token(token)

        if not found:
            token_set.remove_token(token_set.tokens_by_string[added_token])
            break
