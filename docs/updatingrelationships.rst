.. _updatingrelationships:

Updating relationships
======================

For the purposes of concreteness in this section, suppose we have executed the
following code on the server::

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_restless import APIManager

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode)

    class Article(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
        author = db.relationship(Person, backref=db.backref('articles'))

    db.create_all()
    manager = APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['PATCH'])
    manager.create_api(Article)

To update a to-one relationship, the request

.. sourcecode:: http

   PATCH /api/articles/1/relationships/author HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": {
       "type": "person",
       "id": 1
     }
   }

yields a :http:statuscode:`204` response.

To update a to-many relationship (if enabled by setting
``allow_to_many_replacement`` to ``True`` in :meth:`.APIManager.create_api`),
the request

.. sourcecode:: http

   PATCH /api/people/1/relationships/articles HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": [
       {
         "type": "article",
         "id": 1
       },
       {
         "type": "article",
         "id": 2
       }
     ]
   }

yields a :http:statuscode:`204` response.

To add to a to-many relationship, the request

.. sourcecode:: http

   POST /api/person/1/relationships/articles HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": [
       {
         "type": "article",
         "id": 1
       },
       {
         "type": "article",
         "id": 2
       }
     ]
   }

yields a :http:statuscode:`204` response.

To remove from a to-many relationship, the request

.. sourcecode:: http

   DELETE /api/person/1/links/articles HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": [
       {
         "type": "article",
         "id": 1
       },
       {
         "type": "article",
         "id": 2
       }
     ]
   }

yields a :http:statuscode:`204` response.

To remove from a to-many relationship (if enabled by setting
``allow_delete_from_to_many_relationships`` to ``True`` in
:meth:`.APIManager.create_api`), the request

.. sourcecode:: http

   DELETE /api/person/1/relationships/articles HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": [
       {
         "type": "article",
         "id": 1
       },
       {
         "type": "article",
         "id": 2
       }
     ]
   }

yields a :http:statuscode:`204` response.
