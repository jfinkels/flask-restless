.. _basicusage:

Creating API endpoints
======================

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

.. warning::

   Attributes of these entities must not have a name containing two
   underscores. For example, this class definition is no good::

       class Person(Entity):
           __mysecretfield = Field(Unicode)

   This restriction is necessary because the search feature (see
   :ref:`searchformat`) uses double underscores as a separator. This may change
   in the future.

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
