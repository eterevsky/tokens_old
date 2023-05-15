import sys


def main(start: int, finish: int, output: str):
    with open(output, "w", newline="", encoding="utf-8") as out:
        for i in range(start, finish):
            if i % 100 == 0:
                print(f"\r{i}", end="")
            try:
                with open(f"texts/{i}_clean.txt", newline="", encoding="utf-8") as book:
                    lines = book.readlines()
            except FileNotFoundError:
                continue
            try:
                while not lines[-1].strip():
                    lines.pop()
            except IndexError:
                print(f"\nFile {i} is empty")
                continue
            content = "".join(lines) + "\n\uE013"
            out.write(content)

    print()


if __name__ == "__main__":
    start = int(sys.argv[1])
    finish = int(sys.argv[2])
    output = sys.argv[3]
    main(start, finish, output)