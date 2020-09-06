pywreck
=======

A compact HTTP/1.1 client that's "good enough" for many cases. The code has no dependencies, is a single source file, and implements no advanced parsing or error handling. For more detailed parameter descriptions, see the :doc:`api` page.

Quickstart
==========

Lowercased HTTP methods are available for use directly on the :py:mod:`pywreck` module.
Additionally, :py:meth:`pywreck.request` is provided for custom HTTP methods.

.. code-block:: python

    response = await pywreck.get("www.example.com", "/")
    print(response.status, response.headers, response.data)


.. toctree::
    :hidden:

    api
