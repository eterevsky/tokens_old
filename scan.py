import sys

import tokens
from util import stream_file


def scan(filename):
    stream = stream_file(filename)
    token_set = tokens.build_bytes_tokenset()
    tokenizer = tokens.TokenizerBytes(token_set)
    stats = tokenizer.tokenize_and_count(stream)
    stats.report()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:\npython tokenize.py <text file>")
        sys.exit(1)
    scan(sys.argv[1])