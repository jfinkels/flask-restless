.. _searchformat:

Making search queries
=====================

Clients can make :http:method:`get` requests on individual instances of a model
(for example, :http:get:`/api/person/1`) and on collections of all instances of
a model (:http:get:`/api/person`). To get all instances of a model which meet
some criteria, clients can make :http:method:`get` requests with a query
parameter specifying a search. The search functionality in Flask-Restless is
relatively simple, but should suffice for many cases.

If the ``allow_patch_many`` keyword argument is set to ``True`` when calling
the :meth:`APIManager.create_api` function, then :http:method:`patch` requests
will accept search queries as well. In this case, every instance of the model
which meets the criteria of the search will be patched. For more information,
see :ref:`allowpatchmany`.

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
  second ``<fieldname>`` is the field of the model which should be used as the
  second argument to the operator.

  ``<fieldname>`` may alternately specify a field on a related model, if it is
  a string of the form ``<relationname>__<fieldname>``.

  The returned list of matching instances will include only those instances
  which satisfy all of the given filters.

``limit`` 
  A positive integer which specified the maximum number of objects to return.

``offset``
  A positive integer which specifies the offset into the result set of the
  returned list of instances.

``order_by``
  A list of objects of the form::

      {"field": <fieldname>, "direction": <directionname>}

  where ``<fieldname>`` is a string corresponding to the name of a field of the
  requested model and ``<directionname>`` is either ``"asc"`` for ascending
  order or ``"desc"`` for descending order.

``single``
  A boolean representing whether a single result is expected as a result of the
  search. If this is ``true`` and either no results or multiple results meet
  the criteria of the search, the server responds with an error message.

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

Evaluating functions
--------------------

Instead of responding with the list of instances of the model which meet the
specified search criteria, the client can instead request the result of
evaluating a SQL function on some field of the model.

If the following mapping appears in addition to the mappings specified in
:ref:`queryformat` for the query parameter ``q``, then the result of evaluating
functions will be returned instead of the list of matching instances:

``functions``
  A list of objects of the form::

      {"name": <functionname>, "field":, <fieldname>}

  where ``<functionname>`` is a string representing a SQL function to apply to
  the results, and ``<fieldname>`` is the name of the field of the model on
  which the function will be executed.

  The function will be evaluated using SQLAlchemy's `func
  <http://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.expression.func>`_
  object.

Examples
--------

Consider a ``Person`` model available at the URL ``/api/person``, and suppose
all of the following requests are :http:get:`/api/person` requests with query
parameter ``q``.

Attribute greater than a value
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If query parameter ``q`` has the value

.. sourcecode:: javascript

   {"filters": [{"name": "age", "op": "ge", "val": 10}]}

(represented as a string), then the response will include only those ``Person``
instances which have ``age`` attribute greater than or equal to 10.

.. sourcecode:: http

   HTTP/1.1 200 OK

   { "objects":
     [
       {"id": 1, "name": "Jeffrey", "age": 24},
       {"id": 2, "name": "John", "age": 13},
       {"id": 3, "name": "Mary", "age": 18}
     ]
   }

Attribute between two values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If query parameter ``q`` has the value

.. sourcecode:: javascript

   { "filters":
     [
       {"name": "age", "op": "ge", "val": 10},
       {"name": "age", "op": "le", "val": 20}
     ]
   }

(represented as a string), then the response will include only those
``Person`` instances which have ``age`` attribute between 10 and 20,
inclusive.

.. sourcecode:: http

   HTTP/1.1 200 OK

   { "objects":
     [
       {"id": 2, "name": "John", "age": 13},
       {"id": 3, "name": "Mary", "age": 18}
     ]
   }

Expecting a single result
~~~~~~~~~~~~~~~~~~~~~~~~~

If query parameter ``q`` has the value

.. sourcecode:: javascript

   {
     "single": true,
     "filters":
     [
       {"name": "id", "op": "eq", "val": 1}
     ]
   }

(represented as a string), then the response will the sole ``Person`` instance
with ``id`` equal to 1.

.. sourcecode:: http

   HTTP/1.1 200 OK

   {"id": 1, "name": "Jeffrey", "age": 24}

In the case that the search would return no results or more than one result, an
error response is returned instead.

.. sourcecode:: javascript

   {
     "single": true,
     "filters":
     [
       {"name": "age", "op": "ge", "val": 10}
     ]
   }

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   {"message": "Multiple results found"}

.. sourcecode:: javascript

   {
     "single": true,
     "filters":
     [
       {"name": "id", "op": "eq", "val": -1}
     ]
   }

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   {"message": "No result found"}

Comparing two attributes
~~~~~~~~~~~~~~~~~~~~~~~~

If query parameter ``q`` has the value

.. sourcecode:: javascript

   {"filters": [{"name": "age", "op": "ge", "field": "height"}]}

(represented as a string), then the response will include only those ``Person``
instances which have ``age`` attribute greater than or equal to the value of
the ``height`` attribute.

.. sourcecode:: http

   HTTP/1.1 200 OK

   { "objects":
     [
       {"id": 1, "name": "John", "age": 80, "height": 65},
       {"id": 2, "name": "Mary", "age": 73, "height": 60}
     ]
   }

Comparing attribute of a relation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If query parameter ``q`` has the value

.. sourcecode:: javascript

   { "filters":
     [
       {"name": "computers__manufacturer", "val": "Dell", "op": "any"}
     ]
   }

(represented as a string), then the response will include only those ``Person``
instances which are related to any ``Computer`` model which is manufactured by
Apple.

.. sourcecode:: http

   HTTP/1.1 200 OK

   { "objects": [
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
