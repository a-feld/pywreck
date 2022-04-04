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
import functools
import socket

import pytest

import pywreck

from .handlers import (
    handle_chunked,
    handle_cookies,
    handle_echo,
    handle_fin,
    handle_multi_response_headers,
    handle_rst,
)


@pytest.fixture(scope="session")
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


@pytest.fixture
def handler(request):
    return request.param


@pytest.fixture
def port(loop, handler):
    # Get a random port
    s = socket.socket()
    s.bind(("", 0))
    _port = s.getsockname()[1]
    s.close()

    server = loop.run_until_complete(asyncio.start_server(handler, "127.0.0.1", _port))
    yield _port
    server.close()
    loop.create_task(server.wait_closed())

    tasks_to_shutdown = asyncio.all_tasks(loop=loop)
    loop.run_until_complete(
        asyncio.wait_for(
            asyncio.gather(*tasks_to_shutdown),
            timeout=0.1,
        )
    )


@pytest.mark.parametrize(
    "method",
    ("get", "head", "post", "put", "delete"),
)
@pytest.mark.parametrize("handler", (handle_echo,), indirect=True)
def test_basic(loop, port, method):
    response = loop.run_until_complete(
        getattr(pywreck, method)(
            "localhost",
            "/",
            headers={"user-agent": "pywreck test, yo!"},
            port=port,
            ssl=False,
            timeout=0.2,
        )
    )
    assert response.status == 200

    data = response.data
    expected_data = (
        f"{method.upper()} / HTTP/1.1\r\n"
        "host:localhost\r\n"
        "user-agent:pywreck test, yo!\r\n"
        "\r\n"
    ).encode("utf-8")

    assert response.headers == {"content-length": str(len(expected_data))}
    if method == "head":
        assert not data
    else:
        assert data == expected_data


@pytest.mark.parametrize("handler", (handle_echo,), indirect=True)
def test_multiple_requests_on_a_single_connection(loop, port):
    def validate_response(response):
        assert response.status == 200
        data = response.data
        expected_data = (
            "GET / HTTP/1.1\r\n"
            "host:localhost\r\n"
            "user-agent:pywreck test, yo!\r\n"
            "\r\n"
        ).encode("utf-8")

        assert response.headers == {"content-length": str(len(expected_data))}
        assert data == expected_data

    async def _async():
        connection = await pywreck.Connection.create(
            "localhost",
            port=port,
            ssl=False,
        )

        async with connection:
            for _ in range(2):
                response = await connection.request(
                    "GET",
                    "/",
                    headers={"user-agent": "pywreck test, yo!"},
                )
                validate_response(response)

    loop.run_until_complete(_async())


@pytest.mark.parametrize("handler", (handle_echo,), indirect=True)
def test_payload(loop, port):
    response = loop.run_until_complete(
        pywreck.post(
            "localhost",
            "/foo",
            headers={"user-agent": "pywreck test, yo!"},
            payload=b"payload, yo!",
            port=port,
            ssl=False,
            timeout=0.2,
        )
    )
    assert response.status == 200
    expected_data = (
        b"POST /foo HTTP/1.1\r\n"
        b"host:localhost\r\n"
        b"user-agent:pywreck test, yo!\r\n"
        b"content-length:12\r\n"
        b"\r\n"
        b"payload, yo!"
    )
    assert response.data == expected_data


@pytest.mark.parametrize(
    "method",
    ("", "get", "post", "put", "delete"),
)
@pytest.mark.parametrize("handler", (handle_echo,), indirect=True)
def test_default_headers_and_payload(loop, port, method):
    if not method:
        method = "GET"
        f = functools.partial(pywreck.request, method, timeout=None)
    else:
        f = getattr(pywreck, method)

    response = loop.run_until_complete(f("localhost", "/", port=port, ssl=False))
    assert response.status == 200
    data = response.data.split(b"\r\n")
    assert len(data) == 5
    assert data[-2:] == [b"", b""]
    assert data[:2] == [
        f"{method.upper()} / HTTP/1.1".encode("latin1"),
        b"host:localhost",
    ]
    assert data[2].startswith(b"user-agent:pywreck/")


@pytest.mark.parametrize("handler", (handle_multi_response_headers,), indirect=True)
def test_multi_line_response_header(loop, port):
    response = loop.run_until_complete(
        pywreck.get("localhost", "/", port=port, ssl=False, timeout=0.2)
    )
    assert response.status == 200
    assert response.headers == {"foo": "1:1,2:2"}
    assert response.data == b""


@pytest.mark.parametrize("handler", (handle_cookies,), indirect=True)
def test_cookies(loop, port):
    response = loop.run_until_complete(
        pywreck.get("localhost", "/", port=port, ssl=False, timeout=0.2)
    )
    assert response.status == 200
    assert response.headers == {"set-cookie": "foo=bar;boo=baz"}


@pytest.mark.parametrize("handler", (handle_chunked,), indirect=True)
def test_chunked(loop, port):
    async def _async():
        connection = await pywreck.Connection.create(
            "localhost",
            port=port,
            ssl=False,
        )

        async with connection:
            for _ in range(2):
                response = await connection.request(
                    "GET",
                    "/",
                    headers={"user-agent": "pywreck test, yo!"},
                    timeout=None,
                )

                assert response.status == 200
                assert response.headers == {"transfer-encoding": "chunked"}
                assert response.data == (b"*" * 16 + b"foo")

    loop.run_until_complete(_async())


@pytest.mark.parametrize("handler", (handle_rst,), indirect=True)
def test_transport_rst(loop, port):
    """A server may hard-close a connection with a RST"""
    with pytest.raises(ConnectionResetError):
        loop.run_until_complete(
            pywreck.get("localhost", "/", port=port, ssl=False, timeout=0.2)
        )


@pytest.mark.parametrize("handler", (handle_fin,), indirect=True)
def test_transport_fin(loop, port):
    """A server will sometimes close a connection gracefully with a FIN before
    a response is started"""
    with pytest.raises(IndexError):
        loop.run_until_complete(
            pywreck.get("localhost", "/", port=port, ssl=False, timeout=0.2)
        )
