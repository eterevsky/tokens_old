# Select a token set

from typing import Iterable
import sys

from optimizer import prune_token_set
import pjson
import tokens
from tokenizer import Tokenizer, TokenStats, OptimalTokenizer
import top_substrings
from util import TextFile, ChunkProvider


def get_tokenizers(data: ChunkProvider, ntokens: int) -> Iterable[Tokenizer]:
    top_bytes = top_substrings.get_top_bytes(data)
    top_str = top_substrings.get_top_substrings(data, 2 * ntokens)


    if ntokens < 64:
        token_set = tokens.build_bits_tokenset()
        for b, _ in top_bytes:
            if token_set.ntokens >= ntokens:
                break
            token_set.add_byte(b)
        token_set.sort()

        tokenizer = OptimalTokenizer(token_set)
        yield tokenizer


        if ntokens < 8:
            return


        token_set = tokens.build_bits_tokenset()
        for s, _ in top_str:
            if token_set.ntokens >= ntokens:
                break
            token_set.add_string(s)
        token_set.sort()

        tokenizer = OptimalTokenizer(token_set)
        yield tokenizer


        token_set = tokens.build_bits_tokenset()
        for b, _ in top_bytes:
            token_set.add_byte(b)
        for s, _ in top_str:
            token_set.add_string(s)
        prune_token_set(token_set, data, ntokens)

        tokenizer = OptimalTokenizer(token_set)
        yield tokenizer


    if ntokens <= 16:
        return


    token_set = tokens.build_hex_tokenset()
    for b, _ in top_bytes:
        if token_set.ntokens >= ntokens:
            break
        token_set.add_byte(b)
    token_set.sort()

    tokenizer = OptimalTokenizer(token_set)
    yield tokenizer


    token_set = tokens.build_hex_tokenset()
    for s, _ in top_str:
        if token_set.ntokens >= ntokens:
            break
        token_set.add_string(s)
    token_set.sort()

    tokenizer = OptimalTokenizer(token_set)
    yield tokenizer


    token_set = tokens.build_hex_tokenset()
    for b, _ in top_bytes:
        token_set.add_byte(b)
    for s, _ in top_str:
        token_set.add_string(s)
    prune_token_set(token_set, data, ntokens)

    tokenizer = OptimalTokenizer(token_set)
    yield tokenizer


def generate(data_file: str, ntokens: int, output_file: str):
    data = ChunkProvider(TextFile(data_file), 1024, 16384)

    best_tokenizer = None
    best_stats = None
    for tokenizer in get_tokenizers(data, ntokens):
        stats = tokenizer.tokenize_chunks(data)
        stats.report()
        print()
        if best_stats is None or stats.total_tokens < best_stats.total_tokens:
            best_stats = stats
            best_tokenizer = tokenizer

    best_stats.token_set.sort()
    tokenizer_json = {
        "tokens": best_stats.token_set.as_json(),
        "stats": best_stats.as_json(),
    }

    with open(output_file, "w", newline="") as f:
        pjson.save_json(tokenizer_json, f)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage:\npython generate.py <training data> <number of tokens> <output>")
        sys.exit(1)
    data_file = sys.argv[1]
    ntokens = int(sys.argv[2])
    output_file = sys.argv[3]
    generate(data_file, ntokens, output_file)
