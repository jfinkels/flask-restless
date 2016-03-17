.. currentmodule:: flask.ext.restless

.. _fetching:

Fetching resources and relationships
====================================

For the purposes of concreteness in this section, suppose we have executed the
following code on the server::

    from flask import Flask
    from flask.ext.sqlalchemy import SQLAlchemy
    from flask.ext.restless import APIManager

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)

    class Article(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
        author = db.relationship(Person, backref=db.backref('articles'))

    db.create_all()
    manager = APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person)
    manager.create_api(Article)

By default, all columns and relationships will appear in the resource object
representation of an instance of your model. See :ref:`sparse` for more
information on specifying which values appear in responses.

To fetch a collection of resources, the request

.. sourcecode:: http

   GET /api/person HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

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
             "data": [],
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
       "first": "http://example.com/api/person?page[number]=1&page[size]=10",
       "last": "http://example.com/api/person?page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person"
     },
     "meta": {
       "total": 1
     }
   }

To fetch a single resource, the request

.. sourcecode:: http

   GET /api/person/1 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/relationships/articles"
           }
         }
       },
       "type": "person"
     }
   }

To fetch a resource from a to-one relationship, the request

.. sourcecode:: http

   GET /api/article/1/author HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
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
   }

To fetch a resource from a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "2",
         "links": {
           "self": "http://example.com/api/articles/2"
         },
         "relationships": {
           "author": {
             "data": {
               "id": "1",
               "type": "person",
             },
             "links": {
               "related": "http://example.com/api/articles/2/author",
               "self": "http://example.com/api/articles/2/relationships/author"
             }
           }
         },
         "type": "article"
       }
     ],
     "links": {
       "first": "http://example.com/api/person/1/articles?page[number]=1&page[size]=10",
       "last": "http://example.com/api/person/1/articles?page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person/1/articles"
     },
     "meta": {
       "total": 1
     }
   }

To fetch a single resource from a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/articles/2 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "2",
       "links": {
         "self": "http://example.com/api/articles/2"
       },
       "relationships": {
         "author": {
           "data": {
             "id": "1",
             "type": "person"
           },
           "links": {
             "related": "http://example.com/api/articles/2/author",
             "self": "http://example.com/api/articles/2/relationships/author"
           }
         }
       },
       "type": "article"
     }
   }

To fetch the link object for a to-one relationship, the request

.. sourcecode:: http

   GET /api/article/1/relationships/author HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "type": "person"
     }
   }

To fetch the link objects for a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/relationships/articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "1",
         "type": "article"
       },
       {
         "id": "2",
         "type": "article"
       }
     ]
   }

.. _functionevaluation:

Function evaluation
-------------------

*This section describes behavior that is not part of the JSON API specification.*

If the ``allow_functions`` keyword argument to :meth:`APIManager.create_api` is
set to ``True`` when creating an API for a model, then the endpoint
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

.. |func| replace:: ``func``
.. _func: https://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.expression.func

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

.. _includes:

Inclusion of related resources
------------------------------

*For more information on client-side included resources, see* `Inclusion of
Related Resources`_ *in the JSON API specification.*

By default, no related resources will be included in a compound document on
requests that would return data. For the client to request that the response
includes related resources in a compound document, use the ``include`` query
parameter. For example, to fetch a single resource and include all resources
related to it, the request

.. sourcecode:: http

   GET /api/person/1?include=articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
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
     "included": [
       {
         "id": "1",
         "links": {
           "self": "http://example.com/api/article/1"
         },
         "relationships": {
           "author": {
             "data": {
               "id": "1",
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
     ]
   }

To specify a default set of related resources to include when the client does
not specify any `include` query parameter, use the ``includes`` keyword
argument to the :meth:`APIManager.create_api` method.

.. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

.. _sparse:

Specifying which fields appear in responses
-------------------------------------------

*For more information on client-side sparse fieldsets, see* `Sparse Fieldsets`_
*in the JSON API specification.*

.. warning::

   The server-side configuration for specifying which fields appear in resource
   objects as described in this section is simplistic; a better way to specify
   which fields are included in your responses is to use a Python object
   serialization library and specify custom serialization and deserialization
   functions as described in :ref:`serialization`.

By default, all fields of your model will be exposed by the API. A client can
request that only certain fields appear in the resource object in a response to
a :http:method:`get` request by using the ``only`` query parameter. On the
server side, you can specify which fields appear in the resource object
representation of an instance of the model by setting the ``only``, ``exclude``
and ``additional_attributes`` keyword arguments to the
:meth:`APIManager.create_api` method.

If ``only`` is an iterable of column names or actual column attributes, only
those fields will appear in the resource object that appears in responses to
fetch instances of this model. If instead ``exclude`` is specified, all fields
except those specified in that iterable will appear in responses. If
``additional_attributes`` is an iterable of column names, the values of these
attributes will also appear in the response; this is useful if you wish to see
the value of some attribute that is not a column or relationship.

.. attention::

   The ``type`` and ``id`` elements will always appear in the resource object,
   regardless of whether the server or the client tries to exclude them.

For example, if your models are defined like this (using Flask-SQLAlchemy)::

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode)
        birthday = db.Column(db.Date)
        articles = db.relationship('Article')

        # This class attribute is not a column.
        foo = 'bar'

    class Article(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey('person.id'))

and you want your resource objects to include only the values of the ``name``
and ``birthday`` columns, create your API with the following arguments::

    apimanager.create_api(Person, only=['name', 'birthday'])

Now a request like

.. sourcecode:: http

   GET /api/person/1 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "attributes": {
         "birthday": "1969-07-20",
         "name": "foo"
       },
       "type": "person"
     }
   }

If you want your resource objects to *exclude* the ``birthday`` and ``name``
columns::

    apimanager.create_api(Person, exclude=['name', 'birthday'])

Now the same request yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       }
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/links/articles"
           }
         },
       },
       "type": "person"
     }
   }

If you want your resource objects to include the value for the class attribute
``foo``::

    apimanager.create_api(Person, additional_attributes=['foo'])

Now the same request yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "birthday": "1969-07-20",
         "foo": "bar",
         "name": "foo"
       },
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       }
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/links/articles"
           }
         }
       },
       "type": "person"
     }
   }

.. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

.. _sorting:

Sorting
-------

Clients can sort according to the sorting protocol described in the `Sorting
<http://jsonapi.org/format/#fetching-sorting>`__ section of the JSON API
specification. Sorting by a nullable attribute will cause resources with null
attributes to appear first.

Clients can also request grouping by using the ``group`` query parameter. For
example, if your database has two people with name ``'foo'`` and two people
with name ``'bar'``, a request like

.. sourcecode:: http

   GET /api/person?group=name HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "name": "foo",
         },
         "id": "1",
         "links": {
           "self": "http://example.com/api/person/1"
         },
         "relationships": {
           "articles": {
             "data": [],
             "links": {
               "related": "http://example.com/api/person/1/articles",
               "self": "http://example.com/api/person/1/relationships/articles"
             }
           }
         },
         "type": "person"
       },
       {
         "attributes": {
           "name": "bar",
         },
         "id": "3",
         "links": {
           "self": "http://example.com/api/person/3"
         },
         "relationships": {
           "articles": {
             "data": [],
             "links": {
               "related": "http://example.com/api/person/3/articles",
               "self": "http://example.com/api/person/3/relationships/articles"
             }
           }
         },
         "type": "person"
       },
     ],
     "links": {
       "first": "http://example.com/api/person?group=name&page[number]=1&page[size]=10",
       "last": "http://example.com/api/person?group=name&page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person?group=name"
     },
     "meta": {
       "total": 2
     }
   }

.. _pagination:

Pagination
----------

Pagination works as described in the JSON API specification, via the
``page[number]`` and ``page[size]`` query parameters. Pagination respects
sorting, grouping, and filtering. The first page is page one. If no page number
is specified by the client, the first page will be returned. By default,
pagination is enabled and the page size is ten. If the page size specified by
the client is greater than the maximum page size as configured on the server,
then the query parameter will be ignored.

To set the default page size for collections of resources, use the
``page_size`` keyword argument to the :meth:`APIManager.create_api` method.  To
set the maximum page size that the client can request, use the
``max_page_size`` argument. Even if ``page_size`` is greater than
``max_page_size``, at most ``max_page_size`` resources will be returned in a
page. If ``max_page_size`` is set to anything but a positive integer, the
client will be able to specify arbitrarily large page sizes. If, further,
``page_size`` is set to anything but a positive integer, pagination will be
disabled by default, and any :http:method:`get` request that does not specify a
page size in its query parameters will get a response with all matching
results.

.. attention::

   Disabling pagination can result in arbitrarily large responses!

For example, to set each page to include only two results::

    apimanager.create_api(Person, page_size=2)

Then a :http:method:`get` request to ``/api/person?page[number]=2`` would yield
the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "3",
         "type": "person",
         "attributes": {
           "name": "John"
         }
       }
       {
         "id": "4",
         "type": "person",
         "attributes": {
           "name": "Paul"
         }
       }
     ],
     "links": {
       "first": "http://example.com/api/person?page[number]=1&page[size]=2",
       "last": "http://example.com/api/person?page[number]=3&page[size]=2",
       "next": "http://example.com/api/person?page[number]=3&page[size]=2",
       "prev": "http://example.com/api/person?page[number]=1&page[size]=2",
       "self": "http://example.com/api/person"
     },
     "meta": {
       "total": 6
     }
   }

.. _filtering:

Filtering
---------

Requests that would normally return a collection of resources can be filtered
so that only a subset of the resources are returned in a response. If the
client specifies the ``filter[objects]`` query parameter, it must be a
`URL encoded`_ JSON list of :dfn:`filter objects`, as described below.

.. _URL encoded: https://en.wikipedia.org/wiki/Percent-encoding

Quick client examples for filtering
...................................

*TODO: need to test these clients.*

The following are some quick examples of making filtered :http:method:`get`
requests from different types of clients. More complete documentation is in
subsequent sections. In these examples, each client will filter by instances of
the model ``Person`` whose names contain the letter "y".

Using the Python `requests`_ library::

    import requests
    import json

    url = 'http://127.0.0.1:5000/api/person'
    headers = {'Content-Type': 'application/vnd.api+json',
               'Accept': 'application/vnd.api+json'}

    filters = [dict(name='name', op='like', val='%y%')]
    params = {'filter[objects]': filters}

    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    print(response.json())

Using `jQuery`_:

.. sourcecode:: javascript

   var filters = [{"name": "id", "op": "like", "val": "%y%"}];
   $.ajax({
     accepts: 'application/vnd.api+json',
     contentType: "application/vnd.api+json",
     data: {"filter[objects]": JSON.stringify(filters)},
     dataType: "json",
     success: function(data) { console.log(data.objects); }
     url: 'http://127.0.0.1:5000/api/person',
   });

Using `curl`_:

.. sourcecode:: bash

   curl \
     -G \
     -H "Content-Type: application/vnd.api+json" \
     -H "Accept: application/vnd.api+json" \
     -d "filter[objects]=[{\"name\":\"name\",\"op\":\"like\",\"val\":\"%y%\"}]" \
     http://127.0.0.1:5000/api/person

The :file:`examples/` directory has more complete versions of these examples.

.. _requests: http://docs.python-requests.org/en/latest/
.. _jQuery: http://jquery.com/
.. _curl: http://curl.haxx.se/

Filter objects
..............

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

A filter object may be a conjunction ("and") or disjunction ("or") of other
filter objects::

   {"or": [<filter_object>, <filter_object>, ...]}

or ::

   {"and": [<filter_object>, <filter_object>, ...]}

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
.........

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

.. _single:

Requiring singleton collections
...............................

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
......................

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
