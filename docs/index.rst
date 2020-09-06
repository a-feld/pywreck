pywreck
=======

A compact HTTP/1.1 client that's "good enough" for many cases. The code has no dependencies, is a single source file, and implements no advanced parsing or error handling. For more detailed parameter descriptions, see the :doc:`api` page.

Quickstart
==========

Lowercased HTTP methods are available for use directly on the :py:mod:`pywreck` module.
Additionally, :py:meth:`pywreck.request` is provided for custom HTTP methods.

.. code-block:: python

    import asyncio
    import pywreck

    async def main():
        response = await pywreck.get("www.example.com", "/")
        print(response)

    asyncio.run(main())


.. toctree::
    :hidden:

    api
