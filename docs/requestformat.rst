.. _requestformat:

.. currentmodule:: flask.ext.restless

Format of requests and responses
================================

Requests and responses are all in JSON format, so the mimetype is
:mimetype:`application/json`. Ensure that requests you make that require a body
(:http:method:`patch` and :http:method:`post` requests) have the header
``Content-Type: application/json``; if they do not, the server will respond
with a :http:statuscode:`415`.

Suppose we have the following Flask-SQLAlchemy models (the example works with
pure SQLALchemy just the same)::

    from flask import Flask
    from flask.ext.sqlalchemy import SQLAlchemy

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        birth_date = db.Column(db.Date)
        computers = db.relationship('Computer',
                                    backref=db.backref('owner',
                                                       lazy='dynamic'))

    class Computer(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        vendor = db.Column(db.Unicode)
        owner_id = db.Column(db.Integer, db.ForeignKey('person.id'))
        purchase_time = db.Column(db.DateTime)


Also suppose we have registered an API for these models at ``/api/person`` and
``/api/computer``, respectively.

.. note::

   For all requests that would return a list of results, the top-level JSON
   object is a mapping from ``"objects"`` to the list. JSON lists are not sent
   as top-level objects for security reasons. For more information, see `this
   <http://flask.pocoo.org/docs/security/#json-security>`_.

.. http:get:: /api/person

   Gets a list of all ``Person`` objects.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "num_results": 8,
        "total_pages": 3,
        "page": 2,
        "objects": [{"id": 1, "name": "Jeffrey", "age": 24}, ...]
      }

.. http:get:: /api/person?q=<searchjson>

   Gets a list of all ``Person`` objects which meet the criteria of the
   specified search. For more information on the format of the value of the
   ``q`` parameter, see :ref:`searchformat`.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
         "num_results": 8,
         "total_pages": 3,
         "page": 2,
         "objects": [{"id": 1, "name": "Jeffrey", "age": 24}, ...]
       }

.. http:get:: /api/person/(int:id)

   Gets a single instance of ``Person`` with the specified ID.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {"id": 1, "name": "Jeffrey", "age": 24}

.. http:get:: /api/person/(int:id)/computers

   Gets a list of all ``Computer`` objects which are owned by the ``Person``
   object with the specified ID.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "num_results": 2,
        "total_pages": 1,
        "page": 1,
        "objects": [{"id": 1, "vendor": "Apple", "name": "MacBook", ...}, ...]
      }

.. http:delete:: /api/person/(int:id)

   Deletes the instance of ``Person`` with the specified ID.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content

.. http:post:: /api/person

   Creates a new person with initial attributes specified as a JSON string in
   the body of the request.

   **Sample request**:

   .. sourcecode:: http

      POST /api/person HTTP/1.1
      Host: example.com

      {"name": "Jeffrey", "age": 24}

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {
        "id": 1,
        "name": "Jeffrey",
        "age" 24,
        "computers": []
      }

   The server will respond with :http:statuscode:`400` if the request specifies
   a field which does not exist on the model.

   To create a new person which includes a related list of **new** computer
   instances via a one-to-many relationship, a request must take the following
   form.

   **Sample request**:

   .. sourcecode:: http

      POST /api/person HTTP/1.1
      Host: example.com

      {
        "name": "Jeffrey",
        "age": 24,
        "computers":
          [
            {"manufacturer": "Dell", "model": "Inspiron"},
            {"manufacturer": "Apple", "model": "MacBook"}
          ]
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers":
          [
            {"id": 1, "manufacturer": "Dell", "model": "Inspiron"},
            {"id": 2, "manufacturer": "Apple", "model": "MacBook"}
          ]
      }

   .. warning::

      The response does not denote that new instances have been created for the
      ``Computer`` models.

   To create a new person which includes a single related **new** computer
   instance (via a one-to-one relationship), a request must take the following
   form.

   **Sample request**:

   .. sourcecode:: http

      POST /api/person HTTP/1.1
      Host: example.com

      {
        "name": "Jeffrey",
        "age": 24,
        "computer": {"manufacturer": "Dell", "model": "Inspiron"}
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {
        "name": "Jeffrey",
        "age": 24,
        "id": 1,
        "computer": {"id": 1, "manufacturer": "Dell", "model": "Inspiron"}
      }

   .. warning::

      The response does not denote that a new ``Computer`` instance has been
      created.

   To create a new person which includes a related list of **existing**
   computer instances via a one-to-many relationship, a request must take the
   following form.

   **Sample request**:

   .. sourcecode:: http

      POST /api/person HTTP/1.1
      Host: example.com

      {
        "name": "Jeffrey",
        "age": 24,
        "computers": [ {"id": 1}, {"id": 2} ]
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers":
          [
            {"id": 1, "manufacturer": "Dell", "model": "Inspiron"},
            {"id": 2, "manufacturer": "Apple", "model": "MacBook"}
          ]
      }

   To create a new person which includes a single related **existing** computer
   instance (via a one-to-one relationship), a request must take the following
   form.

   **Sample request**:

   .. sourcecode:: http

      POST /api/person HTTP/1.1
      Host: example.com

      {
        "name": "Jeffrey",
        "age": 24,
        "computer": {"id": 1}
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {
        "name": "Jeffrey",
        "age": 24,
        "id": 1,
        "computer": {"id": 1, "manufacturer": "Dell", "model": "Inspiron"}
      }

.. http:patch:: /api/person
.. http:put:: /api/person

   Sets specified attributes on every instance of ``Person`` which meets the
   search criteria described in the ``q`` parameter.

   The JSON object specified in the body of a :http:method:`patch` request to
   this endpoint may include a mapping from `q` to the parameters for a search,
   as described in :ref:`searchformat`. If no `q` key exists, then all
   instances of the model will be patched.

   :http:put:`/api/person` is an alias for :http:patch:`/api/person`, because
   the latter is more semantically correct but the former is part of the core
   HTTP standard.

   The response will return a JSON object which specifies the number of
   instances in the ``Person`` database which were modified.

   **Sample request**:

   Suppose the database contains exactly three people with the letter "y" in
   his or her name.

   .. sourcecode:: http

      PATCH /api/person HTTP/1.1
      Host: example.com

      {
        "age": 1,
        "q": {"filters": [{"name": "name", "op": "like", "val": "%y%"}]}
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created

      {"num_modified": 3}

.. http:patch:: /api/person/(int:id)
.. http:put:: /api/person/(int:id)

   Sets specified attributes on the instance of ``Person`` with the specified
   ID number. :http:put:`/api/person/1` is an alias for
   :http:patch:`/api/person/1`, because the latter is more semantically correct
   but the former is part of the core HTTP standard.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      {"name": "Foobar"}

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {"id": 1, "name": "Foobar", "age": 24}

   The server will respond with :http:statuscode:`400` if the request specifies
   a field which does not exist on the model.

   To add a list of existing objects to a one-to-many relationship, a request
   must take the following form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
        {
          "add": [ {"id": 1} ]
        }
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [ {"id": 1, "manufacturer": "Dell", "model": "Inspiron"} ]
      }

   To add a list of new objects to a one-to-many relationship, a request must
   take the following form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
        {
          "add": [ {"manufacturer": "Dell", "model": "Inspiron"} ]
        }
      }

   .. warning::

      The response does not denote that a new instance has been created for the
      ``Computer`` model.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [ {"id": 1, "manufacturer": "Dell", "model": "Inspiron"} ]
      }

   Similarly, to add a new or existing instance of a related model to a
   one-to-one relationship, a request must take the following form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
        {
          "add": {"id": 1}
        }
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [ {"id": 1, "manufacturer": "Dell", "model": "Inspiron"} ]
      }

   To remove an existing object (without deleting that object from its own
   database) from a one-to-many relationship, a request must take the following
   form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
        {
          "remove": [ {"id": 2} ]
        }
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [
          {"id": 1, "manufacturer": "Dell", "model": "Inspiron 9300"},
          {"id": 3, "manufacturer": "Apple", "model": "MacBook"}
        ]
      }

   To remove an existing object from a one-to-many relationship and
   additionally delete it from its own database, a request must take the
   following form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
        {
          "remove": [ {"id": 2, "__delete__": true} ]
        }
      }

   .. warning::

      The response does not denote that the instance was deleted from its own
      database.

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [
          {"id": 1, "manufacturer": "Dell", "model": "Inspiron 9300"},
          {"id": 3, "manufacturer": "Apple", "model": "MacBook"}
        ]
      }

   To set the value of a one-to-many relationship to contain either existing or
   new instances of the related model, a request must take the following form.

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
          [
            {"id": 1},
            {"id": 3},
            {"manufacturer": "Lenovo", "model": "ThinkPad"}
          ]
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [
          {"id": 1, "manufacturer": "Dell", "model": "Inspiron 9300"},
          {"id": 3, "manufacturer": "Apple", "model": "MacBook"}
          {"id": 4, "manufacturer": "Lenovo", "model": "ThinkPad"}
        ]
      }

   To set the value of a one-to-many relationship *and* update fields on
   existing instances of the related model, a request must take the following
   form.

   Suppose the ``Person`` instance looked like this before the sample
   :http:method:`patch` request below:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [
          {"id": 1, "manufacturer": "Apple", "model": "MacBook"}
        ]
      }

   **Sample request**:

   .. sourcecode:: http

      PATCH /api/person/1 HTTP/1.1
      Host: example.com

      { "computers":
          [
            {"id": 1, "manufacturer": "Lenovo", "model": "ThinkPad"}
          ]
      }

   **Sample response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {
        "id": 1,
        "name": "Jeffrey",
        "age": 24,
        "computers": [
          {"id": 1, "manufacturer": "Lenovo", "model": "ThinkPad"}
        ]
      }

   The changes reflected in this response have been made to the ``Computer``
   instance with ID 1.

Error messages
--------------

Most errors return :http:statuscode:`400`. A bad request, for example, will
receive a response like this:

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   {"message": "Unable to decode data"}

.. _functionevaluation:

Function evaluation
-------------------

If the ``allow_functions`` keyword argument is set to ``True`` when creating an
API for a model using :meth:`APIManager.create_api`, then an endpoint will be
made available for :http:get:`/api/eval/person` which responds to requests for
evaluation of functions on *all* instances the model.

**Sample request**:

.. sourcecode:: http

   GET /api/eval/person?q={"functions": [{"name": "sum", "field": "age"}, {"name": "avg", "field": "height"}]} HTTP/1.1

The format of the response is

.. sourcecode:: http

   HTTP/1.1 200 OK

   {"sum__age": 100, "avg_height": 68}

If no functions are specified in the request, the response will contain
the empty JSON object, ``{}``.

.. note::

   The functions whose names are given in the request will be evaluated using
   SQLAlchemy's `func
   <http://docs.sqlalchemy.org/en/latest/core/expression_api.html#sqlalchemy.sql.expression.func>`_
   object.

.. admonition:: Example

   To get the total number of rows in the query (that is, the number of
   instances of the requested model), use ``count`` as the name of the function
   to evaluate, and ``id`` for the field on which to evaluate it:

   **Request**:

   .. sourcecode:: http

      GET /api/eval/person?q={"functions": [{"name": "count", "field": "id"}]} HTTP/1.1

   **Response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK

      {"count__id": 5}

JSON-P callbacks
----------------

Add a ``callback=myfunc`` query parameter to the request URL on any
:http:method:`get` requests (including endpoints for function evaluation) to
have the JSON data of the response wrapped in the Javascript function
``myfunc``. This can be used to circumvent some cross domain scripting security
issues. For example, a request like this:

.. sourcecode:: http

   GET /api/person/1?callback=foo HTTP/1.1

will produce a response like this:

.. sourcecode:: http

   HTTP/1.1 200 OK

   foo({"id": 1, "name": "Henry", "age": 10})

Then in your Javascript code, write the function ``foo`` like this:

.. sourcecode:: javascript

   function foo(response) {
     var name = response.name;
     console.log(name);
   }

.. _clientpagination:

Pagination
----------

Responses to :http:method:`get` requests are paginated by default, with at most
ten objects per page. To request a specific page, add a ``page=N`` query
parameter to the request URL, where ``N`` is a positive integer (the first page
is page one). If no ``page`` query parameter is specified, the first page will
be returned.

In order to specify the number of results per page, add the query parameter
``results_per_page=N`` where ``N`` is a positive integer. If
``results_per_page`` is greater than the maximum number of results per page as
configured by the server (see :ref:`serverpagination`), then the query
parameter will be ignored.

In addition to the ``"objects"`` list, the response JSON object will have a
``"page"`` key whose value is the current page, a ``"num_pages"`` key whose
value is the total number of pages into which the set of matching instances is
divided, and a ``"num_results"`` key whose value is the total number of
instances which match the requested search. For example, a request to
:http:get:`/api/person?page=2` will result in the following response:

.. sourcecode:: http

   HTTP/1.1 200 OK

   {
     "num_results": 8,
     "page": 2,
     "num_pages": 3,
     "objects": [{"id": 1, "name": "Jeffrey", "age": 24}, ...]
   }

If pagination is disabled (by setting ``results_per_page=None`` in
:meth:`APIManager.create_api`, for example), any ``page`` key in the query
parameters will be ignored, and the response JSON will include a ``"page"`` key
which always has the value ``1``.

.. note::

   As specified in in :ref:`queryformat`, clients can receive responses with
   ``limit`` (a maximum number of objects in the response) and ``offset`` (the
   number of initial objects to skip in the response) applied. It is possible,
   though not recommended, to use pagination in addition to ``limit`` and
   ``offset``. For simple clients, pagination should be fine.
