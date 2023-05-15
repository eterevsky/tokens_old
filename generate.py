# Select a token set

from typing import Iterable
import sys

from filters import FilterCaps, FilterWords
from optimizer import prune_token_set, prune_token_set_simple, optimize_bpe
import pjson
import tokens
from tokenizer import Tokenizer, TokenStats, OptimalTokenizer
import top_substrings
from util import TextFile, ChunkProvider


def add_strings(
    token_set: tokens.TokenSet,
    top_str: list[tuple[int, int]],
    max_tokens: int = None,
    max_added: int = None,
):
    if max_added is None:
        max_added = len(top_str)
    if max_tokens is None:
        max_tokens = float("inf")
    for s, _ in top_str[:max_added]:
        if token_set.ntokens >= max_tokens:
            break
        if isinstance(s, int):
            token_set.add_byte(s)
        else:
            token_set.add_string(s)


def get_tokenizers(data: ChunkProvider, ntokens: int) -> Iterable[Tokenizer]:
    for filters_config in ([], ["caps"], ["caps", "words"]):
        filters = []
        for f in filters_config:
            print(f)
            if f == "caps":
                filters.append(FilterCaps())
            elif f == "words":
                filters.append(FilterWords())
            else:
                assert False

        top_bytes = top_substrings.get_top_bytes(data, filters)
        top_str = top_substrings.get_top_substrings(data, 10 * ntokens, filters)

        token_set = tokens.build_bits_tokenset()
        add_strings(token_set, top_bytes, ntokens)
        add_strings(token_set, top_str, ntokens)
        tokenizer = OptimalTokenizer(token_set, filters)
        yield tokenizer, {"fallback16": False, "type": "top_bytes", "filters": filters_config}

        token_set = tokens.build_bits_tokenset()
        add_strings(token_set, top_str, ntokens)
        tokenizer = OptimalTokenizer(token_set, filters)
        yield tokenizer, {"fallback16": False, "type": "top_strings", "filters": filters_config}

        token_set = tokens.build_bits_tokenset()
        optimize_bpe(token_set, data, ntokens, literal_cost=8, filters=filters)
        tokenizer = OptimalTokenizer(token_set, filters)
        yield tokenizer, {"fallback16": False, "type": "bpe", "filters": filters_config}

        if ntokens >= 17:
            token_set = tokens.build_hex_tokenset()
            add_strings(token_set, top_bytes, ntokens)
            add_strings(token_set, top_str, ntokens)
            tokenizer = OptimalTokenizer(token_set, filters)
            yield tokenizer, {"fallback16": True, "type": "top_bytes", "filters": filters_config}

            token_set = tokens.build_hex_tokenset()
            add_strings(token_set, top_str, ntokens)
            tokenizer = OptimalTokenizer(token_set, filters)
            yield tokenizer, {"fallback16": True, "type": "top_strings", "filters": filters_config}

            token_set = tokens.build_hex_tokenset()
            optimize_bpe(token_set, data, ntokens, literal_cost=3, filters=filters)
            tokenizer = OptimalTokenizer(token_set, filters)
            yield tokenizer, {"fallback16": True, "type": "bpe", "filters": filters_config}

        for init_mult in (2, 4):
            init_strings = round(ntokens * init_mult)
            for fallback16 in (False, True):
                if ntokens > 64 and not fallback16:
                    continue
                if ntokens <= 16 and fallback16:
                    continue

                token_set = (
                    tokens.build_hex_tokenset()
                    if fallback16
                    else tokens.build_bits_tokenset()
                )

                add_strings(token_set, top_str, None, init_strings)
                add_strings(token_set, top_bytes, None, init_strings)
                init_tokens = token_set.ntokens
                prune_token_set_simple(token_set, data, ntokens, filters)
                tokenizer = OptimalTokenizer(token_set, filters)
                yield tokenizer, {
                    "fallback16": fallback16,
                    "type": "prune_last_token",
                    "init_mult": init_mult,
                    "init_tokens": init_tokens,
                    "filters": filters_config,
                }

                for top_to_remove in (8,):
                    token_set = (
                        tokens.build_hex_tokenset()
                        if fallback16
                        else tokens.build_bits_tokenset()
                    )

                    add_strings(token_set, top_str, None, init_strings)
                    add_strings(token_set, top_bytes, None, init_strings)
                    init_tokens = token_set.ntokens
                    prune_token_set(token_set, data, ntokens, filters, top_to_remove)
                    tokenizer = OptimalTokenizer(token_set, filters)
                    yield tokenizer, {
                        "fallback16": fallback16,
                        "type": "prune_useless_token",
                        "init_mult": init_mult,
                        "init_tokens": init_tokens,
                        "top_to_remove": top_to_remove,
                        "filters": filters_config,
                    }


def top_strings(data: ChunkProvider, ntokens: int) -> Iterable[Tokenizer]:
    top_str = top_substrings.get_top_substrings(data, ntokens)
    token_set = tokens.build_bits_tokenset()

    for s, _ in top_str:
        if token_set.ntokens >= ntokens:
            break
        token_set.add_string(s)

    tokenizer = OptimalTokenizer(token_set)
    yield tokenizer


def generate(data_file: str, ntokens: int, output_file: str):
    data = ChunkProvider(TextFile(data_file), 1024, 16384)

    best_stats = None
    best_optimizer = None
    for tokenizer, optimizer in get_tokenizers(data, ntokens):
        stats = tokenizer.tokenize_chunks(data)
        print()
        print(optimizer)
        stats.report(show_tokens=False)
        print()
        if best_stats is None or stats.total_tokens < best_stats.total_tokens:
            best_stats = stats
            best_optimizer = optimizer

    token_set = best_stats.token_set

    token_set.sort()
    assert token_set.has_bits() or token_set.has_hex()
    tokenizer_json = {
        "tokens": token_set.as_json(),
        "stats": best_stats.as_json(),
        "config": {"fallback16": token_set.has_hex()},
        "optimizer": best_optimizer,
    }

    with open(output_file, "w", newline="") as f:
        pjson.save_json(tokenizer_json, f)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage:\npython generate.py <training data> <number of tokens> <output>"
        )
        sys.exit(1)
    data_file = sys.argv[1]
    ntokens = int(sys.argv[2])
    output_file = sys.argv[3]
    generate(data_file, ntokens, output_file)
