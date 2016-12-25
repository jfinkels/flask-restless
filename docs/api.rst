API
===

.. module:: flask_restless

This part of the documentation documents all the public classes and functions
in Flask-Restless.

The API Manager class
---------------------

.. autoclass:: APIManager
   :members: init_app, create_api, create_api_blueprint

.. autoclass:: IllegalArgumentError


Search helper functions
-----------------------

.. autofunction:: register_operator


Global helper functions
-----------------------

.. autofunction:: collection_name(model, _apimanager=None)

.. autofunction:: model_for(collection_name, _apimanager=None)

.. autofunction:: serializer_for(model, _apimanager=None)

.. autofunction:: primary_key_for(model, _apimanager=None)

.. autofunction:: url_for(model, instid=None, relationname=None, relationinstid=None, _apimanager=None, **kw)

Serialization and deserialization
---------------------------------

.. autoclass:: DefaultSerializer
   :members: serialize, serialize_many

.. autoclass:: DefaultDeserializer
   :members: deserialize

.. autoclass:: SerializationException

.. autoclass:: DeserializationException
   :members: message, detail, status

.. autofunction:: simple_serialize

.. autofunction:: simple_serialize_many

.. autoclass:: MultipleExceptions


Pre- and postprocessor helpers
------------------------------

.. autoclass:: ProcessingException
