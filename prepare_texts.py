from gutenbergpy import textget
from gutenbergpy.gutenbergcache import GutenbergCache
import sys


END_SENTENCE = (".", "!", "?")


def looks_like_text_paragraph(lines: list[str]) -> bool:
    stripped_lines = [l.strip() for l in lines]

    caps_new_line = False

    for i in range(len(lines) - 1):
        if stripped_lines[i][-1] not in END_SENTENCE and stripped_lines[i + 1][0].isupper():
            caps_new_line = True

    if caps_new_line and all(l[0].isupper() or not l[0].isalpha() for l in stripped_lines):
        return False

    return True


def process_paragraph(lines: list[str]) -> list[str]:
    if not lines:
        return []
    if looks_like_text_paragraph(lines):
        lines = [lines[0].rstrip()] + [l.strip() for l in lines[1:]]
        return [" ".join(lines)]
    else:
        return lines


SKIP_PREFIXES = [
    "***",
    "All of the original Project Gutenberg Etexts",
    "These original Project Gutenberg Etexts will be compiled into a file",
    "This is a retranscription of one of the first Project",
]


def skip_paragraph(lines: list[str]) -> bool:
    for prefix in SKIP_PREFIXES:
        if lines[0].startswith(prefix):
            return True
    return False


def clean_text(text: str) -> str:
    output_lines = []
    paragraph = []

    for line in text.split("\n"):
        if line.strip():
            paragraph.append(line)
            continue
        if not paragraph:
            if output_lines:
                output_lines.append("")
            continue

        output_paragraph = process_paragraph(paragraph)

        if not output_lines:
            if not skip_paragraph(output_paragraph):
                output_lines = ["", ""] + output_paragraph + [""]
            paragraph = []
            continue

        output_lines.extend(output_paragraph)
        output_lines.append("")
        paragraph = []

    output_paragraph = process_paragraph(paragraph)
    output_lines.extend(output_paragraph)

    return "\n".join(output_lines)


def main(start: int, finish: int):
    for i in range(start, finish):
        print(f"\r{i}", end="")
        try:
            raw_book = textget.get_text_by_id(i)
        except Exception:
            print(" -- missing")
            continue
        assert type(raw_book) is bytes
        clean_book = textget.strip_headers(raw_book)
        book = clean_text(clean_book.decode("utf-8"))

        with open(f"texts/{i}_raw.txt", "wb") as f:
            f.write(raw_book)

        with open(f"texts/{i}_clean.txt", "w", newline="", encoding="utf-8") as f:
            f.write(book)
    print()


if __name__ == "__main__":
    start = int(sys.argv[1])
    finish = int(sys.argv[2])
    main(start, finish)