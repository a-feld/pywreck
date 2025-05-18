# Copyright 2020 Allan Feldman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio

SHUTDOWN_EVENTS: list[asyncio.Event] = []


async def read_request(reader: asyncio.StreamReader) -> bytes:
    request: list[bytes] = []
    content_length = 0

    while True:
        line = await asyncio.wait_for(
            reader.readline(),
            timeout=0.1,
        )
        request.append(line)
        if not line.rstrip():
            break

        if line.lower().startswith(b"content-length"):
            content_length = int(line[15:])

    data = await asyncio.wait_for(
        reader.readexactly(content_length),
        timeout=0.1,
    )
    request.append(data)

    return b"".join(request)


async def handle_echo(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    while True:
        output = await read_request(reader)
        if not output:
            break
        writer.write(b"HTTP/1.1 200 OK\r\n")
        writer.write(f"content-length: {len(output)}\r\n\r\n".encode("latin1"))
        writer.write(output)
        await writer.drain()

    writer.close()
    await writer.wait_closed()


async def handle_multi_response_headers(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"foo:1:1\r\n")
    writer.write(b"foo:2:2\r\n")
    writer.write(b"\r\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def handle_chunked(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    while True:
        output = await read_request(reader)
        if not output:
            break

        writer.write(b"HTTP/1.1 200 OK\r\n")
        writer.write(b"transfer-encoding: chunked\r\n")
        writer.write(b"\r\n")
        await writer.drain()

        chunks = [b"*" * 16, b"foo", b""]
        for chunk in chunks:
            hex_len = b"%x\r\n" % len(chunk)
            writer.write(hex_len)
            writer.write(chunk + b"\r\n")
            await writer.drain()

    writer.close()
    await writer.wait_closed()


async def handle_cookies(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    await read_request(reader)
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"set-cookie: foo=bar\r\n")
    writer.write(b"set-cookie: boo=baz\r\n")
    writer.write(b"\r\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def handle_rst(
    _reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    writer.transport.abort()


async def handle_fin(
    _reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    # EOF triggers TCP FIN
    writer.transport.write_eof()

    # Force a context switch
    shutdown_event = asyncio.Event()
    SHUTDOWN_EVENTS.append(shutdown_event)
    await shutdown_event.wait()

    # Close the socket
    writer.close()
    await writer.wait_closed()
