
pywreck
=======

|ci| |coverage| |docs| |black|

.. |ci| image:: https://img.shields.io/github/workflow/status/a-feld/pywreck/CI/main
   :target: https://github.com/a-feld/pywreck/actions/workflows/ci.yml

.. |coverage| image:: https://img.shields.io/codecov/c/github/a-feld/pywreck/main
    :target: https://codecov.io/gh/a-feld/pywreck

.. |docs| image:: https://img.shields.io/badge/docs-available-brightgreen.svg
    :target: https://a-feld.github.io/pywreck

.. |black| image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black

A small, not so great async Python HTTP client.

`API documentation is available here! <https://a-feld.github.io/pywreck>`_

This HTTP client does not implement any error / exception handling. If the server the client is talking to deviates from the HTTP spec, this code will behave in unexpected ways. Network errors? Those are unhandled too!

Usage
-----

.. code-block:: python

    response = await pywreck.get("www.example.com", "/")
    print(response.status, response.headers, response.data)

Why?
----

Eh, why not? Sometimes you just need a small async HTTP client with no dependencies -- no batteries included.
