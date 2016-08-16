Custom serialization
====================

.. versionadded:: 0.17.0
.. versionchanged:: 1.0.0b1

   Transitioned from function-based serialization to class-based serialization.

Flask-Restless provides serialization and deserialization that work with the
JSON API specification.  If you wish to have more control over the way
instances of your models are converted to Python dictionary representations,
you can specify custom serialization by providing it to
:meth:`.APIManager.create_api` via the ``serializer_class`` keyword argument.
Similarly, to provide a deserializer that converts a Python dictionary
representation to an instance of your model, use the ``deserializer_class``
keyword argument. However, if you provide a serializer that fails to produce
resource objects that satisfy the JSON API specification, your client will
receive non-compliant responses!

Your serializer classes must be a subclass of :class:`.DefaultSerializer` and
can override the :meth:`~.DefaultSerializer.serialize` and
:meth:`~.DefaultSerializer.serialize_many` methods to provide custom
serialization. These methods take an instance or instances as input and return
a dictionary representing a JSON API document. Each also accepts an ``only``
keyword argument, indicating the sparse fieldsets requested by the client::

    from flask_restless import DefaultSerializer

    class MySerializer(DefaultSerializer):

        def serialize(self, instance, only=None):
            super_serialize = super(DefaultSerializer, self).serialize
            document = super_serialize(instance, only=only)
            # Make changes to the document here...
            ...
            return document

        def serialize_many(self, instances, only=None):
            super_serialize = super(DefaultSerializer, self).serialize_many
            document = super_serialize(instances, only=only)
            # Make changes to the document here...
            ...
            return document

``instance`` is an instance of a SQLAlchemy model, ``instances`` is a list of
instances, and the ``only`` argument is a list; only the fields (that is, the
attributes and relationships) whose names appear as strings in `only` should
appear in the returned dictionary. The only exception is that the keys ``'id'``
and ``'type'`` must always appear, regardless of whether they appear in
`only`. The function must return a dictionary representation of the resource
object.

Flask-Restless also provides functional access to the default serialization,
via the :func:`.simple_serialize` and :func:`.simple_serialize_many` functions,
which return the result of the built-in default serialization.

For deserialization, define your custom deserialization class like this::

    from flask_restless import DefaultDeserializer

    class MyDeserializer(DefaultDeserializer):

        def deserialize(self, document):
            return Person(...)

``document`` is a dictionary representation of the *complete* incoming JSON API
document, where the ``data`` element contains the primary resource object or
objects. The function must return an instance of the model that has the
requested fields. If you override the constructor, it must take two positional
arguments, `session` and `model`.

Your code can raise a :exc:`.SerializationException` when overriding the
:meth:`.DefaultSerializer.serialize` method, and similarly a
:exc:`.DeserializationException` in the
:meth:`.DefaultDeserializer.deserialize` method; Flask-Restless will
automatically catch those exceptions and format a `JSON API error response`_.
If you wish to collect multiple exceptions (for example, if several fields of a
resource provided to the :meth:`~.DefaultDeserializer.deserialize` method fail
validation) you can raise a :exc:`.MultipleExceptions` exception, providing a
list of other serialization or deserialization exceptions at instantiation
time.

.. note::

   If you wish to write your own serialization functions, we **strongly
   suggest** using a Python object serialization library instead of writing
   your own serialization functions. This is also likely a better approach than
   specifying which columns to include or exclude (:doc:`includes`) or
   preprocessors and postprocessors (:doc:`processors`).

For example, if you create schema for your database models using
`Marshmallow`_, then you use that library's built-in serialization functions as
follows::

    class PersonSchema(Schema):
        id = fields.Integer()
        name = fields.String()

        def make_object(self, data):
            return Person(**data)

    class PersonSerializer(DefaultSerializer):

        def serialize(self, instance, only=None):
            person_schema = PersonSchema(only=only)
            return person_schema.dump(instance).data

        def serialize_many(self, instances, only=None):
            person_schema = PersonSchema(many=True, only=only)
            return person_schema.dump(instances).data


    class PersonDeserializer(DefaultDeserializer):

        def deserialize(self, document):
            person_schema = PersonSchema()
            return person_schema.load(instance).data

        # # JSON API doesn't currently allow bulk creation of resources. When
        # # it does, either in the specification or in an extension, this is
        # # how you would implement it.
        # def deserialize_many(self, document):
        #     person_schema = PersonSchema(many=True)
        #     return person_schema.load(instance).data

    manager = APIManager(app, session=session)
    manager.create_api(Person, methods=['GET', 'POST'],
                       serializer_class=PersonSerializer,
                       deserializer_class=PersonDeserializer)

For a complete version of this example, see the
:file:`examples/server_configurations/custom_serialization.py` module in the
source distribution, or `view it online`_.

.. _JSON API error response: http://jsonapi.org/format/#errors
.. _Marshmallow: https://marshmallow.readthedocs.org
.. _view it online: https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/custom_serialization.py

Per-model serialization
-----------------------

The correct serialization function will be used for each type of SQLAlchemy
model for which you invoke :meth:`.APIManager.create_api`. For example, if you
create two APIs, one for ``Person`` objects and one for ``Article`` objects, ::

    manager.create_api(Person, serializer=person_serializer)
    manager.create_api(Article, serializer=article_serializer)

and then make a request like

.. sourcecode:: http

   GET /api/article/1?include=author HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

then Flask-Restless will use the ``article_serializer`` function to serialize
the primary data (that is, the top-level ``data`` element in the response
document) and the ``person_serializer`` to serialize the included ``Person``
resource.

