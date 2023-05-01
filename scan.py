import sys

import tokens
from util import stream_file


def get_tokenizers():
    token_set = tokens.build_bytes_tokenset()
    yield tokens.TokenizerBytes(token_set)

    token_set = tokens.build_hex_tokenset()
    yield tokens.TokenizerHex(token_set)


def scan(filename):
    for tokenizer in get_tokenizers():
        stream = stream_file(filename)
        stats = tokenizer.tokenize_and_count(stream)
        print(tokenizer)
        stats.report(show_tokens=False)
        print()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:\npython tokenize.py <text file>")
        sys.exit(1)
    scan(sys.argv[1])