.. _basicusage:

.. currentmodule:: flask.ext.restless

Creating API endpoints
======================

To use this extension, you must have defined your database models using
SQLALchemy.

The basic setup for SQLAlchemy is the same. First, create your model classes as
usual but with the following two (reasonable) restrictions:

1. They must have an ``id`` column of type :class:`sqlalchemy.Integer`.
2. They must have an ``__init__`` method which accepts keyword arguments for
   all columns (the constructor in ``Base`` below supplies such a method, so
   you don't need to declare a new one).

Next, create an engine, create the database tables, and create a ``Session`` class::

    from sqlalchemy import create_engine
    from sqlalchemy import Column, ForeignKey
    from sqlalchemy import Date, DateTime, Integer, Unicode
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship, backref
    from sqlalchemy.orm import sessionmaker

    Base = declarative_base()


    class Person(Base):
        __tablename__ = 'person'
        id = Column(Integer, primary_key=True)
        name = Column(Unicode, unique=True)
        birth_date = Column(Date)
        computers = relationship('Computer', backref=backref('owner',
                                                             lazy='dynamic'))


    class Computer(Base):
        __tablename__ = 'computer'
        id = Column(Integer, primary_key=True)
        name = Column(Unicode, unique=True)
        vendor = Column(Unicode)
        owner_id = Column(Integer, ForeignKey('person.id'))
        purchase_time = Column(DateTime)


    engine = create_engine('sqlite:////tmp/mydatabase.db')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

.. warning::

   Attributes of these entities must not have a name containing two
   underscores. For example, this class definition is no good::

       class Person(Base):
           __mysecretfield = Column(Unicode)

   This restriction is necessary because the search feature (see
   :ref:`searchformat`) uses double underscores as a separator. This may change
   in future versions.

Second, create your :class:`flask.Flask` object and instantiate a
:class:`flask.ext.restless.APIManager` object with that :class:`~flask.Flask`::

    from flask import Flask
    from flask.ext.restless import APIManager

    app = Flask(__name__)
    manager = APIManager(app)

Third, create the API endpoints which will be accessible to web clients::

    person_blueprint = manager.create_api(Session(), Person,
                                          methods=['GET', 'POST', 'DELETE'])
    computer_blueprint = manager.create_api(Session(), Computer)

Each call to :meth:`APIManager.create_api` currently requires you to provide a
``Session``; although we have used two different ones below, you may use the
same one for all APIs. Also, note that you can specify which HTTP methods are
available for each API endpoint. For more information, see :ref:`customizing`.

Due to the design of Flask, these APIs must be created before your application
handles any requests. The return value of :meth:`APIManager.create_api` is the
blueprint in which the endpoints for the specified database model live. The
blueprint has already been registered on the :class:`~flask.Flask` application,
so you do *not* need to register it yourself. It is provided so that you can
examine its attributes, but if you don't need it then just ignore it::

    manager.create_api(Session(), Person, methods=['GET', 'POST', 'DELETE'])
    manager.create_api(Session(), Computer, methods=['GET'])

By default, the API for ``Person``, in the above code samples, will be
accessible at ``http://<host>:<port>/api/person``, where the ``person`` part of
the URL is the value of ``Person.__tablename__``::

    >>> import json
    >>> import requests  # python-requests is installable from PyPI...
    >>> newperson = {'name': u'Lincoln', 'age': 23}
    >>> r = requests.post('/api/person', data=json.dumps(newperson))
    >>> r.status_code, r.headers['content-type'], r.data
    (201, 'application/json', '{"id": 1}')
    >>> newid = json.loads(response.data)['id']
    >>> r = requests.get('/api/person/{}'.format(newid))
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
