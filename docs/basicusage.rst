Creating API endpoints
======================

To use this extension, you must have defined your database models using either
SQLAlchemy or Flask-SQLALchemy. The basic setup in either case is nearly the
same.

If you have defined your models with Flask-SQLAlchemy, first, create your
:class:`~flask.Flask` object, :class:`~flask_sqlalchemy.SQLAlchemy` object, and
model classes as usual but with one additional restriction: each model must
have a primary key column of type either :class:`~sqlalchemy.types.Integer` or
:class:`~sqlalchemy.types.Unicode`.

.. sourcecode:: python

   from flask import Flask
   from flask_sqlalchemy import SQLAlchemy

   app = Flask(__name__)
   app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
   db = SQLAlchemy(app)


   class Person(db.Model):
       id = db.Column(db.Integer, primary_key=True)


   class Article(db.Model):
       id = db.Column(db.Integer, primary_key=True)
       author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
       author = db.relationship(Person, backref=db.backref('articles'))

   db.create_all()

If you are using pure SQLAlchemy::

   from flask import Flask
   from sqlalchemy import Column, Integer, Unicode
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


   class Person(Base):
       id = Column(Integer, primary_key=True)


   class Article(Base):
       id = Column(Integer, primary_key=True)
       author_id = Column(Integer, ForeignKey('person.id'))
       author = relationship(Person, backref=backref('articles'))

   Base.metadata.create_all()

Second, instantiate an :class:`.APIManager` object with the
:class:`~flask.Flask` and :class:`~flask_sqlalchemy.SQLAlchemy` objects::

    from flask_restless import APIManager

    manager = APIManager(app, flask_sqlalchemy_db=db)

Or if you are using pure SQLAlchemy, specify the session you created above
instead::

    manager = APIManager(app, session=mysession)

Third, create the API endpoints that will be accessible to web clients::

    person_blueprint = manager.create_api(Person, methods=['GET', 'POST'])
    article_blueprint = manager.create_api(Article)

You can specify which HTTP methods are available for each API endpoint. In this
example, the client can fetch and create people, but only fetch articles (the
default if no methods are specified). There are many options for customizing
the endpoints created at this step; for more information, see
:doc:`customizing`.

Due to the design of Flask, these APIs must be created before your application
handles any requests. The return value of :meth:`.APIManager.create_api` is the
blueprint in which the endpoints for the specified database model live. The
blueprint has already been registered on the :class:`~flask.Flask` application,
so you do *not* need to register it yourself. It is provided so that you can
examine its attributes, but if you don't need it then just ignore it::

    methods = ['GET', 'POST']
    manager.create_api(Person, methods=methods)
    manager.create_api(Article)

If you wish to create the blueprint for the API without registering it (for
example, if you wish to register it manually later in your code), use the
:meth:`~.APIManager.create_api_blueprint` method instead. You *must* provide an
additional positional argument, *name*, to this method::

    blueprint = manager.create_api_blueprint('person', Person, methods=methods)
    # later...
    someapp.register_blueprint(blueprint)

By default, the API for ``Person`` in the above code samples will be accessible
at ``<base_url>/api/person``, where the ``person`` part of the URL is the value
of ``Person.__tablename__``::

    >>> import json
    >>> # The python-requests library is installable from PyPI.
    >>> import requests
    >>> # Let's create a new person resource with the following fields.
    >>> newperson = {'type': 'person', 'name': u'Lincoln', 'age': 23}
    >>> # Our requests must have the appropriate JSON API headers.
    >>> headers = {'Content-Type': 'application/vnd.api+json',
    ...            'Accept': 'application/vnd.api+json'}
    >>> # Assume we have a Flask application running on localhost.
    >>> r = requests.post('http://localhost/api/person',
    ...                   data=json.dumps(newperson), headers=headers)
    >>> r.status_code
    201
    >>> document = json.loads(r.data)
    >>> dumps(document, indent=2)
    {
      "data": {
        "id": "1",
        "type": "person",
        "relationships": {
          "articles": {
            "data": [],
            "links": {
              "related": "http://localhost/api/person/1/articles",
              "self": "http://localhost/api/person/1/relationships/articles"
            }
          },
        },
        "links": {
          "self": "http://localhost/api/person/1"
        }
      }
      "meta": {},
      "jsonapi": {
        "version": "1.0"
      }
    }
    >>> newid = document['data']['id']
    >>> r = requests.get('/api/person/{0}'.format(newid), headers=headers)
    >>> r.status_code
    200
    >>> document = loads(r.data)
    >>> dumps(document, indent=2)
    {
      "data": {
        "id": "1",
        "type": "person",
        "relationships": {
          "articles": {
            "data": [],
            "links": {
              "related": "http://localhost/api/person/1/articles",
              "self": "http://localhost/api/person/1/relationships/articles"
            }
          },
        },
        "links": {
          "self": "http://localhost/api/person/1"
        }
      }
      "meta": {},
      "jsonapi": {
        "version": "1.0"
      }
    }

If the primary key is a :class:`~sqlalchemy.types.Unicode` instead of an
:class:`~sqlalchemy.types.Integer`, the instances will be accessible at URL
endpoints like ``http://<host>:<port>/api/person/foo`` instead of
``http://<host>:<port>/api/person/1``.

Deferred API registration
-------------------------

If you only wish to create APIs on a single Flask application and have access
to the Flask application before you create the APIs, you can provide a Flask
application as an argument to the constructor of the :class:`.APIManager`
class, as described above. However, if you wish to create APIs on multiple
Flask applications or if you do not have access to the Flask application at the
time you create the APIs, you can use the :meth:`.APIManager.init_app` method.

If a :class:`.APIManager` object is created without a Flask application, ::

    manager = APIManager(session=session)

then you can create your APIs without registering them on a particular Flask
application::

    manager.create_api(Person)
    manager.create_api(Article)

Later, you can call the :meth:`~.APIManager.init_app` method with any
:class:`~flask.Flask` objects on which you would like the APIs to be
available::

    app1 = Flask('app1')
    app2 = Flask('app2')
    manager.init_app(app1)
    manager.init_app(app2)

The manager creates and stores a blueprint each time
:meth:`~.APIManager.create_api` is invoked, and registers those blueprints each
time :meth:`~.APIManager.init_app` is invoked. (The name of each blueprint will
be a :class:`uuid.UUID`.)

.. versionchanged:: 1.0.0

   The behavior of the :meth:`~.APIManager.init_app` method was strange and
   incorrect before version 1.0.0. It is best not to use earlier versions.
