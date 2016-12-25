Filtering
=========

Requests that would normally return a collection of resources can be filtered
so that only a subset of the resources are returned in a response. If the
client specifies the ``filter[objects]`` query parameter, it must be a
`URL encoded`_ JSON list of :dfn:`filter objects`, as described below.

.. _URL encoded: https://en.wikipedia.org/wiki/Percent-encoding

Quick client examples for filtering
-----------------------------------

The following are some quick examples of making filtered :http:method:`get`
requests from different types of clients. More complete documentation is in
subsequent sections. In these examples, each client will filter by instances of
the model ``Person`` whose names contain the letter "y".

Using the Python `requests`_ library::

    import requests
    import json

    url = 'http://127.0.0.1:5000/api/person'
    headers = {'Accept': 'application/vnd.api+json'}

    filters = [dict(name='name', op='like', val='%y%')]
    params = {'filter[objects]': json.dumps(filters)}

    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    print(response.json())

Using `jQuery`_:

.. sourcecode:: javascript

   var filters = [{"name": "id", "op": "like", "val": "%y%"}];
   $.ajax({
     data: {"filter[objects]": JSON.stringify(filters)},
     headers: {
       "Accept": JSONAPI_MIMETYPE
     },
     success: function(data) { console.log(data.objects); },
     url: 'http://127.0.0.1:5000/api/person'
   });

Using `curl`_:

.. sourcecode:: bash

   curl \
     -G \
     -H "Accept: application/vnd.api+json" \
     -d "filter[objects]=[{\"name\":\"name\",\"op\":\"like\",\"val\":\"%y%\"}]" \
     http://127.0.0.1:5000/api/person

The :file:`examples/` directory has more complete versions of these examples.

.. _requests: http://docs.python-requests.org/en/latest/
.. _jQuery: http://jquery.com/
.. _curl: http://curl.haxx.se/

Filter objects
--------------

A :dfn:`filter object` is a JSON object. Filter objects are defined recursively
as follows. A filter object may be of the form ::

   {"name": <field_name>, "op": <unary_operator>}

where ``<field_name>`` is the name of a field on the model whose instances are
being fetched and ``<unary_operator>`` is the name of one of the unary
operators supported by Flask-Restless. For example,

.. sourcecode:: json

   {"name": "birthday", "op": "is_null"}

A filter object may be of the form ::

   {"name": <field_name>, "op": <binary_operator>, "val": <argument>}

where ``<binary_operator>`` is the name of one of the binary operators
supported by Flask-Restless and ``<argument>`` is the second argument to that
binary operator. For example,

.. sourcecode:: json

   {"name": "age", "op": "gt", "val": 23}

A filter object may be of the form ::

   {"name": <field_name>, "op": <binary_operator>, "field": <field_name>}

The ``field`` element indicates that the second argument to the binary operator
should be the value of that field. For example, to filter by resources that
have a greater width than height,

.. sourcecode:: json

   {"name": "width", "op": "gt", "field": "height"}

A filter object may be of the form ::

   {"name": <relation_name>, "op": <relation_operator>, "val": <filter_object>}

where ``<relation_name>`` is the name of a relationship on the model whose
resources are being fetched, ``<relation_operator>`` is either ``"has"``, for a
to-one relationship, or ``"any"``, for a to-many relationship, and
``<filter_object>`` is another filter object. For example, to filter person
resources by only those people that have authored an article dated before
January 1, 2010,

.. sourcecode:: json

   {
     "name": "articles",
     "op": "any",
     "val": {
       "name": "date",
       "op": "lt",
       "val": "2010-01-01"
     }
   }

For another example, to filter article resources by only those articles that
have an author of age at most fifty,

.. sourcecode:: json

   {
     "name": "author",
     "op": "has",
     "val": {
       "name": "age",
       "op": "lte",
       "val": 50
     }
   }

A filter object may be a conjunction ("and"), disjunction ("or"), or negation
("not") of other filter objects::

   {"or": [<filter_object>, <filter_object>, ...]}

or ::

   {"and": [<filter_object>, <filter_object>, ...]}

or ::

   {"not": <filter_object>}

For example, to filter by resources that have width greater than height, and
length of at least ten,

.. sourcecode:: json

   {
     "and": [
       {"name": "width", "op": "gt", "field": "height"},
       {"name": "length", "op": "lte", "val": 10}
     ]
   }

How are filter objects used in practice? To get a response in which only those
resources that meet the requirements of the filter objects are
returned, clients can make requests like this:

.. sourcecode:: http

   GET /api/person?filter[objects]=[{"name":"age","op":"<","val":18}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

.. _operators:

Operators
---------

Flask-Restless understands the following operators, which correspond to the
appropriate `SQLAlchemy column operators`_.

* ``==``, ``eq``, ``equals``, ``equals_to``
* ``!=``, ``neq``, ``does_not_equal``, ``not_equal_to``
* ``>``, ``gt``, ``<``, ``lt``
* ``>=``, ``ge``, ``gte``, ``geq``, ``<=``, ``le``, ``lte``, ``leq``
* ``in``, ``not_in``
* ``is_null``, ``is_not_null``
* ``like``, ``ilike``, ``not_like``
* ``has``
* ``any``

Flask-Restless also understands the `PostgreSQL network address operators`_
``<<``, ``<<=``, ``>>``, ``>>=``, ``<>``, and ``&&``.

.. warning::

   If you use a percent sign in the argument to the ``like`` operator (for
   example, ``%somestring%``), make sure it is `percent-encoded`_, otherwise
   the server may interpret the first few characters of that argument as a
   percent-encoded character when attempting to decode the URL.

   .. _percent-encoded: https://en.wikipedia.org/wiki/Percent-encoding#Percent-encoding_the_percent_character

.. _SQLAlchemy column operators: https://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.operators.ColumnOperators
.. _PostgreSQL network address operators: https://www.postgresql.org/docs/current/static/functions-net.html


Custom operators
----------------

You can use the :func:`~flask_restless.register_operator` function to extend
the set of known operators::

    from flask_restless import register_operator

    # Create a custom "greater than" implementation.
    register_operator('my_gt', lambda x, y: x - y > 0)

Then the client makes a request with a filter object whose ``op`` element is
the name of this operator:

.. sourcecode:: http

   GET /api/person?filter[objects]=[{"name":"age","op":"my_gt","val":18}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

You can also override existing operators by setting the name of your operator
to be the name of a existing operator; the built-in operators are listed in
the :ref:`previous section <operators>`::

    register_operator('gt', lambda x, y: x - y > 0)


Simpler filtering
-----------------

Flask-Restless also supports a simpler form of filtering as described in the
`JSON API filtering recommendation`_. For filtering by the foreign key of a
to-one relationship, use a request of the form

.. sourcecode:: http

   GET /api/comments?filter[post]=1,2&filter[author]=12 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

Flask-Restless will automatically determine the correct query corresponding to
the given to-one relationships.

You can also filter by attribute:

.. sourcecode:: http

   GET /api/person?filter[age]=21 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

.. admonition:: Implementation note

   Each of these simple filters is converted to the more complex filter object
   representation as described in the preceding sections and appended to the
   list of filter objects computed from the request query parameters.

.. _JSON API filtering recommendation: http://jsonapi.org/recommendations/#filtering

.. _single:

Requiring singleton collections
-------------------------------

If a client wishes a request for a collection to yield a response with a
singleton collection, the client can use the ``filter[single]`` query
parameter. The value of this parameter must be either ``1`` or ``0``. If the
value of this parameter is ``1`` and the response would yield a collection of
either zero or more than two resources, the server instead responds with
:http:statuscode:`404`.

For example, a request like

.. sourcecode:: http

   GET /api/person?filter[single]=1&filter[objects]=[{"name":"id","op":"eq","val":1}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "type": "person",
       "links": {
         "self": "http://example.com/api/person/1"
       }
     },
     "links": {
       "self": "http://example.com/api/person?filter[single]=1&filter[objects]=[{\"name\":\"id\",\"op\":\"eq\",\"val\":1}]"
     },
   }

But a request like

.. sourcecode:: http

   GET /api/person?filter[single]=1 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

would yield an error response if there were more than one ``Person`` instance
in the database.

Filter object examples
----------------------

Attribute greater than a value
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request

.. sourcecode:: http

   GET /api/person?filter[objects]=[{"name":"age","op":"gt","val":18}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

the response will include only those ``Person`` instances that have ``age``
attribute greater than or equal to 18:

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "age": 19
         },
         "id": "2",
         "links": {
           "self": "http://example.com/api/person/2"
         },
         "type": "person"
       },
       {
         "attributes": {
           "age": 29
         },
         "id": "5",
         "links": {
           "self": "http://example.com/api/person/5"
         },
         "type": "person"
       },
     ],
     "links": {
       "self": "/api/person?filter[objects]=[{\"name\":\"age\",\"op\":\"gt\",\"val\":18}]"
     },
     "meta": {
       "total": 2
     }
   }

Arbitrary Boolean expression of filters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On request

.. sourcecode:: http

   GET /api/person?filter[objects]=[{"or":[{"name":"age","op":"lt","val":10},{"name":"age","op":"gt","val":20}]}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

the response will include only those ``Person`` instances that have ``age``
attribute either less than 10 or greater than 20:

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "age": 9
         },
         "id": "1",
         "links": {
           "self": "http://example.com/api/person/1"
         },
         "type": "person"
       },
       {
         "attributes": {
           "age": 25
         },
         "id": "3",
         "links": {
           "self": "http://example.com/api/person/3"
         },
         "type": "person"
       }
     ],
     "links": {
       "self": "/api/person?filter[objects]=[{\"or\":[{\"name\":\"age\",\"op\":\"lt\",\"val\":10},{\"name\":\"age\",\"op\":\"gt\",\"val\":20}]}]"
     },
     "meta": {
       "total": 2
     }
   }

Comparing two attributes
~~~~~~~~~~~~~~~~~~~~~~~~

On request

.. sourcecode:: http

   GET /api/box?filter[objects]=[{"name":"width","op":"ge","field":"height"}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

the response will include only those ``Box`` instances that have ``width``
attribute greater than or equal to the value of the ``height`` attribute:

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "height": 10,
           "width": 20
         }
         "id": "1",
         "links": {
           "self": "http://example.com/api/box/1"
         },
         "type": "box"
       },
       {
         "attributes": {
           "height": 15,
           "width": 20
         }
         "id": "2",
         "links": {
           "self": "http://example.com/api/box/2"
         },
         "type": "box"
       }
     ],
     "links": {
       "self": "/api/box?filter[objects]=[{\"name\":\"width\",\"op\":\"ge\",\"field\":\"height\"}]"
     },
     "meta": {
       "total": 100
     }
   }

Using ``has`` and ``any``
~~~~~~~~~~~~~~~~~~~~~~~~~

On request

.. sourcecode:: http

   GET /api/person?filter[objects]=[{"name":"articles","op":"any","val":{"name":"date","op":"lt","val":"2010-01-01"}}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

the response will include only those people that have authored an article dated
before January 1, 2010 (assume in the example below that at least one of the
article linkage objects refers to an article that has such a date):

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "1",
         "links": {
           "self": "http://example.com/api/person/1"
         },
         "relationships": {
           "articles": {
             "data": [
               {
                 "id": "1",
                 "type": "article"
               },
               {
                 "id": "2",
                 "type": "article"
               }
             ],
             "links": {
               "related": "http://example.com/api/person/1/articles",
               "self": "http://example.com/api/person/1/relationships/articles"
             }
           }
         },
         "type": "person"
       }
     ],
     "links": {
       "self": "/api/person?filter[objects]=[{\"name\":\"articles\",\"op\":\"any\",\"val\":{\"name\":\"date\",\"op\":\"lt\",\"val\":\"2010-01-01\"}}]"
     },
     "meta": {
       "total": 1
     }
   }

On request

.. sourcecode:: http

   GET /api/article?filter[objects]=[{"name":"author","op":"has","val":{"name":"age","op":"lte","val":50}}] HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

the response will include only those articles that have an author of age at
most fifty (assume in the example below that the author linkage objects refers
to a person that has such an age):

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "1",
         "links": {
           "self": "http://example.com/api/article/1"
         },
         "relationships": {
           "author": {
             "data": {
               "id": "7",
               "type": "person"
             },
             "links": {
               "related": "http://example.com/api/article/1/author",
               "self": "http://example.com/api/article/1/relationships/author"
             }
           }
         },
         "type": "article"
       }
     ],
     "links": {
       "self": "/api/article?filter[objects]=[{\"name\":\"author\",\"op\":\"has\",\"val\":{\"name\":\"age\",\"op\":\"lte\",\"val\":50}}]"
     },
     "meta": {
       "total": 1
     }
   }
