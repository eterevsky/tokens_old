import sys
from operator import itemgetter

import tokens
from util import stream_file


def get_tokenizers(filename):
    stream = stream_file(filename)
    counts = [0] * 256
    for byte in stream:
         counts[byte] += 1

    pairs = list(enumerate(counts))
    pairs.sort(key=itemgetter(1), reverse=True)

    for ntokens in (2, 4, 8, 16, 32, 64, 128, 256):
        token_set = tokens.build_bits_tokenset()

        for byte, _ in pairs:
             if token_set.ntokens >= ntokens:
                  break
             if token_set._byte_tokens_by_value[byte] is None:
                  token_set.add_byte(byte)

        print(f"Bits({ntokens})")
        yield tokens.TokenizerBytes(token_set)

        if ntokens <= 16: continue

        token_set = tokens.build_hex_tokenset()

        for byte, _ in pairs:
             if token_set.ntokens >= ntokens:
                  break
             if token_set._byte_tokens_by_value[byte] is None:
                  token_set.add_byte(byte)

        print(f"Hex({ntokens})")
        yield tokens.TokenizerBytes(token_set)


def scan(filename):
        for tokenizer in get_tokenizers(filename):
            stream = stream_file(filename)
            stats = tokenizer.tokenize_and_count(stream)
            print(tokenizer)
            stats.report(show_tokens=True)
            print()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:\npython tokenize.py <text file>")
        sys.exit(1)
    scan(sys.argv[1])