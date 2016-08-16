Customizing the ReSTful interface
=================================

This section describes how to use the keyword arguments to the
:meth:`~.APIManager.create_api` method to customize the interface created by
Flask-Restless.

.. toctree::
   :hidden:

   serialization
   processors


HTTP methods
------------

By default, the :meth:`.APIManager.create_api` method creates a read-only
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
:meth:`.APIManager.create_api` method.

API prefix
----------

To create an API at a prefix other than the default ``/api``, use the
``url_prefix`` keyword argument::

    apimanager.create_api(Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/person``.

.. _collectionname:

Collection name
---------------

By default, the name of the collection that appears in the URLs of the API will
be the name of the table that backs your model. If your model is a SQLAlchemy
model, this will be the value of its ``__table__.name`` attribute. If your
model is a Flask-SQLAlchemy model, this will be the lowercase name of the model
with camel case changed to all-lowercase with underscore separators. For
example, a class named ``MyModel`` implies a collection name of
``'my_model'``. Furthermore, the URL at which this collection is accessible by
default is ``/api/my_model``.

To provide a different name for the model, provide a string to the
`collection_name` keyword argument of the :meth:`.APIManager.create_api`
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
-----------------------------------

If your model has more than one primary key (one called ``id`` and one called
``username``, for example), you should specify the one to use::

    manager.create_api(User, primary_key='username')

If you do this, Flask-Restless will create URLs like ``/api/user/myusername``
instead of ``/api/user/123``.

.. _validation:

Capturing validation errors
---------------------------

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
``ValidationError``, then call the :meth:`.APIManager.create_api` method with
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

.. _customqueries:

Custom queries
--------------

In cases where it is not possible to use preprocessors or postprocessors
(:doc:`processors`) efficiently, you can provide a custom ``query`` attribute
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

.. _allowmany:

Bulk operations
---------------

Bulk operations are not supported, though they may be in the future.

Custom serialization and deserialization
----------------------------------------

You can provide a custom serializer using the ``serializer_class`` keyword
argument and a custom deserializer using the ``deserializer_class`` keyword
argument. For a full description of how to use these arguments, see
:doc:`serialization`.

Request preprocessors and postprocessors
----------------------------------------

You can have custom code executed before or after Flask-Restless handles the
incoming request by using the ``preprocessors`` and ``postprocessors`` keyword
arguments, respectively. For a full description of how to use these arguments,
see :doc:`processors`.
