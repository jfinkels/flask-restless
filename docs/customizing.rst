.. _customizing:

.. currentmodule:: flask.ext.restless

Customizing the ReSTful interface
=================================

HTTP methods
~~~~~~~~~~~~

By default, the :meth:`APIManager.create_api` method creates a read-only
interface; requests with HTTP methods other than :http:method:`GET` will cause
a response with :http:statuscode:`405`. To explicitly specify which methods
should be allowed for the endpoint, pass a list as the value of keyword
argument ``methods``::

    apimanager.create_api(Person, methods=['GET', 'POST', 'DELETE'])

This creates an endpoint at ``/api/person`` which responds to
:http:method:`get`, :http:method:`post`, and :http:method:`delete` methods, but
not to other ones like :http:method:`put` or :http:method:`patch`.

The recognized HTTP methods and their semantics are described below (assuming
you have created an API for an entity ``Person``). All endpoints which respond
with data respond with serialized JSON strings.

.. http:get:: /api/person

   Returns a list of all ``Person`` instances.

.. http:get:: /api/person/(int:id)

   Returns a single ``Person`` instance with the given ``id``.

.. http:get:: /api/person?q=<searchjson>

   Returns a list of all ``Person`` instances which match the search query
   specified in the query parameter ``q``. For more information on searching,
   see :ref:`searchformat`.

.. http:delete:: /api/person/(int:id)

   Deletes the person with the given ``id`` and returns :http:statuscode:`204`.

.. http:post:: /api/person

   Creates a new person in the database and returns its ``id``. The initial
   attributes of the ``Person`` are read as JSON from the body of the
   request. For information about the format of this request, see
   :ref:`requestformat`.

.. http:patch:: /api/person/(int:id)

   Updates the attributes of the ``Person`` with the given ``id``. The
   attributes are read as JSON from the body of the request. For information
   about the format of this request, see :ref:`requestformat`.

.. http:patch:: /api/person

   This is only available if the ``allow_patch_many`` keyword argument is set
   to ``True`` when calling the :meth:`~APIManager.create_api` method. For more
   information, see :ref:`allowpatchmany`.

   Updates the attributes of all ``Person`` instances. The attributes are read
   as JSON from the body of the request. For information about the format of
   this request, see :ref:`requestformat`.
  
.. http:put:: /api/person
.. http:put:: /api/person/(int:id)

   Aliases for :http:patch:`/api/person` and
   :http:patch:`/api/person/(int:id)`.

API prefix
~~~~~~~~~~

To create an API at a different prefix, use the ``url_prefix`` keyword
argument::

    apimanager.create_api(Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/person``.

Collection name
~~~~~~~~~~~~~~~

By default, the name of the collection which appears in the URLs of the API
will be the name of the table which backs your model. If your model is a
SQLAlchemy model, this will be the value of ``__tablename__``. If your model is
a Flask-SQLAlchemy model, this will be the lowercase name of the model with
``CamelCase`` changed to ``camel_case``.

To provide a different name for the model, provide a string to the
`collection_name` keyword argument of the :meth:`APIManager.create_api`
method::

    apimanager.create_api(Person, collection_name='people')

Then the API will be exposed at ``/api/people`` instead of ``/api/person``.

.. _allowpatchmany:

Enable patching all instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, a :http:patch:`/api/person` request (note the missing ID) will
cause a :http:statuscode:`405` response. By setting the ``allow_patch_many``
keyword argument of the :meth:`APIManager.create_api` method to be ``True``,
:http:patch:`/api/person` requests will patch the provided attributes on all
instances of ``Person``::

    apimanager.create_api(Person, methods=['PATCH'], allow_patch_many=True)

.. _validation:

Capturing validation errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, no validation is performed by Flask-Restless; if you want
validation, implement it yourself in your database models. However, by
specifying a list of exceptions raised by your backend on validation errors,
Flask-Restless will forward messages from raised exceptions to the client in an
error response.

A reasonable validation framework you might use for this purpose is `SQLAlchemy
Validation <https://bitbucket.org/blazelibs/sqlalchemy-validation>`_. You can
also use the :func:`~sqlalchemy.orm.validates` decorator that comes with
SQLAlchemy.

For example, if your validation framework includes an exception called
``ValidationError``, then call the :meth:`APIManager.create_api` method with
the ``validation_exceptions`` keyword argument::

    from cool_validation_framework import ValidationError
    apimanager.create_api(Person, validation_exceptions=[ValidationError])

.. note::

   Currently, Flask-Restless expects that an instance of a specified validation
   error will have a ``errors`` attribute, which is a dictionary mapping field
   name to error description (note: one error per field). If you have a better,
   more general solution to this problem, please visit `our issue tracker
   <https://github.com/jfinkels/flask-restless/issues>`_.

Now when you make :http:method:`post` and :http:method:`patch` requests with
invalid fields, the JSON response will look like this:

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   { "validation_errors":
       {
         "age": "Must be an integer",
       }
   }

Currently, Flask-Restless can only forward one exception at a time to the
client.

Exposing evaluation of SQL functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the ``allow_functions`` keyword argument is set to ``True`` when creating an
API for a model using :meth:`APIManager.create_api`, then an endpoint will be
made available for :http:get:`/api/eval/person` which responds to requests for
evaluation of functions on all instances the model.

For information about the request and response formats for this endpoint, see
:ref:`functionevaluation`.

.. _includes:

Specifying which columns are provided in responses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, all columns of your model will be exposed by the API. If the
``include_columns`` keyword argument is an iterable of strings, *only* columns
with those names (that is, the strings represent the names of attributes of the
model which are ``Column`` objects) will be provided in JSON responses for
:http:method:`get` requests.

For example, if your models are defined like this (using Flask-SQLAlchemy)::

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode, unique=True)
        birth_date = db.Column(db.Date)
        computers = db.relationship('Computer')

and you want your JSON responses to include only the values of the ``name`` and
``birth_date`` columns, create your API with the following arguments::

    apimanager.create_api(Person, include_columns=['name', 'birth_date'])

Now requests like :http:get:`/api/person/1` will return JSON objects which look
like this:

.. sourcecode:: javascript

   {"name": "Jeffrey", "birth_date": "1999-12-31"}

The ``exclude_columns`` keyword argument works similarly; it forces your JSON
responses to include only the columns *not* specified in ``exclude_columns``.
For example::

    apimanager.create_api(Person, exclude_columns=['name', 'birth_date'])

will produce responses like:

.. sourcecode:: javascript

   {"id": 1, "computers": [{"id": 1, "vendor": "Apple", "model": "MacBook"}]}

In this example, the ``Person`` model has a one-to-many relationship with the
``Computer`` model. To specify which columns on the related models will be
included or excluded, include a string of the form ``'<relation>.<column>'``,
where ``<relation>`` is the name of the relationship attribute of the model and
``<column>`` is the name of the column on the related model which you want to
be included or excluded. For example::

    includes = ['name', 'birth_date', 'computers', 'computers.vendor']
    apimanager.create_api(Person, include_columns=includes)

will produce responses like:

.. sourcecode:: javascript

   {
     "name": "Jeffrey",
     "birth_date": "1999-12-31",
     "computers": [{"vendor": "Apple"}]
   }

An attempt to include a field on a related model without including the
relationship field has no effect::

    includes = ['name', 'birth_date', 'computers.vendor']
    apimanager.create_api(Person, include_columns=includes)

.. sourcecode:: javascript

   {"name": "Jeffrey", "birth_date": "1999-12-31"}

.. _authentication:

Requiring authentication for some methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   The authentication system in Flask-Restless is relatively simple, but since
   I suspect it is a common requirement for ReSTful APIs, suggestions,
   comments, and pull requests are much appreciated. Please visit `our issue
   tracker <https://github.com/jfinkels/flask-restless/issues>`_.

If you want certain HTTP methods to require authentication, use the
``authentication_required_for`` and ``authentication_function`` keyword
arguments to the :meth:`APIManager.create_api` method. If you specify the
former, you must also specify the latter.

``authentication_required_for`` is the list of HTTP method names which will
require authentication and ``authentication_function`` is a function with zero
arguments which returns ``True`` if and only if the client making the request
has been authenticated. This function can really be anything you like, but
presumably it will have something to do with your authentication framework.

For an example using `Flask-Login <packages.python.org/Flask-Login/>`_, see the
:file:`examples/authentication` directory in the source distribution, or view
it online at `GitHub
<https://github.com/jfinkels/flask-restless/tree/master/examples/authentication>`_.

.. _serverpagination:

Server-side pagination
~~~~~~~~~~~~~~~~~~~~~~

To set the default number of results returned per page, use the
``results_per_page`` keyword argument to the :meth:`APIManager.create_api`
method. The default number of results per page is ten. The client can override
the number of results per page by using a query parameter in its
:http:method:`get` request; see :ref:`clientpagination`.

To set the maximum number of results returned per page, use the
``max_results_per_page`` keyword argument. Even if ``results_per_page >
max_results_per_page``, at most ``max_results_per_page`` will be returned. The
same is true if the client specifies ``results_per_page`` as a query argument;
``max_results_per_page`` provides an upper bound.

If ``max_results_per_page`` is set to anything but a positive integer, the
client will be able to specify arbitrarily large page sizes. If, further,
``results_per_page`` is set to anything but a positive integer, pagination will
be disabled by default, and any :http:method:`get` request which does not
specify a page size in its query parameters will get a response with all
matching results.

.. attention::

   Disabling pagination can result in large responses!

For example, to set each page to include only two results::

    apimanager.create_api(Person, results_per_page=2)

Then a request to :http:get:`/api/person` will return a JSON object which looks
like this:

.. sourcecode:: javascript

   {
     "num_results": 6,
     "total_pages": 3,
     "page": 1,
     "objects": [
       {"name": "Jeffrey", "id": 1},
       {"name": "John", "id": 2}
     ]
   }

For more information on using pagination in the client, see
:ref:`clientpagination`.

.. _processors:

Request preprocessors and postprocessors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To apply a function to the request parameters and/or body before the request is
processed, use the ``preprocessors`` keyword argument. To apply a function to
the response data after the request is processed (immediately before the
response is sent), use the ``postprocessors`` keyword argument. Both
``preprocessors`` and ``postprocessors`` must be a dictionary which maps HTTP
method names as strings (with exceptions as described below) to a list of
functions. The specified functions will be applied in the order given in the
list.

Since :http:method:`get` and :http:method:`patch` (and :http:method:`put`)
requests can be made not only on individual instances of the model but also the
entire collection of instances, you must separately specify which functions to
apply in the individual case and which to apply in the collection case. For
example::

    # Define pre- and postprocessor functions as described below.
    def pre_get_single(instid): ...
    def pre_get_many(params): ...
    def post_patch_many(query, data): ...
    def pre_delete(instid): ...

    # Create an API for the Person model.
    manager.create_api(Person,
                       # Allow GET, PATCH, and POST requests.
                       methods=['GET', 'PATCH', 'DELETE'],
                       # Allow PATCH requests modifying the whole collection.
                       allow_patch_many=True,
                       # A list of preprocessors for each method.
                       preprocessors={
                           'GET_SINGLE': [pre_get_single],
                           'GET_MANY': [pre_get_many],
                           'DELETE': [pre_delete]
                           },
                       # A list of postprocessors for each method.
                       postprocessors={
                           'PATCH_MANY': [post_patch_many]
                           }
                       )

As introduced in the above example, the dictionary keys for the `preprocessors`
and `postprocessors` can be one of the following strings:

* ``'GET_SINGLE'`` for requests to get a single instance of the model.
* ``'GET_MANY'`` for requests to get the entire collection of instances of the
  model.
* ``'PATCH_SINGLE'`` or ``'PUT_SINGLE'`` for requests to patch a single
  instance of the model.
* ``'PATCH_MANY'`` or ``'PATCH_SINGLE'`` for requests to patch the entire
  collection of instances of the model.
* ``'POST'`` for requests to post a new instance of the model.
* ``'DELETE'`` for requests to delete an instance of the model.

.. note::

   Since :http:method:`put` requests are handled by the :http:method:`patch`
   handler, any preprocessors or postprocessors specified for the
   :http:method:`put` method will be applied on :http:method:`patch` requests
   *after* the preprocessors or postprocessors specified for the
   :http:method:`patch` method.

Also as seen in the above example, the preprocessors and postprocessors for
each type of request accept different arguments and have different return
values.

* :http:method:`get` for a single instance::

      def get_single_preprocessor(instid):
          """Accepts a single argument, `instid`, the primary key of the
          instance of the model to get.

          The return value is ignored, so this function should return nothing.

          """
          return

      def get_single_postprocessor(data):
          """Accepts a single argument, `data`, which is the dictionary
          representation of the requested instance of the model.

          This function must return a dictionary representing the JSON to
          return to the client.

          """
          return data

  and for the collection::

      def get_many_preprocessor(params):
          """Accepts a single argument, `params`, which is a dictionary
          containing the search parameters for the request.

          This function must return a dictionary which represents the search
          parameters for the request.

          """
          return params


      def get_many_postprocessor(data):
          """Accepts a single argument, `data`, which is the dictionary
          representation of the JSON response which will be returned to the
          client.

          This function must return a dictionary representing the JSON to
          return to the client.

          """
          return data

* :http:method:`patch` (or :http:method:`put`) for a single instance::

      def patch_single_preprocessor(instid, data):
          """Accepts two arguments, `instid`, the primary key of the
          instance of the model to patch, and `data`, the dictionary of fields
          to change on the instance.

          This function must return a dictionary representing the fields to
          change in the specified instance of the model (that is, a modified
          version of `data`).

          """
          return data

      def patch_single_postprocessor(data):
          """Accepts a single argument, `data`, which is the dictionary
          representation of the requested instance of the model.

          This function must return a dictionary representing the JSON to
          return to the client.

          """
          return data

  and for the collection::

      def patch_many_preprocessor(search_params, data):
          """Accepts two arguments: `search_params`, which is a dictionary
          containing the search parameters for the request, and `data`, which
          is a dictionary representing the fields to change on the matching
          instances and the values to which they will be set.

          This function must return a pair of dictionaries representing
          modified versions of the input arguments.

          """
          return search_params, data

      def patch_many_postprocessor(query, data):
          """Accepts two arguments: `query`, which is the SQLAlchemy query
          which was inferred from the search parameters in the query string,
          and `data`, which is the dictionary representation of the JSON
          response which will be returned to the client.

          This function must return a dictionary representing the JSON to
          return to the client.

          """
          return data

* :http:method:`post`::

      def post_preprocessor(data):
          """Accepts a single argument, `data`, which is the dictionary of
          fields to set on the new instance of the model.

          This function must return a dictionary representing the fields to
          set on the new instance of the model.

          """
          return data

      def post_postprocessor(data):
          """Accepts a single argument, `data`, which is the dictionary
          representation of the created instance of the model.

          This function must return a dictionary representing the JSON to
          return to the client.

          """
          return data

* :http:method:`delete`::

      def delete_preprocessor(instid):
          """Accepts a single argument, `instid`, which is the primary key of
          the instance which will be deleted.

          The return value is ignored, so this function should return nothing.

          """
          return

      def delete_postprocessor(was_deleted):
          """Accepts a single argument, `was_deleted`, which represents whether
          the instance has been deleted.

          The return value is ignored, so this function should return nothing.

          """
          return

Note: for more information about search parameters, see :ref:`searchformat`,
and for more information about request and response formats, see
:ref:`requestformat`.

Finally, in order to halt the preprocessing or postprocessing and return an
error response directly to the client, your preprocessor or postprocessor
functions can raise a :exc:`ProcessingException`. If a function raises this
exception, no preprocessing or postprocessing functions that appear later in
the list specified when the API was created will be invoked. For example, an
authentication function can be implemented like this::

    def check_auth(instid):
        # Here, get the current user from the session.
        current_user = ...
        # Next, check if the user is authorized to modify the specified
        # instance of the model.
        if not is_authorized_to_modify(current_user, instid):
            raise ProcessingException(message='Not Authorized',
                                      status_code=401)
    manager.create_api(Person, preprocessors=dict(GET_SINGLE=[check_auth]))

The :exc:`ProcessingException` allows you to specify an HTTP status code for
the generated response and an error message which the client will receive as
part of the JSON in the body of the response.
