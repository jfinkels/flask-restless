Flask-Restless
==============

**Flask-Restless** provides simple generation of ReSTful APIs for database
models given as Elixir entities. The generated APIs send and receive messages
in JSON format. To get started now, see `Quickstart`_.

Quickstart
----------

For the restless::

    import flask.ext.restless
    from elixir import Date, DateTime, Field, Unicode
    from elixir import ManyToOne, OneToMany
    from elixir import create_all, metadata, setup_all

    # Entity classes must inherit from flaskext.restless.Entity. Other than
    # that, the definition of the model is exactly the same.
    class Person(flask.ext.restless.Entity):
        name = Field(Unicode, unique=True)
        birth_date = Field(Date)
        computers = OneToMany('Computer')

    class Computer(flask.ext.restless.Entity):
        name = Field(Unicode, unique=True)
        vendor = Field(Unicode)
        owner = ManyToOne('Person')
        purchase_time = Field(DateTime)

    # Basic Elixir setup is the same.
    metadata.bind = create_engine('sqlite:////tmp/test.db')
    metadata.bind.echo = False
    setup_all()
    create_all()    

    # Create the Flask application and register it with the APIManager.
    app = flask.Flask(__name__)
    manager = flask.ext.restless.APIManager(app)

    # Create API endpoints, which will be available at /api/<modelname> by
    # default. Allowed HTTP methods can be specified as well.
    manager.create_api(Person, methods=['GET', 'PATCH', 'POST', 'DELETE'])
    manager.create_api(Computer, method=['GET'])

Installing Flask-Restless
-------------------------

Install with ``pip`` (hopefully in a virtual environment provided by
``virtualenv``)::

    pip install Flask-Restless

``Flask-Restless`` has the following dependencies (which will be automatically
installed if you use ``pip``):

* `Flask <http://flask.pocoo.org>`_ version 0.7 or greater
* `Elixir <http://elixir.ematia.de>`_
* `SQLAlchemy <http://sqlalchemy.org>`_
* `python-dateutil <http://labix.org/python-dateutil>`_ version less than 2.0

Creating API endpoints
----------------------

To use this extension, you must have defined your database models using
:class:`elixir.Entity` as a base class.

First, change your model classes to inherit from
:class:`flaskext.restless.Entity` instead of :class:`elixir.Entity`::

    #from elixir import Entity
    from flask.ext.restless import Entity
    from elixir import Date, DateTime, Field, Unicode
    from elixir import ManyToOne, OneToMany

    class Person(Entity):
        name = Field(Unicode, unique=True)
        birth_date = Field(Date)
        computers = OneToMany('Computer')

    class Computer(Entity):
        name = Field(Unicode, unique=True)
        vendor = Field(Unicode)
        owner = ManyToOne('Person')
        purchase_time = Field(DateTime)

Second, create your :class:`flask.Flask` object and instantiate a
:class:`flaskext.restless.APIManager` object with that :class:`~flask.Flask`::

    from flask import Flask
    from flask.ext.restless import APIManager

    app = Flask(__name__)
    manager = APIManager(app)

Third, create the API endpoints which will be accessible to web clients::

    manager.create_api(Person, methods=['GET', 'PATCH', 'POST', 'DELETE'])
    manager.create_api(Computer, method=['GET'])

Due to the design of Flask, these APIs must be created before your application
handles any requests.

By default, the API for ``Person``, in the above code samples, will be
accessible at ``http://<host>:<port>/api/Person``::

    >>> import json
    >>> import requests  # python-requests is installable from PyPI...
    >>> newperson = {'name': u'Lincoln', 'age': 23}
    >>> r = requests.post('/api/Person', data=json.dumps(newperson))
    >>> r.status_code, r.headers['content-type'], r.data
    (201, 'application/json', '{"id": 1}')
    >>> newid = json.loads(response.data)['id']
    >>> r = requests.get('/api/Person/{}'.format(newid))
    >>> r.status_code, r.headers['content-type']
    (200, 'application/json')
    >>> r.data
    {
      "other": null,
      "name": "Lincoln",
      "birth_date": null,
      "age": 23.0,
      "computers": [],
      "id": 1
    }

Customizing the ReSTful interface
---------------------------------

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
   see :ref:`search`.

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
