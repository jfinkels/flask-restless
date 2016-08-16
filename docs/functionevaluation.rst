Function evaluation
===================

*This section describes behavior that is not part of the JSON API specification.*

If the ``allow_functions`` keyword argument to :meth:`.APIManager.create_api`
is set to ``True`` when creating an API for a model, then the endpoint
``/api/eval/person`` will be made available for :http:method:`get`
requests. This endpoint responds to requests for evaluation of SQL functions on
*all* instances the model.

If the client specifies the ``functions`` query parameter, it must be a
`percent-encoded`_ list of :dfn:`function objects`, as described below.

A :dfn:`function object` is a JSON object. A function object must be of the
form ::

   {"name": <function_name>, "field": <field_name>}

where ``<function_name>`` is the name of a SQL function as provided by
SQLAlchemy's |func|_ object.

For example, to get the average age of all people in the database,

.. sourcecode:: http

   GET /api/eval/person?functions=[{"name":"avg","field":"age"}] HTTP/1.1
   Host: example.com
   Accept: application/json

The response will be a JSON object with a single element, ``data``, containing
a list of the results of all the function evaluations requested by the client,
in the same order as in the ``functions`` query parameter. For example, to get
the sum and the average ages of all people in the database, the request

.. sourcecode:: http

   GET /api/eval/person?functions=[{"name":"avg","field":"age"},{"name":"sum","field":"age"}] HTTP/1.1
   Host: example.com
   Accept: application/json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/json

   [15.0, 60.0]

.. admonition:: Example

   To get the total number of resources in the collection (that is, the number
   of instances of the model), you can use the function object

   .. sourcecode:: json

      {"name": "count", "field": "id"}

   Then the request

   .. sourcecode:: http

      GET /api/eval/person?functions=[{"name":"count","field":"id"}] HTTP/1.1
      Host: example.com
      Accept: application/json

   yields the response

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "data": [42]
      }

The function evaluation endpoint also respects filtering query
parameters. Specifically, filters are applied to the model *before* the
function evaluation is performed, so you can apply a function to a subset of
resources. See :doc:`filtering` for more information.

.. versionchanged:: 1.0.0b2

   Adds ability to use filters in function evaluation.

.. |func| replace:: ``func``
.. _func: https://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.expression.func
.. _percent-encoded: https://en.wikipedia.org/wiki/Percent-encoding#Percent-encoding_the_percent_character
