.. _customizing:

Customizing the ReSTful interface
=================================

HTTP methods
~~~~~~~~~~~~

By default, the :meth:`~flaskext.restless.APIManager.create_api` method creates
a read-only interface; requests with HTTP methods other than :http:method:`GET`
will cause a response with :http:statuscode:`405`. To explicitly specify which
methods should be allowed for the endpoint, pass a list as the value of keyword
argument ``methods``::

    apimanager.create_api(Person, methods=['GET', 'POST', 'DELETE'])

This creates an endpoint at ``/api/person`` which responds to
:http:method:`get`, :http:method:`post`, and :http:method:`delete` methods, but
not to other ones like :http:method:`put` or :http:method:`patch`.

The HTTP methods have the following semantics (assuming you have created an API
for an entity named ``Person``). All endpoints which respond with data respond
with serialized JSON strings.

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

.. http:patch:: /api/person?q=<searchjson>

   Updates the attributes of all ``Person`` instances which match the search
   query specified in the query parameter ``q``. The attributes are read as
   JSON from the body of the request. For information about searching, see
   :ref:`search`. For information about the format of this request, see
   :ref:`requestformat`.
  
.. http:put:: /api/person?q=<searchjson>
.. http:put:: /api/person/(int:id)

   Aliases for :http:patch:`/api/person`.

API prefix
~~~~~~~~~~

To create an API at a different prefix, use the ``url_prefix`` keyword
argument::

    apimanager.create_api(Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/person``.

Collection name
~~~~~~~~~~~~~~~

By default, the name of the collection in the API will be the lowercase name of
the model. To provide a different name for the model, provide a string to the
`collection_name` keyword argument of the :meth:`APIManager.create_api`
method::

    apimanager.create_api(Person, collection_name='people')

Then the API will be exposed at ``/api/people`` instead of ``/api/person``.
