import sys


def main(start: int, finish: int, output: str):
    with open(output, "w", newline="", encoding="utf-8") as out:
        for i in range(start, finish):
            print(f"\r{i}", end="")
            with open(f"texts/{i}_clean.txt", newline="", encoding="utf-8") as book:
                lines = book.readlines()
            while not lines[-1].strip():
                lines.pop()
            content = "".join(lines) + "\n\uE013"
            out.write(content)

    print()


if __name__ == "__main__":
    start = int(sys.argv[1])
    finish = int(sys.argv[2])
    output = sys.argv[3]
    main(start, finish, output)