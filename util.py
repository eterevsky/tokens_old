import mmap
import random
from typing import Iterable


def stream_file(filename):
    with open(filename, "rb") as file:
        while True:
            byte = file.read(1)
            if not byte:
                return
            yield byte[0]


def mmap_iterator(mmaped_file) -> Iterable[int]:
    for i in range(len(mmaped_file)):
        yield mmaped_file[i]


class TextFile(object):
    def __init__(self, filename):
        self.file = open(filename, "rb")
        self.data = mmap.mmap(
            self.file.fileno(),
            0,
            flags=mmap.MAP_PRIVATE,
            prot=mmap.PROT_READ,
        )

    def __del__(self):
        self.file.close()

    def all_str(self) -> str:
        return self.data.decode("utf-8")

    def all_bytes(self) -> Iterable[bytes]:
        return mmap_iterator(self.data)

    @property
    def length(self):
        return len(self.data)

    def sample_bytes(self, length: int, separator: bytes = b"\n") -> bytes:
        """Take a random substring of the file as a string.

        If length is >= file size, the whole file contents will be returned,
        otherwise returned sample will be at least length bytes long. The sample
        will start on the next byte after the `separator` or at the beginning
        of the file and will end on the `separator` or at the end of the file.

        The data will be decoded into a string. This should work if
        the `separator` is a single-byte character.
        """
        if length >= len(self.data):
            return self.all_bytes()
        approx_start = random.randrange(len(self.data) - length)
        start = self.data.rfind(separator, 0, approx_start)
        if start < 0:
            start = 0

        finish = self.data.find(separator, start + length - len(separator))
        if finish < 0:
            finish = len(self.data)
        else:
            finish += len(separator)

        fragment = self.data[start:finish]
        return fragment

    def sample_str(self, length: int, separator: bytes = b"\n") -> str:
        return self.sample_bytes(length, separator).decode("utf-8")


class ChunkProvider(object):
    def __init__(self, file: TextFile, nchunks: int = 0, size: int = 0):
        self._file = file
        self._nchunks = nchunks
        self._chunk_size = size

    def chunks(self) -> Iterable[Iterable[int]]:
        if (
            self._nchunks <= 0
            or self._chunk_size <= 0
            or self._file.length <= self._nchunks * self._chunk_size
        ):
            yield self._file.all_bytes()
            return

        for _ in range(self._nchunks):
            yield self._file.sample_bytes(self._chunk_size)
