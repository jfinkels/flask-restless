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
not to :http:method:`patch`.

If you allow :http:method:`get` requests, you will have access to endpoints of
the following forms.

.. http:get:: /api/person
.. http:get:: /api/person/1
.. http:get:: /api/person/1/comments
.. http:get:: /api/person/1/relationships/comments
.. http:get:: /api/person/1/comments/2

The first four are described explicitly in the JSON API specification. The
last is particular to Flask-Restless; it allows you to access a particular
related resource via a relationship on another resource.

If you allow :http:method:`delete` requests, you will have access to endpoints
of the form

.. http:delete:: /api/person/1

If you allow :http:method:`post` requests, you will have access to endpoints
of the form

.. http:post:: /api/person

Finally, if you allow :http:method:`patch` requests, you will have access to
endpoints of the following forms.

.. http:patch:: /api/person/1
.. http:post:: /api/person/1/relationships/comments
.. http:patch:: /api/person/1/relationships/comments
.. http:delete:: /api/person/1/relationships/comments

The last three allow the client to interact with the relationships of a
particular resource. The last two must be enabled explicitly by setting the
``allow_to_many_replacement`` and ``allow_delete_from_to_many_relationships``,
respectively, to ``True`` when creating an API using the
:meth:`APIManager.create_api` method.

API prefix
~~~~~~~~~~

To create an API at a prefix other than the default ``/api``, use the
``url_prefix`` keyword argument::

    apimanager.create_api(Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/person``.

.. _collectionname:

Collection name
~~~~~~~~~~~~~~~

By default, the name of the collection that appears in the URLs of the API
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

   According to the `JSON API specification`_,

      Note: This spec is agnostic about inflection rules, so the value of type
      can be either plural or singular. However, the same value should be used
      consistently throughout an implementation.

   It's up to you to make sure your collection names are either all plural or
   all singular!

.. _JSON API specification: http://jsonapi.org/format/#document-resource-object-identification

.. _primarykey:

Specifying one of many primary keys
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your model has more than one primary key (one called ``id`` and one called
``username``, for example), you should specify the one to use::

    manager.create_api(User, primary_key='username')

If you do this, Flask-Restless will create URLs like ``/api/user/myusername``
instead of ``/api/user/123``.

.. _allowmany:

Enable bulk operations
~~~~~~~~~~~~~~~~~~~~~~

Bulk operations via the JSON API Bulk extension are not yet supported.

.. _serialization:

Custom serialization
~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 0.17.0

Flask-Restless provides serialization and deserialization that work with the
JSON API specification.  If you wish to have more control over the way
instances of your models are converted to Python dictionary representations,
you can specify a custom serialization function by providing it to
:meth:`APIManager.create_api` via the ``serializer`` keyword argument.
Similarly, to provide a deserialization function that converts a Python
dictionary representation to an instance of your model, use the
``deserializer`` keyword argument.  However, if you provide a serializer that
fails to produce resource objects that satisfy the JSON API specification, your
client will receive non-compliant responses!

Define your serialization functions like this::

    def serialize(instance, only=None):
        return {'data': ...}

``instance`` is an instance of a SQLAlchemy model and the ``only`` argument is
a list; only the fields (that is, the attributes and relationships) whose names
appear as strings in `only` should appear in the returned dictionary. The only
exception is that the keys ``'id'`` and ``'type'`` must always appear,
regardless of whether they appear in `only`. The function must return a
dictionary representation of the object.

Define your deserialization function like this::

    def deserialize(data):
        return Person(...)

``data`` is a dictionary representation of an instance of the model. The
function must return return an instance of `model` that has those attributes.

.. note::

   If you wish to write your own serialization functions, we **strongly
   suggest** using a Python object serialization library instead of writing
   your own serialization functions. This is also likely a better approach than
   specifying which columns to include or exclude (:ref:`includes`) or
   preprocessors and postprocessors (:ref:`processors`).

For example, if you create schema for your database models using
`Marshmallow`_, then you use that library's built-in serialization functions as
follows::

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
source distribution, or `view it online`_

.. _Marshmallow: https://marshmallow.readthedocs.org
.. _view it online: https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/custom_serialization.py

.. _validation:

Capturing validation errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, no validation is performed by Flask-Restless; if you want
validation, implement it yourself in your database models. However, by
specifying a list of exceptions raised by your backend on validation errors,
Flask-Restless will forward messages from raised exceptions to the client in an
error response.

.. COMMENT

   A reasonable validation framework you might use for this purpose is
   `SQLAlchemy Validation
   <https://bitbucket.org/blazelibs/sqlalchemy-validation>`_. You can also use
   the :func:`~sqlalchemy.orm.validates` decorator that comes with SQLAlchemy.

For example, if your validation framework includes an exception called
``ValidationError``, then call the :meth:`APIManager.create_api` method with
the ``validation_exceptions`` keyword argument::

    from cool_validation_framework import ValidationError
    apimanager.create_api(Person, validation_exceptions=[ValidationError],
                          methods=['PATCH', 'POST'])

.. note::

   Currently, Flask-Restless expects that an instance of a specified validation
   error will have a ``errors`` attribute, which is a dictionary mapping field
   name to error description (note: one error per field). If you have a better,
   more general solution to this problem, please visit our `issue tracker`_.

Now when you make :http:method:`post` and :http:method:`patch` requests with
invalid fields, the JSON response will look like this:

.. sourcecode:: http

   HTTP/1.1 400 Bad Request

   {
     "errors": [
       {
         "status": 400,
         "title": "Validation error",
         "detail": "age: must be an integer"
       }
     ]
   }

.. _issue tracker: https://github.com/jfinkels/flask-restless/issues

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

There are many different routes on which you can apply preprocessors and
postprocessors, depending on HTTP method type, whether the client is accessing
a resource or a relationship, whether the client is accessing a collection or a
single resource, etc.

This table states the preprocessors that apply to each type of endpoint.

    ======================== ========================================
    preprocessor name        applies to URLs like…
    ======================== ========================================
    ``GET_COLLECTION``       ``/api/person``
    ``GET_RESOURCE``         ``/api/person/1``
    ``GET_RELATION``         ``/api/person/1/articles``
    ``GET_RELATED_RESOURCE`` ``/api/person/1/articles/2``

    ``DELETE_RESOURCE``      ``/api/person/1``

    ``POST_RESOURCE``        ``/api/person``

    ``PATCH_RESOURCE``       ``/api/person/1``

    ``GET_RELATIONSHIP``     ``/api/person/1/relationships/articles``
    ``DELETE_RELATIONSHIP``  ``/api/person/1/relationships/articles``
    ``POST_RELATIONSHIP``    ``/api/person/1/relationships/articles``
    ``PATCH_RELATIONSHIP``   ``/api/person/1/relationships/articles``
    ======================== ========================================

This table states the postprocessors that apply to each type of endpoint.

    ============================ ========================================
    postprocessor name           applies to URLs like…
    ============================ ========================================
    ``GET_COLLECTION``           ``/api/person``
    ``GET_RESOURCE``             ``/api/person/1``
    ``GET_TO_MANY_RELATION``     ``/api/person/1/articles``
    ``GET_TO_ONE_RELATION``      ``/api/articles/1/author``
    ``GET_RELATED_RESOURCE``     ``/api/person/1/articles/2``

    ``DELETE_RESOURCE``          ``/api/person/1``

    ``POST_RESOURCE``            ``/api/person``

    ``PATCH_RESOURCE``           ``/api/person/1``

    ``GET_TO_MANY_RELATIONSHIP`` ``/api/person/1/relationships/articles``
    ``GET_TO_ONE_RELATIONSHIP``  ``/api/articles/1/relationships/author``
    ``GET_RELATIONSHIP``         ``/api/person/1/relationships/articles``
    ``DELETE_RELATIONSHIP``      ``/api/person/1/relationships/articles``
    ``POST_RELATIONSHIP``        ``/api/person/1/relationships/articles``
    ``PATCH_RELATIONSHIP``       ``/api/person/1/relationships/articles``
    ============================ ========================================

Each type of preprocessor or postprocessor requires different
arguments. For preprocessors:

    ======================== ===================================================================================
    preprocessor name        keyword arguments
    ======================== ===================================================================================
    ``GET_COLLECTION``       ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RESOURCE``         ``resource_id``
    ``GET_RELATION``         ``resource_id``, ``relation_name``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RELATED_RESOURCE`` ``resource_id``, ``relation_name``, ``related_resource_id``

    ``DELETE_RESOURCE``      ``resource_id``

    ``POST_RESOURCE``        ``data``

    ``PATCH_RESOURCE``       ``resource_id``, ``data``

    ``GET_RELATIONSHIP``     ``resource_id``, ``relation_name``
    ``DELETE_RELATIONSHIP``  ``resource_id``, ``relation_name``
    ``POST_RELATIONSHIP``    ``resource_id``, ``relation_name``, ``data``
    ``PATCH_RELATIONSHIP``   ``resource_id``, ``relation_name``, ``data``
    ======================== ===================================================================================

For postprocessors:

    ============================ ===========================================================
    postprocessor name            keyword arguments
    ============================ ===========================================================
    ``GET_COLLECTION``           ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RESOURCE``             ``result``
    ``GET_TO_MANY_RELATION``     ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_TO_ONE_RELATION``      ``result``
    ``GET_RELATED_RESOURCE``     ``result``

    ``DELETE_RESOURCE``          ``was_deleted``

    ``POST_RESOURCE``            ``result``

    ``PATCH_RESOURCE``           ``result``

    ``GET_TO_MANY_RELATIONSHIP`` ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_TO_ONE_RELATIONSHIP``  ``result``
    ``DELETE_RELATIONSHIP``      ``was_deleted``
    ``POST_RELATIONSHIP``        none
    ``PATCH_RELATIONSHIP``       none
    ============================ ===========================================================

How can one use these tables to create a preprocessor or postprocessor? If you
want to create a preprocessor that will be applied on :http:method:`get`
requests to ``/api/person``, first define a function that accepts the keyword
arguments you need, and has a ``**kw`` argument for any additional keyword
arguments (and any new arguments that may appear in future versions of
Flask-Restless)::

    def fetch_preprocessor(filters=None, sort=None, group_by=None, single=None,
                           **kw):
        # Here perform any application-specific code...

Next, instruct these preprocessors to be applied by Flask-Restless by using the
``preprocessors`` keyword argument to :meth:`APIManager.create_api`. The value
of this argument must be a dictionary in which each key is a string containing
a processor name and each value is a list of functions to be applied for that
request::

    preprocessors = {'GET_COLLECTION': [fetch_preprocessor]}
    manager.create_api(Person, preprocessors=preprocessors)

For preprocessors for endpoints of the form ``/api/person/1``, a returned value
will be interpreted as the resource ID for the request. For example, if a
preprocessor for a :http:method:`get` request to ``/api/person/1`` returns the
string ``'foo'``, then Flask-Restless will behave as if the request were
originally for the URL ``/api/person/foo``.  For preprocessors for endpoints of
the form ``/api/person/1/articles`` or
``/api/person/1/relationships/articles``, the function can return either one
value, in which case the resource ID will be replaced with the return value, or
a two-tuple, in which case both the resource ID and the relationship name will
be replaced. Finally, for preprocessors for endpoints of the form
``/api/person/1/articles/2``, the function can return one, two, or three
values; if three values are returned, the resource ID, the relationship name,
and the related resource ID are all replaced. (If multiple preprocessors are
specified for a single HTTP method and each one has a return value,
Flask-Restless will only remember the value returned by the last preprocessor
function.)

Those preprocessors and postprocessors that accept dictionaries as parameters
can (and should) modify their arguments *in-place*. That means the changes made
to, for example, the ``result`` dictionary will be seen by the Flask-Restless
view functions and ultimately returned to the client.

.. note::

   For more information about the ``filters`` and ``single`` keyword arguments,
   see :ref:`filtering`. For more information about ``sort`` and ``group_by``
   keyword arguments, see :ref:`sorting`.

In order to halt the preprocessing or postprocessing and return an error
response directly to the client, your preprocessor or postprocessor functions
can raise a :exc:`ProcessingException`. If a function raises this exception, no
preprocessing or postprocessing functions that appear later in the list
specified when the API was created will be invoked. For example, an
authentication function can be implemented like this::

    def check_auth(resource_id=None, **kw):
        # Here, get the current user from the session.
        current_user = ...
        # Next, check if the user is authorized to modify the specified
        # instance of the model.
        if not is_authorized_to_modify(current_user, instance_id):
            raise ProcessingException(detail='Not Authorized', status=401)
    manager.create_api(Person, preprocessors=dict(GET_SINGLE=[check_auth]))

The :exc:`ProcessingException` allows you to specify as keyword arguments to
the constructor the elements of the JSON API `error object`_. If no arguments
are provided, the error is assumed to have status code :http:statuscode:`400`.

.. _error object: https://jsonapi.org/format/#error-objects

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
            raise ProcessingException(detail='Not authenticated', status=401)

    app = Flask(__name__)
    preprocessors = {'POST_RESOURCE': [auth_func]}
    api_manager = APIManager(app, session=session, preprocessors=preprocessors)
    api_manager.create_api(User)

Preprocessors for collections
-----------------------------

When the server receives, for example, a :http:method:`get` request for
``/api/person``, Flask-Restless interprets this request as a search with no
filters (that is, a search for all instances of ``Person`` without
exception). In other words, a :http:method:`get` request to ``/api/person`` is
roughly equivalent to the same request to
``/api/person?filter[objects]=[]``. Therefore, if you want to filter the set of
``Person`` instances returned by such a request, you can create a
``GET_COLLECTION`` preprocessor that *appends filters* to the ``filters``
keyword argument. For example::

    def preprocessor(filters=None, **kw):
        # This checks if the preprocessor function is being called before a
        # request that does not have search parameters.
        if filters is None:
            return
        # Create the filter you wish to add; in this case, we include only
        # instances with ``id`` not equal to 1.
        filt = dict(name='id', op='neq', val=1)
        # *Append* your filter to the list of filters.
        filters.append(filt)

    preprocessors = {'GET_COLLECTION': [preprocessor]}
    manager.create_api(Person, preprocessors=preprocessors)

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

Then :http:method:`get` requests to, for example, ``/api/person`` will only
reveal instances of ``Person`` who also are in the group named "students".

.. _authentication:

Requiring authentication for some methods
-----------------------------------------

If you want certain HTTP methods to require authentication, use preprocessors::

    from flask import Flask
    from flask.ext.restless import APIManager
    from flask.ext.restless import ProcessingException
    from flask.ext.login import current_user
    from mymodels import User

    def auth_func(*args, **kwargs):
        if not current_user.is_authenticated():
            raise ProcessingException(detail='Not authenticated', status=401)

    app = Flask(__name__)
    api_manager = APIManager(app)
    # Set `auth_func` to be a preprocessor for any type of endpoint you want to
    # be guarded by authentication.
    preprocessors = {'GET_RESOURCE': [auth_func], ...}
    api_manager.create_api(User, preprocessors=preprocessors)

For a more complete example using `Flask-Login`_, see the
:file:`examples/server_configurations/authentication` directory in the source
distribution, or `view the authentication example online`_.

.. _Flask-Login: https://packages.python.org/Flask-Login
.. _view the authentication example online: https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/authentication
