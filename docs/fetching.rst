Fetching resources and relationships
====================================

This section described fetching resources and relationships via
:http:method:`get` requests.

.. toctree::
   :maxdepth: 2

   functionevaluation
   includes
   sparse
   sorting
   pagination
   filtering

Basic fetching
--------------

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
        title = db.Column(db.Unicode)
        author_id = db.Column(db.Integer, db.ForeignKey('person.id'))
        author = db.relationship(Person, backref=db.backref('articles'))

    db.create_all()
    manager = APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person)
    manager.create_api(Article)

By default, all columns and relationships will appear in the resource object
representation of an instance of your model. See :doc:`sparse` for more
information on specifying which values appear in responses.

To fetch a collection of resources, the request

.. sourcecode:: http

   GET /api/person HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "name": "John"
         },
         "id": "1",
         "links": {
           "self": "http://example.com/api/person/1"
         },
         "relationships": {
           "articles": {
             "data": [],
             "links": {
               "related": "http://example.com/api/person/1/articles",
               "self": "http://example.com/api/person/1/relationships/articles"
             }
           }
         },
         "type": "person"
       }
     ],
     "links": {
       "first": "http://example.com/api/person?page[number]=1&page[size]=10",
       "last": "http://example.com/api/person?page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person"
     },
     "meta": {
       "total": 1
     }
   }

To fetch a single resource, the request

.. sourcecode:: http

   GET /api/person/1 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "name": "John"
       },
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/relationships/articles"
           }
         }
       },
       "type": "person"
     }
   }

To fetch a resource from a to-one relationship, the request

.. sourcecode:: http

   GET /api/article/1/author HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "name": "John"
       },
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "relationships": {
         "articles": {
           "data": [
             {
               "id": "1",
               "type": "article"
             }
           ],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/relationships/articles"
           }
         }
       },
       "type": "person"
     }
   }

To fetch a resource from a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "title": "Once upon a time"
         },
         "id": "2",
         "links": {
           "self": "http://example.com/api/articles/2"
         },
         "relationships": {
           "author": {
             "data": {
               "id": "1",
               "type": "person",
             },
             "links": {
               "related": "http://example.com/api/articles/2/author",
               "self": "http://example.com/api/articles/2/relationships/author"
             }
           }
         },
         "type": "article"
       }
     ],
     "links": {
       "first": "http://example.com/api/person/1/articles?page[number]=1&page[size]=10",
       "last": "http://example.com/api/person/1/articles?page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person/1/articles"
     },
     "meta": {
       "total": 1
     }
   }

To fetch a single resource from a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/articles/2 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "title": "Once upon a time"
       },
       "id": "2",
       "links": {
         "self": "http://example.com/api/articles/2"
       },
       "relationships": {
         "author": {
           "data": {
             "id": "1",
             "type": "person"
           },
           "links": {
             "related": "http://example.com/api/articles/2/author",
             "self": "http://example.com/api/articles/2/relationships/author"
           }
         }
       },
       "type": "article"
     }
   }

To fetch the link object for a to-one relationship, the request

.. sourcecode:: http

   GET /api/article/1/relationships/author HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "type": "person"
     }
   }

To fetch the link objects for a to-many relationship, the request

.. sourcecode:: http

   GET /api/person/1/relationships/articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
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
