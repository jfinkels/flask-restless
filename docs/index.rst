Flask-Restless
==============

**Flask-Restless** provides simple generation of ReSTful APIs for database
models given as Elixir entities.

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
