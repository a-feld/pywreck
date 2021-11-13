.. _api:

API Reference
=============

Response
--------

Holds an HTTP response

.. autoclass:: pywreck.Response

Request API
-----------

Use these APIs to open a connection, make a request, and close the connection.

.. autofunction:: pywreck.request

HTTP Method APIs
++++++++++++++++

When using HTTP method functions directly, the method string does not have to be specified in the function call parameters.

Supported methods:

* get
* head
* post
* put
* delete

Connection API
--------------

.. autoclass:: pywreck.Connection
