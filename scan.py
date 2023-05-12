import sys
from operator import itemgetter
import json
import cProfile

import tokens
from top_substrings import get_top_bytes, get_top_substrings
from util import stream_file, TextFile, ChunkProvider
from optimizer import build_top_substrings_token_set
from tokenizer import TokenStats, GreedyTokenizer, build_from_json


def get_tokenizers(data: ChunkProvider):
    print()

    pairs = get_top_bytes(data)
    for t, c in pairs[:100]:
        print(bytes([t]), c)

    top_strings = get_top_substrings(data, 256)

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

        print(f"TopBytes+Hex({ntokens})")
        yield tokens.GreedyTokenizer(token_set)

        token_set = tokens.build_hex_tokenset()

        for s, _ in top_strings:
             if token_set.ntokens >= ntokens:
                  break
             if s not in token_set.tokens_by_string:
                  token_set.add_string(s)

        print(f"TopStrings+Hex({ntokens})")
        yield tokens.GreedyTokenizer(token_set)


def scan(tokens_json, filename):
     with open(tokens_json) as save:
          tokens_dict = json.load(save)
     tokenizer = build_from_json(tokens_dict)
     data = ChunkProvider(TextFile(filename))
     stats = tokenizer.tokenize_chunks(data)
     stats.report(show_tokens=False)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage:\npython scan.py <tokens json> <data file>")
        sys.exit(1)
    scan(sys.argv[1], sys.argv[2])
