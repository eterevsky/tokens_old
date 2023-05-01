def stream_file(filename):
    with open(filename, "rb") as file:
        while True:
            byte = file.read(1)
            if not byte:
                return
            yield byte[0]
