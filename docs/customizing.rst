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

.. http:delete:: /api/person

   This is only available if the ``allow_delete_many`` keyword argument is set
   to ``True`` when calling the :meth:`~APIManager.create_api` method. For more
   information, see :ref:`allowmany`.

   Deletes all instances of ``Person`` that match the search query provided in
   the ``q`` URL query paremeter. For more information on search parameters,
   see :ref:`searchformat`.

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
   information, see :ref:`allowmany`.

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

.. _collectionname:

Collection name
~~~~~~~~~~~~~~~

By default, the name of the collection which appears in the URLs of the API
will be the name of the table that backs your model. If your model is a
SQLAlchemy model, this will be the value of its ``__tablename__`` attribute. If
your model is a Flask-SQLAlchemy model, this will be the lowercase name of the
model with camel case changed to all-lowercase with underscore separators. For
example, a class named ``MyModel`` implies a collection name of
``'my_model'``. Furthermore, the URL at which this collection is accessible by
default is ``/api/my_model``.

To provide a different name for the model, provide a string to the
`collection_name` keyword argument of the :meth:`APIManager.create_api`
method::

    apimanager.create_api(Person, collection_name='people')

Then the API will be exposed at ``/api/people`` instead of ``/api/person``.

.. note::

   According to the `JSON API standard`_,

   .. blockquote::

      Note: This spec is agnostic about inflection rules, so the value of type
      can be either plural or singular. However, the same value should be used
      consistently throughout an implementation.

   It's up to you to make sure your collection names are either all plural or
   all singular!

.. _JSON API standard: http://jsonapi.org/format/#document-structure-resource-types

Specifying one of many primary keys
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your model has more than one primary key (one called ``id`` and one called
``username``, for example), you should specify the one to use::

    manager.create_api(User, primary_key='username')

If you do this, Flask-Restless will create URLs like ``/api/user/myusername``
instead of ``/api/user/137``.

.. _allowmany:

Enable bulk patching or deleting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, a :http:patch:`/api/person` request (note the missing ID) will
cause a :http:statuscode:`405` response. By setting the ``allow_patch_many``
keyword argument of the :meth:`APIManager.create_api` method to be ``True``,
:http:patch:`/api/person` requests will patch the provided attributes on all
instances of ``Person``::

    apimanager.create_api(Person, methods=['PATCH'], allow_patch_many=True)

If search parameters are provided via the ``q`` query parameter as described in
:ref:`searchformat`, only those instances matching the search will be patched.

Similarly, to allow bulk deletions, set the ``allow_delete_many`` keyword
argument to be ``True``.

.. _serialization:

Custom serialization
~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 0.17.0

Flask-Restless provides very basic object serialization and deserialization. If
you wish to have more control over the way instances of your models are
converted to Python dictionary representations, you can specify a custom
serialization function by providing it to :meth:`APIManager.create_api` via the
``serializer`` keyword argument. Similarly, to provide a deserialization
function that converts a Python dictionary representation to an instance of
your model, use the ``deserializer`` keyword argument.

The serialization function must take a single argument representing the
instance of the model to serialize, and must return a dictionary representation
of that instance. The deserialization function must take a single argument
representing the dictionary representation of an instance of the model and must
return an instance of `model` that has those attributes.

.. note::

   We **strongly suggest** using a Python object serialization library instead
   of writing your own serialization functions. This is also likely a better
   approach than specifying which columns to include or exclude
   (:ref:`includes`) or preprocessors and postprocessors (:ref:`processors`).

For example, if you create schema for your database models using `Marshmallow
<https://marshmallow.readthedocs.org>`_), then you use that library's built-in
serialization functions as follows::

    class PersonSchema(Schema):
        id = fields.Integer()
        name = fields.String()

        def make_object(self, data):
            print('MAKING OBJECT FROM', data)
            return Person(**data)

    person_schema = PersonSchema()

    def person_serializer(instance):
        return person_schema.dump(instance).data

    def person_deserializer(data):
        return person_schema.load(data).data

    manager = APIManager(app, session=session)
    manager.create_api(Person, methods=['GET', 'POST'],
                       serializer=person_serializer,
                       deserializer=person_deserializer)

For a complete version of this example, see the
:file:`examples/server_configurations/custom_serialization.py` module in the
source distribution, or view it online at `GitHub
<https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/custom_serialization.py>`__.

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

.. warning::

   The include/exclude system described in this section is very simplistic; a
   much better way to specify which columns are included in your responses is
   to use a Python object serialization library and specify custom
   serialization and deserialization functions as described in
   :ref:`serialization`.

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

To include the return value of an arbitrary method defined on a model, use the
``include_methods`` keyword argument. This argument must be an iterable of
strings representing methods with no arguments (other than ``self``) defined on
the model for which the API will be created::

    class Person(Base):
        __tablename__ = 'person'
        id = Column(Integer, primary_key=True)
        name = Column(Unicode)
        age = Column(Integer)

        def name_and_age(self):
            return "%s (aged %d)" % (self.name, self.age)

    include_methods = ['name_and_age']
    manager.create_api(Person, include_methods=['name_and_age'])

A response to a :http:method:`get` request will then look like this:

.. sourcecode:: javascript

   {
     "id": 1,
     "name": "Paul McCartney",
     "age": 64,
     "name_and_age": "Paul McCartney (aged 64)"
   }

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
    def pre_get_single(**kw): pass
    def pre_get_many(**kw): pass
    def post_patch_many(**kw): pass
    def pre_delete(**kw): pass

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

* ``'POST'`` for requests to post a new instance of the model.
* ``'GET_SINGLE'`` for requests to get a single instance of the model.
* ``'GET_MANY'`` for requests to get multiple instances of the model.
* ``'PATCH_SINGLE'`` or ``'PUT_SINGLE'`` for requests to patch a single
  instance of the model.
* ``'PATCH_MANY'`` or ``'PUT_MANY'`` for requests to patch multiple instances
  of the model.
* ``'DELETE_SINGLE'`` for requests to delete an instance of the model.
* ``'DELETE_MANY'`` for requests to delete multiple instances of the model.

.. note::

   Since :http:method:`put` requests are handled by the :http:method:`patch`
   handler, any preprocessors or postprocessors specified for the
   :http:method:`put` method will be applied on :http:method:`patch` requests
   *after* the preprocessors or postprocessors specified for the
   :http:method:`patch` method.

The preprocessors and postprocessors for each type of request accept different
arguments. Most of them should have no return value (more specifically, any
returned value is ignored). The return value from each of the ``GET_SINGLE``,
``PATCH_SINGLE``, and ``DELETE_SINGLE`` preprocessors is interpreted as a value
with which to replace ``instance_id``, the variable containing the value of the
primary key of the requested instance of the model. For example, if a request
for :http:get:`/api/person/1` encounters a preprocessor (for ``GET_SINGLE``)
that returns the integer ``8``, Flask-Restless will continue to process the
request as if it had received :http:get:`/api/person/8`. (If multiple
preprocessors are specified for a single HTTP method and each one has a return
value, Flask-Restless will only remember the value returned by the last
preprocessor function.)

Those preprocessors and postprocessors that accept dictionaries as parameters
can (and should) modify their arguments *in-place*. That means the changes made
to, for example, the ``result`` dictionary will be seen by the Flask-Restless
view functions and ultimately returned to the client.

The arguments to the preprocessor and postprocessor functions will be provided
as keyword arguments, so you should always add ``**kw`` as the final argument
when defining a preprocessor or postprocessor function. This way, you can
specify only the keyword arguments you need when defining your
functions. Furthermore, if a new version of Flask-Restless changes the API,
you can update Flask-Restless without breaking your code.

.. versionchanged:: 0.16.0
   Replaced ``DELETE`` with ``DELETE_MANY`` and ``DELETE_SINGLE``.

.. versionadded:: 0.13.0
   Functions provided as postprocessors for ``GET_MANY`` and ``PATCH_MANY``
   requests receive the ``search_params`` keyword argument, so that both
   preprocessors and postprocessors have access to this information.

* :http:method:`get` for a single instance::

      def get_single_preprocessor(instance_id=None, **kw):
          """Accepts a single argument, `instance_id`, the primary key of the
          instance of the model to get.

          """
          pass

      def get_single_postprocessor(result=None, **kw):
          """Accepts a single argument, `result`, which is the dictionary
          representation of the requested instance of the model.

          """
          pass

  and for the collection::

      def get_many_preprocessor(search_params=None, **kw):
          """Accepts a single argument, `search_params`, which is a dictionary
          containing the search parameters for the request.

          """
          pass

      def get_many_postprocessor(result=None, search_params=None, **kw):
          """Accepts two arguments, `result`, which is the dictionary
          representation of the JSON response which will be returned to the
          client, and `search_params`, which is a dictionary containing the
          search parameters for the request (that produced the specified
          `result`).

          """
          pass

* :http:method:`patch` (or :http:method:`put`) for a single instance::

      def patch_single_preprocessor(instance_id=None, data=None, **kw):
          """Accepts two arguments, `instance_id`, the primary key of the
          instance of the model to patch, and `data`, the dictionary of fields
          to change on the instance.

          """
          pass

      def patch_single_postprocessor(result=None, **kw):
          """Accepts a single argument, `result`, which is the dictionary
          representation of the requested instance of the model.

          """
          pass

  and for the collection::

      def patch_many_preprocessor(search_params=None, data=None, **kw):
          """Accepts two arguments: `search_params`, which is a dictionary
          containing the search parameters for the request, and `data`, which
          is a dictionary representing the fields to change on the matching
          instances and the values to which they will be set.

          """
          pass

      def patch_many_postprocessor(query=None, data=None, search_params=None,
                                   **kw):
          """Accepts three arguments: `query`, which is the SQLAlchemy query
          which was inferred from the search parameters in the query string,
          `data`, which is the dictionary representation of the JSON response
          which will be returned to the client, and `search_params`, which is a
          dictionary containing the search parameters for the request.

          """
          pass

* :http:method:`post`::

      def post_preprocessor(data=None, **kw):
          """Accepts a single argument, `data`, which is the dictionary of
          fields to set on the new instance of the model.

          """
          pass

      def post_postprocessor(result=None, **kw):
          """Accepts a single argument, `result`, which is the dictionary
          representation of the created instance of the model.

          """
          pass


* :http:method:`delete` for a single instance::

      def delete_single_preprocessor(instance_id=None, **kw):
          """Accepts a single argument, `instance_id`, which is the primary key
          of the instance which will be deleted.

          """
          pass

      def delete_postprocessor(was_deleted=None, **kw):
          """Accepts a single argument, `was_deleted`, which represents whether
          the instance has been deleted.

          """
          pass

  and for the collection::

      def delete_many_preprocessor(search_params=None, **kw):
          """Accepts a single argument, `search_params`, which is a dictionary
          containing the search parameters for the request.

          """
          pass

      def delete_many_postprocessor(result=None, search_params=None, **kw):
          """Accepts two arguments: `result`, which is the dictionary
          representation of which is the dictionary representation of the JSON
          response which will be returned to the client, and `search_params`,
          which is a dictionary containing the search parameters for the
          request.

          """
          pass

.. note::

   For more information about search parameters, see :ref:`searchformat`, and
   for more information about request and response formats, see
   :ref:`requestformat`.

In order to halt the preprocessing or postprocessing and return an error
response directly to the client, your preprocessor or postprocessor functions
can raise a :exc:`ProcessingException`. If a function raises this exception, no
preprocessing or postprocessing functions that appear later in the list
specified when the API was created will be invoked. For example, an
authentication function can be implemented like this::

    def check_auth(instance_id=None, **kw):
        # Here, get the current user from the session.
        current_user = ...
        # Next, check if the user is authorized to modify the specified
        # instance of the model.
        if not is_authorized_to_modify(current_user, instance_id):
            raise ProcessingException(description='Not Authorized',
                                      code=401)
    manager.create_api(Person, preprocessors=dict(GET_SINGLE=[check_auth]))

The :exc:`ProcessingException` allows you to specify an HTTP status code for
the generated response and an error message which the client will receive as
part of the JSON in the body of the response.

.. _universal:

Universal preprocessors and postprocessors
------------------------------------------

.. versionadded:: 0.13.0

The previous section describes how to specify a preprocessor or postprocessor
on a per-API (that is, a per-model) basis. If you want a function to be
executed for *all* APIs created by a :class:`APIManager`, you can use the
``preprocessors`` or ``postprocessors`` keyword arguments in the constructor of
the :class:`APIManager` class. These keyword arguments have the same format as
the corresponding ones in the :meth:`APIManager.create_api` method as described
above. Functions specified in this way are prepended to the list of
preprocessors or postprocessors specified in the :meth:`APIManager.create_api`
method.

This may be used, for example, if all :http:method:`post` requests require
authentication::

    from flask import Flask
    from flask.ext.restless import APIManager
    from flask.ext.restless import ProcessingException
    from flask.ext.login import current_user
    from mymodels import User
    from mymodels import session

    def auth_func(*args, **kw):
        if not current_user.is_authenticated():
            raise ProcessingException(description='Not authenticated!', code=401)

    app = Flask(__name__)
    api_manager = APIManager(app, session=session,
                             preprocessors=dict(POST=[auth_func]))
    api_manager.create_api(User)


Preprocessors for collections
-----------------------------

When the server receives, for example, a request for :http:get:`/api/person`,
Flask-Restless interprets this request as a search with no filters (that is, a
search for all instances of ``Person`` without exception). In other words,
:http:get:`/api/person` is roughly equivalent to
:http:get:`/api/person?q={}`. Therefore, if you want to filter the set of
``Person`` instances returned by such a request, you can create a preprocessor
for a :http:method:`get` request to the collection endpoint that *appends
filters* to the ``search_params`` keyword argument. For example::

    def preprocessor(search_params=None, **kw):
        # This checks if the preprocessor function is being called before a
        # request that does not have search parameters.
        if search_params is None:
            return
        # Create the filter you wish to add; in this case, we include only
        # instances with ``id`` not equal to 1.
        filt = dict(name='id', op='neq', val=1)
        # Check if there are any filters there already.
        if 'filters' not in search_params:
            search_params['filters'] = []
        # *Append* your filter to the list of filters.
        search_params['filters'].append(filt)

    apimanager.create_api(Person, preprocessors=dict(GET_MANY=[preprocessor]))

.. _customqueries:

Custom queries
~~~~~~~~~~~~~~

In cases where it is not possible to use preprocessors or postprocessors
(:ref:`processors`) efficiently, you can provide a custom ``query`` attribute
to your model instead. The attribute can either be a SQLAlchemy query
expression or a class method that returns a SQLAlchemy query
expression. Flask-Restless will use this ``query`` attribute internally,
however it is defined, instead of the default ``session.query(Model)`` (in the
pure SQLAlchemy case) or ``Model.query`` (in the Flask-SQLAlchemy
case). Flask-Restless uses a query during most :http:method:`get` and
:http:method:`patch` requests to find the model(s) being requested.

You may want to use a custom query attribute if you want to reveal only certain
information to the client. For example, if you have a set of people and you
only want to reveal information about people from the group named "students",
define a query class method this way::

    class Group(Base):
        __tablename__ = 'group'
        id = Column(Integer, primary_key=True)
        groupname = Column(Unicode)
        people = relationship('Person')

    class Person(Base):
        __tablename__ = 'person'
        id = Column(Integer, primary_key=True)
        group_id = Column(Integer, ForeignKey('group.id'))
        group = relationship('Group')

        @classmethod
        def query(cls):
            original_query = session.query(cls)
            condition = (Group.groupname == 'students')
            return original_query.join(Group).filter(condition)

Then requests to, for example, :http:get:`/api/person` will only reveal
instances of ``Person`` who also are in the group named "students".

.. _authentication:

Requiring authentication for some methods
-----------------------------------------

If you want certain HTTP methods to require authentication, use preprocessors::

    from flask import Flask
    from flask.ext.restless import APIManager
    from flask.ext.restless import NO_CHANGE
    from flask.ext.restless import ProcessingException
    from flask.ext.login import current_user
    from mymodels import User

    def auth_func(*args, **kwargs):
        if not current_user.is_authenticated():
            raise ProcessingException(description='Not authenticated!', code=401)
        return True

    app = Flask(__name__)
    api_manager = APIManager(app)
    api_manager.create_api(User, preprocessors=dict(GET_SINGLE=[auth_func],
                                                    GET_MANY=[auth_func]))

For a more complete example using `Flask-Login
<packages.python.org/Flask-Login/>`_, see the
:file:`examples/server_configurations/authentication` directory in the source
distribution, or view it online at `GitHub
<https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/authentication>`__.

Enabling Cross-Origin Resource Sharing (CORS)
---------------------------------------------

`Cross-Origin Resource Sharing (CORS) <http://enable-cors.org>`_ is a protocol
that allows JavaScript HTTP clients to make HTTP requests across Internet
domain boundaries while still protecting against cross-site scripting (XSS)
attacks. If you have access to the HTTP server that serves your Flask
application, I recommend configuring CORS there, since such concerns are beyond
the scope of Flask-Restless. However, in case you need to support CORS at the
application level, you should create a function that adds the necessary HTTP
headers after the request has been processed by Flask-Restless (that is, just
before the HTTP response is sent from the server to the client) using the
:meth:`flask.Blueprint.after_request` method::

    from flask import Flask
    from flask.ext.restless import APIManager

    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = 'example.com'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        # Set whatever other headers you like...
        return response

    app = Flask(__name__)
    manager = APIManager(app)
    blueprint = manager.create_api(Person)
    blueprint.after_request(add_cors_headers)
