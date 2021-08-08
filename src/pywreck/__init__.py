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
import os.path
import ssl
from dataclasses import dataclass
from typing import Dict, Optional, Union

try:
    with open(os.path.join(os.path.dirname(__file__), "version.txt")) as f:
        __version__ = f.read()
except Exception:  # pragma: no cover
    __version__ = "0.0.0"  # pragma: no cover


class _HttpReader:
    def __init__(self, reader: asyncio.StreamReader, timeout: Optional[float]) -> None:
        self.reader = reader
        self.timeout = timeout

    async def readline(self) -> str:
        coro = self.reader.readline()
        result = await asyncio.wait_for(coro, timeout=self.timeout)
        return result.decode("latin1")

    async def readexactly(self, n: int) -> bytes:
        coro = self.reader.readexactly(n)
        return await asyncio.wait_for(coro, timeout=self.timeout)

    async def readuntil(self, separator: bytes) -> bytes:
        coro = self.reader.readuntil(separator)
        return await asyncio.wait_for(coro, timeout=self.timeout)


class _HttpWriter:
    def __init__(self, writer: asyncio.StreamWriter, timeout: Optional[float]) -> None:
        self.writer = writer
        self.timeout = timeout
        self.transport = writer.transport

    def write(self, data: bytes) -> None:
        return self.writer.write(data)

    def write_ascii(self, data: str) -> None:
        return self.writer.write(data.encode("latin1"))

    def close(self) -> None:
        return self.writer.close()

    async def wait_closed(self) -> None:
        coro = self.writer.wait_closed()
        return await asyncio.wait_for(coro, timeout=self.timeout)


@dataclass
class Response:
    """HTTP Response Container"""

    status: int
    headers: Dict[str, str]
    data: bytes


async def request(
    method: str,
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    """Make a full HTTP request

    Drives a full request/response cycle using the HTTP/1.1 protocol.

    No exception handling is done for:

    * Malformed HTTP/1.1 responses
    * Network communication errors

    The raw exceptions will be raised for any violation of HTTP/1.1
    protocol.

    :param method: HTTP method string send in the request line.
    :type method: str
    :param host: Host string controlling both the DNS request and the
        host header.
    :type host: str
    :param uri: Request-Uniform Resource Identifier (URI), usually
        the absolute path to the resource being requested.
    :type uri: str
    :param payload: The encoded HTTP request body bytes to be sent.
    :type payload: bytes
    :param headers: (optional) A dictionary of headers to be sent
        with the request. Default: {}
    :type headers: dict
    :param port: (optional) The TCP port used for the connection. Default: 443
    :type port: int
    :param timeout: (optional) Timeout in seconds, used when retrieving a response.
        Default: 5 seconds.
    :type timeout: float
    :param ssl: (optional) Indicates if SSL is to be used in
        establishing the connection. Also accepts an SSLContext object.
        Default: True
    :type ssl: bool or ssl.SSLContext

    :rtype: Response
    """
    _reader, _writer = await asyncio.open_connection(host, port, ssl=ssl)
    reader, writer = _HttpReader(_reader, timeout), _HttpWriter(_writer, timeout)

    try:
        request = f"{method} {uri} HTTP/1.1\r\n"
        writer.write_ascii(request)

        request_headers = {"host": host, "user-agent": f"pywreck/{__version__}"}
        if payload:
            request_headers["content-length"] = str(len(payload))

        if headers:
            request_headers.update(headers)

        for header_name, header_value in request_headers.items():
            writer.write_ascii(
                "{header_name}:{header_value}\r\n".format(
                    header_name=header_name, header_value=header_value
                )
            )

        # Finish request metadata section
        writer.write(b"\r\n")

        # Send payload
        writer.write(payload)

        response_line = await reader.readline()
        status = int(response_line.split(" ", 2)[1])

        response_headers: Dict[str, str] = {}
        content_length = 0
        chunked = False

        while True:
            header_line = await reader.readline()
            header_line = header_line.rstrip()
            if not header_line:
                break

            header_name, header_value = header_line.split(":", 1)
            header_name = header_name.rstrip().lower()
            header_value = header_value.lstrip()

            if header_name in response_headers:
                separator = "," if header_name != "set-cookie" else ";"
                response_headers[header_name] += separator + header_value
            else:
                response_headers[header_name] = header_value

        if method != "HEAD":
            if "content-length" in response_headers:
                content_length = int(response_headers["content-length"])

            chunked = response_headers.get("transfer-encoding", "") == "chunked"

        if chunked:
            response_chunks = []
            while True:
                chunk_len_bytes = await reader.readuntil(b"\r\n")
                content_length = int(chunk_len_bytes.rstrip(), 16)
                if not content_length:
                    break
                part = await reader.readexactly(content_length + 2)
                response_chunks.append(part[:-2])

            response_data = b"".join(response_chunks)
        else:
            response_data = await reader.readexactly(content_length)

        return Response(status, response_headers, response_data)

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):
            assert isinstance(writer.transport, asyncio.WriteTransport)
            writer.transport.abort()


async def get(
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    return await request("GET", host, uri, payload, headers, port, timeout, ssl)


async def head(
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    return await request("HEAD", host, uri, payload, headers, port, timeout, ssl)


async def post(
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    return await request("POST", host, uri, payload, headers, port, timeout, ssl)


async def put(
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    return await request("PUT", host, uri, payload, headers, port, timeout, ssl)


async def delete(
    host: str,
    uri: str,
    payload: bytes = b"",
    headers: Optional[Dict[str, str]] = None,
    port: int = 443,
    timeout: Optional[float] = 5.0,
    ssl: Union[bool, ssl.SSLContext] = True,
) -> Response:
    return await request("DELETE", host, uri, payload, headers, port, timeout, ssl)
