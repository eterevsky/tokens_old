import sys
from operator import itemgetter

import tokens
from top_substrings import get_top_bytes, get_top_substrings
from util import stream_file, TextFile, ChunkProvider


def get_tokenizers(data: ChunkProvider):
    pairs = get_top_bytes(data)
    for t, c in pairs[:100]:
        print(bytes([t]), c)

    for ntokens in (2, 4, 8, 16, 32, 64, 128, 256):
        token_set = tokens.build_bits_tokenset()

        for byte, _ in pairs:
             if token_set.ntokens >= ntokens:
                  break
             if token_set.byte_tokens_by_value[byte] is None:
                  token_set.add_byte(byte)

        print(f"Bits({ntokens})")
        yield tokens.GreedyTokenizer(token_set)

        if ntokens <= 16: continue

        token_set = tokens.build_hex_tokenset()

        for byte, _ in pairs:
             if token_set.ntokens >= ntokens:
                  break
             if token_set.byte_tokens_by_value[byte] is None:
                  token_set.add_byte(byte)

        print(f"Hex({ntokens})")
        yield tokens.GreedyTokenizer(token_set)


def scan(filename):
    data = ChunkProvider(TextFile(filename), 1024, 16384)

    for tokenizer in get_tokenizers(data):
        stream = stream_file(filename)
        stats = tokens.TokenStats(tokenizer.token_set)
        for i in range(512):
            fragment = data.sample_bytes(2048)
            tokenizer.tokenize_and_count(fragment, stats)
        print(tokenizer)
        stats.report(show_tokens=False)
        print()


def top_strings(filename):
    data = ChunkProvider(TextFile(filename), 1024, 16384)
    top_strings = get_top_substrings(data, 256)
    for s, count in top_strings:
        print(s, count)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:\npython tokenize.py <text file>")
        sys.exit(1)
    # scan(sys.argv[1])
    top_strings(sys.argv[1])