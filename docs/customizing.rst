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

    apimanager.create_api(session, Person, methods=['GET', 'POST', 'DELETE'])

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

    apimanager.create_api(session, Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/person``.

Collection name
~~~~~~~~~~~~~~~

By default, the name of the collection in the API will be the lowercase name of
the model. To provide a different name for the model, provide a string to the
`collection_name` keyword argument of the :meth:`APIManager.create_api`
method::

    apimanager.create_api(session, Person, collection_name='people')

Then the API will be exposed at ``/api/people`` instead of ``/api/person``.

.. _allowpatchmany:

Enable patching all instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, a :http:patch:`/api/person` request (note the missing ID) will
cause a :http:statuscode:`405` response. By setting the ``allow_patch_many``
keyword argument of the :meth:`APIManager.create_api` method to be ``True``,
:http:patch:`/api/person` requests will patch the provided attributes on all
instances of ``Person``::

    apimanager.create_api(session, Person, allow_patch_many=True)

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

For example, if your model is defined like this::

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
