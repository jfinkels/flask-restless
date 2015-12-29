.. currentmodule:: flask.ext.restless

.. _basicusage:

Creating API endpoints
======================

To use this extension, you must have defined your database models using either
SQLAlchemy or Flask-SQLALchemy. The basic setup in either case is nearly the
same.

If you have defined your models with Flask-SQLAlchemy, first, create your
:class:`~flask.Flask` object, :class:`~flask.ext.sqlalchemy.SQLAlchemy` object,
and model classes as usual but with one additional restriction: each model must
have a primary key column named ``id`` of type :class:`sqlalchemy.Integer` or
type :class:`sqlalchemy.Unicode`.

.. sourcecode:: python

   from flask import Flask
   from flask.ext.sqlalchemy import SQLAlchemy

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

Second, instantiate an :class:`APIManager` object with the
:class:`~flask.Flask` and :class:`~flask.ext.sqlalchemy.SQLAlchemy` objects::

    from flask.ext.restless import APIManager

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
:ref:`customizing`.

Due to the design of Flask, these APIs must be created before your application
handles any requests. The return value of :meth:`APIManager.create_api` is the
blueprint in which the endpoints for the specified database model live. The
blueprint has already been registered on the :class:`~flask.Flask` application,
so you do *not* need to register it yourself. It is provided so that you can
examine its attributes, but if you don't need it then just ignore it::

    manager.create_api(Person, methods=['GET', 'POST'])
    manager.create_api(Article)

If you wish to create the blueprint for the API without registering it (for
example, if you wish to register it later in your code), use the
:meth:`APIManager.create_api_blueprint` method instead::

    blueprint = manager.create_api_blueprint(Person, methods=['GET', 'POST'])
    # later...
    app.register_blueprint(blueprint)

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

If the primary key is a :class:`~sqlalchemy.Unicode` instead of an
:class:`~sqlalchemy.Integer`, the instances will be accessible at URL endpoints
like ``http://<host>:<port>/api/person/foo`` instead of
``http://<host>:<port>/api/person/1``.

Initializing the Flask application after creating the API manager
-----------------------------------------------------------------

Instead of providing the Flask application at instantiation time, you can
initialize the Flask application after instantiating the :class:`APIManager`
object by using the :meth:`APIManager.init_app` method. If you do this, you
will need to provide the Flask application object using the ``app`` keyword
argument to the :meth:`APIManager.create_api` method::

    from flask import Flask
    from flask.ext.restless import APIManager
    from flask.ext.sqlalchemy import SQLAlchemy

    app = Flask(__name__)
    db = SQLAlchemy(app)
    manager = APIManager(flask_sqlalchemy_db=db)

    # later...

    manager.init_app(app)
    manager.create_api(Person, app=app)

You can also use this approach to initialize multiple Flask applications with a
single instance of :class:`APIManager`. For example::

    from flask import Flask
    from flask.ext.restless import APIManager
    from flask.ext.sqlalchemy import SQLAlchemy

    # Create two Flask applications, both backed by the same database.
    app1 = Flask(__name__)
    app2 = Flask(__name__ + '2')
    app1.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    app2.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app1)

    # Create the Flask-SQLAlchemy models.
    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)


   class Article(db.Model):
       id = db.Column(db.Integer, primary_key=True)
       author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
       author = db.relationship(Person, backref=db.backref('articles'))

    # Create the database tables.
    db.create_all()

    # Create the APIManager and initialize it with the different Flask objects.
    manager = APIManager(flask_sqlalchemy_db=db)
    manager.init_app(app1)
    manager.init_app(app2)

    # When creating each API, you need to specify which Flask application
    # should be handling these requests.
    manager.create_api(Person, app=app1)
    manager.create_api(Article, app=app2)

Finally, you can also create an API *before* initializing the Flask
application. For example::

    manager = APIManager()
    manager.create_api(Person)
    manager.init_app(app, session=session)

.. versionchanged:: 0.16.0
   The :meth:`APIManager.init_app` method behaved incorrectly before version
   0.16.0. From that version on, you must provide the Flask application when
   you call :meth:`APIManager.create_api` after having performed the delayed
   initialization described in this section.
