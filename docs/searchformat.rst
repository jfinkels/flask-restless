.. _searchformat:

Making search queries
=====================

Clients can make :http:method:`get` requests on individual instances of a model
(for example, :http:get:`/api/person/1`) and on collections of all instances of
a model (:http:get:`/api/person`). To get all instances of a model which meet
some criteria, clients can make :http:method:`get` requests with a query
parameter specifying a search.

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

To come...
