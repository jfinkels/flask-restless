.. _basicusage:

.. currentmodule:: flask.ext.restless

Creating API endpoints
======================

To use this extension, you must have defined your database models using either
SQLAlchemy or Flask-SQLALchemy.

The basic setup for Flask-SQLAlchemy is the same. First, create your
:class:`flask.Flask` object, :class:`flask.ext.sqlalchemy.SQLAlchemy` object,
and model classes as usual but with the following two (reasonable) restrictions
on models:

1. They must have an ``id`` column of type :class:`sqlalchemy.Integer`.
2. They must have an ``__init__`` method which accepts keyword arguments for
   all columns (the constructor in
   :class:`flask.ext.sqlalchemy.SQLAlchemy.Model` supplies such a method, so
   you don't need to declare a new one).

.. sourcecode:: python

   import flask
   import flask.ext.sqlalchemy

   app = flask.Flask(__name__)
   app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
   db = flask.ext.sqlalchemy.SQLAlchemy(app)

   class Person(db.Model):
       id = db.Column(db.Integer, primary_key=True)
       name = db.Column(db.Unicode, unique=True)
       birth_date = db.Column(db.Date)
       computers = db.relationship('Computer',
                                   backref=db.backref('owner',
                                                      lazy='dynamic'))


   class Computer(db.Model):
       id = db.Column(db.Integer, primary_key=True)
       name = db.Column(db.Unicode, unique=True)
       vendor = db.Column(db.Unicode)
       owner_id = db.Column(db.Integer, db.ForeignKey('person.id'))
       purchase_time = db.Column(db.DateTime)


   db.create_all()

If you are using pure SQLAlchemy::

   from flask import Flask
   from sqlalchemy import Column, Date, DateTime, Float, Integer, Unicode
   from sqlalchemy import ForeignKey
   from sqlalchemy import create_engine
   from sqlalchemy.ext.declarative import declarative_base
   from sqlalchemy.orm import backref, relationship
   from sqlalchemy.orm import scoped_session, sessionmaker

   app = Flask(__name__)
   engine = create_engine('sqlite:////tmp/testdb.sqlite', convert_unicode=True)
   Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
   mysession = scoped_session(Session)

   Base = declarative_base()
   Base.metadata.bind = engine

   class Computer(Base):
       __tablename__ = 'computer'
       id = Column(Integer, primary_key=True)
       name = Column(Unicode, unique=True)
       vendor = Column(Unicode)
       buy_date = Column(DateTime)
       owner_id = Column(Integer, ForeignKey('person.id'))

   class Person(Base):
       __tablename__ = 'person'
       id = Column(Integer, primary_key=True)
       name = Column(Unicode, unique=True)
       age = Column(Float)
       other = Column(Float)
       birth_date = Column(Date)
       computers = relationship('Computer',
                                backref=backref('owner', lazy='dynamic'))

   Base.metadata.create_all()

.. warning::

   Attributes of these entities must not have a name containing two
   underscores. For example, this class definition is no good::

       class Person(db.Model):
           __mysecretfield = db.Column(db.Unicode)

   This restriction is necessary because the search feature (see
   :ref:`searchformat`) uses double underscores as a separator. This may change
   in future versions.

Second, instantiate a :class:`flask.ext.restless.APIManager` object with the
:class:`~flask.Flask` and :class:`~flask.ext.sqlalchemy.SQLAlchemy` objects::

    from flask.ext.restless import APIManager

    manager = APIManager(app, flask_sqlalchemy_db=db)

Or if you are using pure SQLAlchemy, specify the session you created above
instead::

    manager = APIManager(app, session=mysession)

You may also provide the session class (as returned by
:class:`sqlalchemy.orm.sessionmaker`); in this case Flask-Restless will
instantiate a new :class:`sqlalchemy.orm.scoped_session` from the provided
class::

    manager = APIManager(app, session=Session)

Third, create the API endpoints which will be accessible to web clients::

    person_blueprint = manager.create_api(Person,
                                          methods=['GET', 'POST', 'DELETE'])
    computer_blueprint = manager.create_api(Computer)

Note that you can specify which HTTP methods are available for each API
endpoint. There are several more customization options; for more information,
see :ref:`customizing`.

Due to the design of Flask, these APIs must be created before your application
handles any requests. The return value of :meth:`APIManager.create_api` is the
blueprint in which the endpoints for the specified database model live. The
blueprint has already been registered on the :class:`~flask.Flask` application,
so you do *not* need to register it yourself. It is provided so that you can
examine its attributes, but if you don't need it then just ignore it::

    manager.create_api(Person, methods=['GET', 'POST', 'DELETE'])
    manager.create_api(Computer)

If you wish to create the blueprint for the API without registering it (for
example, if you wish to register it later in your code), use the
:meth:`APIManager.create_api_blueprint` method instead::

    blueprint = manager.create_api_blueprint(Person, methods=['GET', 'POST'])
    # later...
    app.register_blueprint(blueprint)

By default, the API for ``Person``, in the above code samples, will be
accessible at ``http://<host>:<port>/api/person``, where the ``person`` part of
the URL is the value of ``Person.__tablename__``::

    >>> import json  # import simplejson as json, if on Python 2.5
    >>> import requests  # python-requests is installable from PyPI...
    >>> newperson = {'name': u'Lincoln', 'age': 23}
    >>> r = requests.post('/api/person', data=json.dumps(newperson),
    ...                   headers={'content-type': 'application/json'})
    >>> r.status_code, r.headers['content-type'], r.data
    (201, 'application/json', '{"id": 1}')
    >>> newid = json.loads(response.data)['id']
    >>> r = requests.get('/api/person/%s' % newid,
    ...                  headers={'content-type': 'application/json'})
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
