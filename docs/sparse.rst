Specifying which fields appear in responses
===========================================

*For more information on client-side sparse fieldsets, see* `Sparse Fieldsets`_
*in the JSON API specification.*

.. warning::

   The server-side configuration for specifying which fields appear in resource
   objects as described in this section is simplistic; a better way to specify
   which fields are included in your responses is to use a Python object
   serialization library and specify custom serialization and deserialization
   functions as described in :doc:`serialization`.

By default, all fields of your model will be exposed by the API. A client can
request that only certain fields appear in the resource object in a response to
a :http:method:`get` request by using the ``only`` query parameter. On the
server side, you can specify which fields appear in the resource object
representation of an instance of the model by setting the ``only``, ``exclude``
and ``additional_attributes`` keyword arguments to the
:meth:`.APIManager.create_api` method.

If ``only`` is an iterable of column names or actual column attributes, only
those fields will appear in the resource object that appears in responses to
fetch instances of this model. If instead ``exclude`` is specified, all fields
except those specified in that iterable will appear in responses. If
``additional_attributes`` is an iterable of column names, the values of these
attributes will also appear in the response; this is useful if you wish to see
the value of some attribute that is not a column or relationship.

.. attention::

   The ``type`` and ``id`` elements will always appear in the resource object,
   regardless of whether the server or the client tries to exclude them.

For example, if your models are defined like this (using Flask-SQLAlchemy)::

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode)
        birthday = db.Column(db.Date)
        articles = db.relationship('Article')

        # This class attribute is not a column.
        foo = 'bar'

    class Article(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        author_id = db.Column(db.Integer, db.ForeignKey('person.id'))

and you want your resource objects to include only the values of the ``name``
and ``birthday`` columns, create your API with the following arguments::

    apimanager.create_api(Person, only=['name', 'birthday'])

Now a request like

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
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "attributes": {
         "birthday": "1969-07-20",
         "name": "foo"
       },
       "type": "person"
     }
   }

If you want your resource objects to *exclude* the ``birthday`` and ``name``
columns::

    apimanager.create_api(Person, exclude=['name', 'birthday'])

Now the same request yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       }
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/links/articles"
           }
         },
       },
       "type": "person"
     }
   }

If you want your resource objects to include the value for the class attribute
``foo``::

    apimanager.create_api(Person, additional_attributes=['foo'])

Now the same request yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "birthday": "1969-07-20",
         "foo": "bar",
         "name": "foo"
       },
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       }
       "relationships": {
         "articles": {
           "data": [],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/links/articles"
           }
         }
       },
       "type": "person"
     }
   }

.. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets
