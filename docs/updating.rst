Updating resources
==================

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

To update an existing resource, the request

.. sourcecode:: http

   PATCH /api/person/1 HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": {
       "type": "person",
       "id": 1,
       "attributes": {
         "name": "foo"
       }
     }
   }

yields a :http:statuscode:`204` response.

If you set the ``allow_to_many_replacement`` keyword argument of
:meth:`.APIManager.create_api` to ``True``, you can replace a to-many
relationship entirely by making a request to update a resource. To update a
to-many relationship, the request

.. sourcecode:: http

   PATCH /api/person/1 HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": {
       "type": "person",
       "id": 1,
       "relationships": {
         "articles": {
           "data": [
             {
               "id": "1",
               "type": "article"
             },
             {
               "id": "2",
               "type": "article"
             }
           ]
         }
       }
     }
   }

yields a :http:statuscode:`204` response.

The server will respond with :http:statuscode:`400` if the request specifies a
field that does not exist on the model.
