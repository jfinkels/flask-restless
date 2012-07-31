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

    apimanager.create_api(Person, allow_patch_many=True)

.. _validation:

Capturing validation errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, no validation is performed by Flask-Restless; if you want
validation, implement it yourself in your database models. However, by
specifying a list of exceptions raised by your backend on validation errors,
Flask-Restless will forward messages from raised exceptions to the client in an
error response.

A reasonable validation framework you might use for this purpose is `SQLAlchemy
Validation <https://bitbucket.org/rsyring/sqlalchemy-validation>`_. You can
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

.. _authentication:

Specifying which columns are provided in responses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, all columns of your model will be exposed by the API. If the
``include_columns`` keyword argument is an iterable of strings, *only* columns
with those names (that is, the strings represent the names of attributes of the
model which are ``Column`` objects) will be provided in JSON responses for
:http:method:`get` requests.

For example, if your model is defined like this (using Flask-SQLAlchemy)::

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

Pagination
~~~~~~~~~~

To set the number of results returned per page, use the ``results_per_page``
keyword arguments to the :meth:`APIManager.create_api` method. The default
number of results per page is ten. If this is set to anything except a positive
integer, pagination will be disabled and all results will be returned on each
:http:method:`get` request.

.. attention::

   Disabling pagination can result in large responses!

For example, to set each page to include only two results::

    apimanager.create_api(Person, results_per_page=2)

Then a request to :http:get:`/api/person` will return a JSON object which looks
like this:

.. sourcecode:: javascript

   {
     "page": 1,
     "objects": [
       {"name": "Jeffrey", "id": 1},
       {"name": "John", "id": 2}
     ]
   }

For more information on using pagination, see :ref:`pagination`.

Updating POST parameters before committing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To apply some function to the :http:method:`post` form parameters before the
database model is created, specify the ``post_form_preprocessor`` keyword. The
value of ``post_form_preprocessor`` must be a function which accepts a single
dictionary as input and outputs a dictionary. The input dictionary is the
dictionary mapping names of columns of the model to values to assign to that
column, as specified by the JSON provided in the body of the
:http:method:`post` request. The output dictionary should be the same, but with
whatever additions, deletions, or modifications you wish.

For example, if the client is making a :http:method:`post` request to a model
which which has an ``owner`` field which should contain the ID of the currently
logged in user, you may wish for the server to append the mapping ``('owner',
current_user.id)`` to the form parameters. In this case, you would set the
value of ``post_form_processor`` to be the function defined below::

    def add_user_id(dictionary):
        dictionary['owner'] = current_user.id
        return dictionary
