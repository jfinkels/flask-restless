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

This creates an endpoint at ``/api/Person`` which responds to
:http:method:`get`, :http:method:`post`, and :http:method:`delete` methods, but
not to other ones like :http:method:`put` or :http:method:`patch`.

The HTTP methods have the following semantics (assuming you have created an API
for an entity named ``Person``). All endpoints which respond with data respond
with serialized JSON strings.

.. http:get:: /api/Person

   Returns a list of all ``Person`` instances.

.. http:get:: /api/Person/(int:id)

   Returns a single ``Person`` instance with the given ``id``.

.. http:get:: /api/Person?q=<searchjson>

   Returns a list of all ``Person`` instances which match the search query
   specified in the query parameter ``q``. For more information on searching,
   see :ref:`searchformat`.

.. http:delete:: /api/Person/(int:id)

   Deletes the person with the given ``id`` and returns :http:statuscode:`204`.

.. http:post:: /api/Person

   Creates a new person in the database and returns its ``id``. The initial
   attributes of the ``Person`` are read as JSON from the body of the
   request. For information about the format of this request, see
   :ref:`requestformat`.

.. http:patch:: /api/Person/(int:id)

   Updates the attributes of the ``Person`` with the given ``id``. The
   attributes are read as JSON from the body of the request. For information
   about the format of this request, see :ref:`requestformat`.

.. http:patch:: /api/Person?q=<searchjson>

   Updates the attributes of all ``Person`` instances which match the search
   query specified in the query parameter ``q``. The attributes are read as
   JSON from the body of the request. For information about searching, see
   :ref:`search`. For information about the format of this request, see
   :ref:`requestformat`.
  
.. http:put:: /api/Person?q=<searchjson>
.. http:put:: /api/Person/(int:id)

   Aliases for :http:patch:`/api/Person`.

API prefix
~~~~~~~~~~

To create an API at a different prefix, use the ``url_prefix`` keyword
argument::

    apimanager.create_api(Person, url_prefix='/api/v2')

Then your API for ``Person`` will be available at ``/api/v2/Person``.
