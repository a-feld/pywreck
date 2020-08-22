async def read_request(reader):
    request = []
    content_length = 0
    while True:
        line = await reader.readline()
        request.append(line)
        if not line.rstrip():
            break

        if line.lower().startswith(b"content-length"):
            content_length = int(line[15:])

    data = await reader.readexactly(content_length)
    request.append(data)
    request = b"".join(request)
    return request


async def handle_echo(reader, writer):
    output = await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(f"content-length: {len(output)}\r\n\r\n".encode("latin1"))
    writer.write(output)
    await writer.drain()
    writer.close()


async def handle_multi_response_headers(reader, writer):
    await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"foo:1\r\n")
    writer.write(b"foo:2\r\n")
    writer.write(b"\r\n")
    await writer.drain()
    writer.close()


async def handle_chunked(reader, writer):
    await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"transfer-encoding: chunked\r\n")
    writer.write(b"\r\n")
    await writer.drain()

    chunks = [b"chunk_foo", b"chunk_bar", b""]
    for chunk in chunks:
        hex_len = b"%x\r\n" % len(chunk)
        writer.write(hex_len)
        writer.write(chunk + b"\r\n")
        await writer.drain()


async def handle_cookies(reader, writer):
    await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"set-cookie: foo=bar\r\n")
    writer.write(b"set-cookie: boo=baz\r\n")
    writer.write(b"\r\n")
