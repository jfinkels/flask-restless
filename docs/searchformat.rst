.. _searchformat:

.. currentmodule:: flask.ext.restless

Making search queries
=====================

Clients can make :http:method:`get` requests on individual instances of a model
(for example, :http:get:`/api/person/1`) and on collections of all instances of
a model (:http:get:`/api/person`). To get all instances of a model that meet
some criteria, clients can make :http:method:`get` requests with a query
parameter specifying a search. The search functionality in Flask-Restless is
relatively simple, but should suffice for many cases.

Quick examples
--------------

The following are some quick examples of creating search queries with different
types of clients. Find more complete documentation in subsequent sections. In
these examples, each client will search for instances of the model ``Person``
whose names contain the letter "y".

Using the Python `requests <http://docs.python-requests.org/en/latest/>`_
library::

    import requests
    import json

    url = 'http://127.0.0.1:5000/api/person'
    headers = {'Content-Type': 'application/json'}

    filters = [dict(name='name', op='like', val='%y%')]
    params = dict(q=json.dumps(dict(filters=filters)))

    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    print(response.json())

Using `jQuery <http://jquery.com/>`_:

.. sourcecode:: javascript

   var filters = [{"name": "id", "op": "like", "val": "%y%"}];
   $.ajax({
     url: 'http://127.0.0.1:5000/api/person',
     data: {"q": JSON.stringify({"filters": filters})},
     dataType: "json",
     contentType: "application/json",
     success: function(data) { console.log(data.objects); }
   });

Using `curl <http://curl.haxx.se/>`_:

.. sourcecode:: bash

   curl \
     -G \
     -H "Content-type: application/json" \
     -d "q={\"filters\":[{\"name\":\"name\",\"op\":\"like\",\"val\":\"%y%\"}]}" \
     http://127.0.0.1:5000/api/person

The ``examples/`` directory has more complete versions of these examples.

.. _queryformat:

Query format
------------

The query parameter ``q`` must be a JSON string. It can have the following
mappings, all of which are optional:

``filters``
  A list of objects of one of the following forms::

      {"name": <fieldname>, "op": <operatorname>, "val": <argument>}

  or::

      {"name": <fieldname>, "op": <operatorname>, "field": <fieldname>}

  In the first form, ``<operatorname>`` is one of the strings described in the
  :ref:`operators` section, the first ``<fieldname>`` is the name of the field
  of the model to which to apply the operator, ``<argument>`` is a value to be
  used as the second argument to the given operator. In the second form, the
  second ``<fieldname>`` is the field of the model that should be used as the
  second argument to the operator.

  ``<fieldname>`` may alternately specify a field on a related model, if it is
  a string of the form ``<relationname>__<fieldname>``.

  If the field name is the name of a relation and the operator is ``"has"`` or
  ``"any"``, the ``"val"`` argument can be a dictionary with the arguments
  representing another filter to be applied as the argument for ``"has"`` or
  ``"any"``.

  The returned list of matching instances will include only those instances
  that satisfy all of the given filters.

  Filter objects can also be arbitrary Boolean formulas. For example::

      {"or": [<filterobject>, {"and": [<filterobject>, ...]}, ...]}

``limit`` 
  A positive integer which specifies the maximum number of objects to return.

``offset``
  A positive integer which specifies the offset into the result set of the
  returned list of instances.

``order_by``
  A list of objects of the form::

      {"field": <fieldname>, "direction": <directionname>}

  where ``<fieldname>`` is a string corresponding to the name of a field of the
  requested model and ``<directionname>`` is either ``"asc"`` for ascending
  order or ``"desc"`` for descending order.

  ``<fieldname>`` may alternately specify a field on a related model, if it is
  a string of the form ``<relationname>__<fieldname>``.

``group_by``
  A list of objects of the form::

      {"field": <fieldname>}

  where ``<fieldname>`` is a string corresponding to the name of a field of the
  requested model.

  ``<fieldname>`` may alternately specify a field on a related model, if it is
  a string of the form ``<relationname>__<fieldname>``.

  .. versionadded:: 0.16.0

``single``
  A Boolean representing whether a single result is expected as a result of the
  search. If this is ``true`` and either no results or multiple results meet
  the criteria of the search, the server responds with an error message.

If a filter is poorly formatted (for example, ``op`` is set to ``'=='`` but
``val`` is not set), the server responds with :http:statuscode:`400`.

.. versionchanged:: 0.17.0
   Removed the ``disjunction`` mapping in favor of a more robust Boolean
   expression system.

.. _operators:

Operators
---------

The operator strings recognized by the API incude:

* ``==``, ``eq``, ``equals``, ``equals_to``
* ``!=``, ``neq``, ``does_not_equal``, ``not_equal_to``
* ``>``, ``gt``, ``<``, ``lt``
* ``>=``, ``ge``, ``gte``, ``geq``, ``<=``, ``le``, ``lte``, ``leq``
* ``in``, ``not_in``
* ``is_null``, ``is_not_null``
* ``like``
* ``has``
* ``any``

These correspond to SQLAlchemy column operators as defined `here
<http://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.operators.ColumnOperators>`_.

Examples
--------

Consider a ``Person`` model available at the URL ``/api/person``, and suppose
all of the following requests are :http:get:`/api/person` requests with query
parameter ``q``.

Attribute greater than a value
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"age","op":"ge","val":10}]} HTTP/1.1
   Host: example.com

the response will include only those ``Person`` instances that have ``age``
attribute greater than or equal to 10:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 8,
     "total_pages": 3,
     "page": 2,
     "objects":
     [
       {"id": 1, "name": "Jeffrey", "age": 24},
       {"id": 2, "name": "John", "age": 13},
       {"id": 3, "name": "Mary", "age": 18}
     ]
   }

Arbitrary Boolean expression of filters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"or":[{"name":"age","op":"lt","val":10},{"name":"age","op":"gt","val":20}]}]} HTTP/1.1
   Host: example.com

the response will include only those ``Person`` instances that have ``age``
attribute either less than 10 or greater than 20:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 3,
     "total_pages": 1,
     "page": 1,
     "objects":
     [
       {"id": 4, "name": "Abraham", "age": 9},
       {"id": 5, "name": "Isaac", "age": 25},
       {"id": 6, "name": "Job", "age": 37}
     ]
   }

Attribute between two values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"age","op":"ge","val":10},{"name":"age","op":"le","val":20}]} HTTP/1.1
   Host: example.com

the response will include only those ``Person`` instances that have ``age``
attribute between 10 and 20, inclusive:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 2,
     "objects":
     [
       {"id": 2, "name": "John", "age": 13},
       {"id": 3, "name": "Mary", "age": 18}
     ]
   }

Expecting a single result
~~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: javascript

   GET /api/person?q={"filters":[{"name":"id","op":"eq","val":1}],"single":true} HTTP/1.1
   Host: example.com

the response will include only the sole ``Person`` instance with ``id`` equal
to 1:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {"id": 1, "name": "Jeffrey", "age": 24}

In the case that the search would return no results or more than one result, an
error response is returned instead:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"age","op":"ge","val":10}],"single":true} HTTP/1.1
   Host: example.com

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   {"message": "Multiple results found"}

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"id","op":"eq","val":-1}],"single":true} HTTP/1.1
   Host: example.com

.. sourcecode:: http

   HTTP/1.1 404 Bad Request

   {"message": "No result found"}

Comparing two attributes
~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"age","op":"ge","field":"height"}]} HTTP/1.1
   Host: example.com

the response will include only those ``Person`` instances that have ``age``
attribute greater than or equal to the value of the ``height`` attribute:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 2,
     "objects":
     [
       {"id": 1, "name": "John", "age": 80, "height": 65},
       {"id": 2, "name": "Mary", "age": 73, "height": 60}
     ]
   }

Comparing attribute of a relation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"computers__manufacturer","op":"any","val":"Apple"}],"single":true} HTTP/1.1
   Host: example.com

response will include only those ``Person`` instances that are related to any
``Computer`` model that is manufactured by Apple:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 2,
     "objects":
       {
         "id": 1,
         "name": "John",
         "computers": [
           { "id": 1, "manufacturer": "Dell", "model": "Inspiron 9300"},
           { "id": 2, "manufacturer": "Apple", "model": "MacBook"}
         ]
       },
       {
         "id": 2,
         "name": "Mary",
         "computers": [
           { "id": 3, "manufacturer": "Apple", "model": "iMac"}
         ]
       }
     ]
   }

Using ``has`` and ``any``
~~~~~~~~~~~~~~~~~~~~~~~~~

Use the ``has`` and ``any`` operators to search for instances by fields on
related instances. For example, you can search for all ``Person`` instances
that have a related ``Computer`` with a certain ID number by using the ``any``
operator. For another example, you can search for all ``Computer`` instances
that have an owner with a certain name by using the ``has`` operator. In
general, use the ``any`` operator if the relation is a list of objects and use
the ``has`` operator if the relation is a single object. For more information,
see the SQLAlchemy documentation.

On request:

.. sourcecode:: http

   GET /api/person?q={"filters":[{"name":"computers","op":"any","val":{"name":"id","op":"gt","val":1}}]} HTTP/1.1
   Host: example.com

the response will include only those ``Person`` instances that have a related
``Computer`` instance with ``id`` field of value greater than 1:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 2,
     "objects":
     [
       {"id": 1, "name": "John", "age": 80, "height": 65, "computers": [...]},
       {"id": 2, "name": "Mary", "age": 73, "height": 60, "computers": [...]}
     ]
   }

On request:

.. sourcecode:: http

   GET /api/computers?q={"filters":[{"name":"owner","op":"has","val":{"name":"vendor","op":"ilike","val":"%John%"}}]} HTTP/1.1
   Host: example.com

the response will include only those ``Computer`` instances that have an owner
with ``name`` field that includes ``'John'``:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 2,
     "objects":
     [
       {"id": 1, "name": "pluto", vendor="Apple", ...},
       {"id": 2, "name": "jupiter", vendor="Dell", ...}
     ]
   }
