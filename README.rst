pywreck
=======

A small, not so great async Python HTTP client.

This HTTP client does not implement any error / exception handling. If the server the client is talking to deviates from the HTTP spec, this code will behave in unexpected ways. Network errors? Those are unhandled too!

Usage
-----

.. code-block:: python

    import asyncio
    import pywreck

    async def main():
        response = await pywreck.get("www.example.com", "/")
        print(response)

    asyncio.run(main())

Why?
----

Eh, why not? Sometimes you just need a small async HTTP client with no dependencies -- no batteries included.
