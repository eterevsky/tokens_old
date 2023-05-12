import sys

import util


if __name__ == "__main__":
    count = {}
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        char = f.read(1)
        counter = 0
        while char:
            code = ord(char)
            try:
                count[code] += 1
            except KeyError:
                count[code] = 1

            counter += 1
            if counter % 1000000 == 0:
                print(counter // 1000000)

            char = f.read(1)

    for i in range(500):
        if i in count:
            print(hex(i), count[i])

    for i in range(0xE000, 0xE020):
        if i in count:
            print(hex(i), count[i])

