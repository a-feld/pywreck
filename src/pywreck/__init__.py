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
from types import TracebackType
from typing import Dict, Optional, Type, Union, cast

try:
    with open(os.path.join(os.path.dirname(__file__), "version.txt")) as f:
        __version__ = f.read()
except Exception:  # pragma: no cover
    __version__ = "0.0.0"  # pragma: no cover


@dataclass(frozen=True)
class Response:
    """HTTP Response Container"""

    status: int
    headers: Dict[str, str]
    data: bytes


class Connection:
    """Streaming connection wrapper

    Provides an interface to make HTTP requests via a streaming connection.

    It is not recommended to instantiate :class:`Connection` objects directly;
    use :meth:`Connection.create()` instead.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        lock: asyncio.Lock,
        host: str,
        close_timeout: Optional[float],
    ):
        self._reader = reader
        self._writer = writer
        self._lock = lock
        self._host = host
        self._close_timeout = close_timeout

    async def _readline_ascii(self) -> str:
        result = await self._reader.readline()
        return result.decode("latin1")

    def _write_ascii(self, data: str) -> None:
        return self._writer.write(data.encode("latin1"))

    @classmethod
    async def create(
        cls,
        host: str,
        port: int = 443,
        ssl: Union[bool, ssl.SSLContext] = True,
        close_timeout: Optional[float] = 5.0,
    ) -> "Connection":
        """Create a Connection

        :param host: Host string controlling both the DNS request and the
            host header.
        :type host: str
        :param port: (optional) The TCP port used for the connection.
            Default: 443
        :type port: int
        :param ssl: (optional) Indicates if SSL is to be used in
            establishing the connection. Also accepts an SSLContext object.
            Default: True
        :type ssl: bool or ssl.SSLContext
        :param close_timeout: (optional) The amount of time to wait in seconds
            for the connection to close before forcing the connection to close
            via TCP RST. Default: 5 seconds
        :type close_timeout: float

        :rtype: Connection
        """
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl)
        return Connection(reader, writer, asyncio.Lock(), host, close_timeout)

    async def __aenter__(self) -> "Connection":
        return self

    async def request(
        self,
        method: str,
        uri: str,
        payload: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = 5.0,
    ) -> Response:
        """Make an HTTP request

        Drives a full request/response cycle using the HTTP/1.1 protocol.

        No exception handling is done for:

        * Malformed HTTP/1.1 responses
        * Network communication errors

        The raw exceptions will be raised for any violation of HTTP/1.1
        protocol.

        :param method: HTTP method string send in the request line.
        :type method: str
        :param uri: Request-Uniform Resource Identifier (URI), usually
            the absolute path to the resource being requested.
        :type uri: str
        :param payload: (optional) The encoded HTTP request body bytes to be
            sent. Default: b""
        :type payload: bytes
        :param headers: (optional) A dictionary of headers to be sent
            with the request. Default: {}
        :type headers: dict
        :param timeout: (optional) Timeout in seconds for the request.
            Default: 5 seconds.
        :type timeout: float

        :rtype: Response
        """
        coro = self._request(method, uri, payload, headers)
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    async def _request(
        self,
        method: str,
        uri: str,
        payload: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        # Since the connection can be a shared resource, we must ensure
        # exclusive access for the duration of the request/response cycle
        async with self._lock:
            reader, writer = self._reader, self._writer
            request = f"{method} {uri} HTTP/1.1\r\n"
            self._write_ascii(request)

            request_headers = {
                "host": self._host,
                "user-agent": f"pywreck/{__version__}",
            }
            if payload:
                request_headers["content-length"] = str(len(payload))

            if headers:
                request_headers.update(headers)

            for header_name, header_value in request_headers.items():
                self._write_ascii(f"{header_name}:{header_value}\r\n")

            # Finish request metadata section
            writer.write(b"\r\n")

            # Send payload
            writer.write(payload)

            response_line = await self._readline_ascii()
            status = int(response_line.split(" ", 2)[1])

            response_headers: Dict[str, str] = {}
            content_length = 0
            chunked = False

            while True:
                header_line = await self._readline_ascii()
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
                    part = await reader.readexactly(content_length + 2)
                    if not content_length:
                        break
                    response_chunks.append(part[:-2])

                response_data = b"".join(response_chunks)
            else:
                response_data = await reader.readexactly(content_length)

        return Response(status, response_headers, response_data)

    async def __aexit__(
        self,
        exc: Optional[Type[BaseException]],
        value: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the connection"""
        coro = self._close()
        timeout = self._close_timeout
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    async def _close(self) -> None:
        writer = self._writer
        writer.close()
        try:
            await writer.wait_closed()
        finally:
            cast(asyncio.WriteTransport, writer.transport).abort()


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
    :param timeout: (optional) Timeout in seconds for the request.
        Default: 5 seconds.
    :type timeout: float
    :param ssl: (optional) Indicates if SSL is to be used in
        establishing the connection. Also accepts an SSLContext object.
        Default: True
    :type ssl: bool or ssl.SSLContext

    :rtype: Response
    """

    async def _request() -> Response:
        async with await Connection.create(
            host,
            port,
            ssl=ssl,
            close_timeout=None,
        ) as connection:
            return await connection.request(
                method,
                uri,
                payload,
                headers,
                None,
            )

    coro = _request()
    if timeout is not None:
        return await asyncio.wait_for(coro, timeout=timeout)
    return await coro


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
