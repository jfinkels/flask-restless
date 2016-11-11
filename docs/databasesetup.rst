Common SQLAlchemy setups
========================

Flask-Restless automatically handles SQLAlchemy models defined with
`association proxies`_ and `polymorphism`_.

.. _association proxies: http://docs.sqlalchemy.org/en/latest/orm/extensions/associationproxy.html
.. _polymorphism: http://docs.sqlalchemy.org/en/latest/orm/inheritance.html


Association proxies
-------------------

Flask-Restless handles many-to-many relationships transparently through
association proxies. It exposes the remote table in the ``relationships``
element of a resource in the JSON document and hides the association table or
association object.


Proxying association objects
............................

TODO Add link to the correct section of the SQLAlchemy documentation here.

When proxying a to-many relationship via an association object, the related
resources will appear in the ``relationships`` element of the resource object
but the association object will not appear. For example, in the following
setup, each article has a to-many relationship to tags via the ``ArticleTag``
object::

    from sqlalchemy import Column, Integer, Unicode, ForeignKey
    from sqlalchemy.ext.associationproxy import association_proxy
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship

    Base = declarative_base()

    class Article(Base):
        __tablename__ = 'article'
        id = Column(Integer, primary_key=True)
        articletags = relationship('ArticleTag',
                                   cascade='all, delete-orphan')
        tags = association_proxy('articletags', 'tag',
                                 creator=lambda tag: ArticleTag(tag=tag))

    class ArticleTag(Base):
        __tablename__ = 'articletag'
        article_id = Column(Integer, ForeignKey('article.id'),
                            primary_key=True)
        tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
        tag = relationship('Tag')

    class Tag(Base):
        __tablename__ = 'tag'
        id = Column(Integer, primary_key=True)
        name = Column(Unicode)

Resource objects of type ``'article'`` will have a ``tags`` relationship that
proxies directly to the ``Tag`` resource through the ``ArticleTag`` table. The
intermediate ``articletags`` relationship does not appear as a relationship in
the resource object:

.. sourcecode:: json

   {
     "data": {
       "id": "1",
       "type": "article",
       "relationships": {
         "tags": {
           "data": [
             {
               "id": "1",
               "type": "tag"
             },
             {
               "id": "2",
               "type": "tag"
             }
           ],
         }
       }
     }
   }


Proxying association tables
...........................

TODO Add link to the correct section of the SQLAlchemy documentation here.

When proxying an attribute of a to-many relationship via an association table,
the attribute will appear in the ``attributes`` element of the resource object
and the to-many relationship will appear in the ``relationships`` element of
the resource object but the association table will not appear. For example, in
the following setup, each article has an association proxy ``tag_names`` which
is a list of the ``name`` attribute of each related tag::

    from sqlalchemy import Column, Integer, Unicode, ForeignKey
    from sqlalchemy.ext.associationproxy import association_proxy
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship

    Base = declarative_base()

    class Article(Base):
        __tablename__ = 'article'
        id = Column(Integer, primary_key=True)
        tags = relationship('Tag', secondary=lambda: articletags_table)
        tag_names = association_proxy('tags', 'name',
                                      creator=lambda s: Tag(name=s))

    class Tag(Base):
        __tablename__ = 'tag'
        id = Column(Integer, primary_key=True)
        name = Column(Unicode)

    articletags_table = \
        Table('articletags', Base.metadata,
              Column('article_id', Integer, ForeignKey('article.id'),
                     primary_key=True),
              Column('tag_id', Integer, ForeignKey('tag.id'),
                     primary_key=True))

Resource objects of type ``'article'`` will have a ``tag_names`` attribute that
is a list of tag names in addition to a ``tags`` relationship. The intermediate
``articletags`` table does not appear as a relationship in the resource object:

.. sourcecode:: json

   {
     "data": {
       "id": "1",
       "type": "article",
       "attributes": {
         "tag_names": [
           "foo",
           "bar"
         ]
       },
       "relationships": {
         "tags": {
           "data": [
             {
               "id": "1",
               "type": "tag"
             },
             {
               "id": "2",
               "type": "tag"
             }
           ],
         }
       }
     }
   }


Polymorphic models
------------------

Flask-Restless automatically handles polymorphic models defined using either
single table or joined table inheritance. We have made some design choices we
believe are reasonable. Requests to create, update, or delete a resource must
specify a ``type`` that matches the collection name of the endpoint. This means
you cannot request to create a resource of the subclass type at the endpoint
for the superclass type, for example. On the other hand, requests to fetch a
collection of objects that have a subclass will yield a response that includes
all resources of the superclass and all resources of any subclass.

For example, consider a setup where there are employees and some employees are
managers::

    from sqlalchemy import Column, Integer, Enum
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()

    class Employee(Base):
        __tablename__ = 'employee'
        id = Column(Integer, primary_key=True)
        type = Column(Enum('employee', 'manager'), nullable=False)
        __mapper_args__ = {
            'polymorphic_on': type,
            'polymorphic_identity': 'employee'
        }

    class Manager(Employee):
        __mapper_args__ = {
            'polymorphic_identity': 'manager'
        }

Collection name
...............

When creating an API for these models, Flask-Restless chooses the polymorphic
identity as the collection name::

    >>> from flask.ext.restless import collection_name
    >>>
    >>> manager.create_api(Employee)
    >>> manager.create_api(Manager)
    >>> collection_name(Employee)
    'employee'
    >>> collection_name(Manager)
    'manager'

Creating and updating resources
...............................

Creating a resource require the ``type`` element of the resource object in the
request to match the collection name of the endpoint::

    >>> from flask import json
    >>> import requests
    >>>
    >>> headers = {
    ...     'Accept': 'application/vnd.api+json',
    ...     'Content-Type': 'application/vnd.api+json'
    ... }
    >>> resource = {'data': {'type': 'employee'}}
    >>> data = json.dumps(resource)
    >>> response = requests.post('https://example.com/api/employee', data=data,
    ...                           headers=headers)
    >>> response.status_code
    201
    >>> resource = {'data': {'type': 'manager'}}
    >>> data = json.dumps(resource)
    >>> response = requests.post('https://example.com/api/manager', data=data,
    ...                           headers=headers)
    >>> response.status_code
    201

If the ``type`` does not match the collection name for the endpoint, the server
responds with a :http:statuscode:`409`::

    >>> resource = {'data': {'type': 'manager'}}
    >>> data = json.dumps(resource)
    >>> response = requests.post('https://example.com/api/employee', data=data,
    ...                           headers=headers)
    >>> response.status_code
    409

The same rules apply for updating resources.

Fetching resources
..................

Assume the database contains an employee with ID 1 and a manager with ID 2.
You can only fetch each individual resource at the endpoint for the exact type
of that resource::

    >>> response = requests.get('https://example.com/api/employee/1')
    >>> response.status_code
    200
    >>> response = requests.get('https://example.com/api/manager/2')
    >>> response.status_code
    200

You cannot access individual resources of the subclass at the endpoint for the
superclass::

    >>> response = requests.get('https://example.com/api/employee/2')
    >>> response.status_code
    404
    >>> response = requests.get('https://example.com/api/manager/1')
    >>> response.status_code
    404

Fetching from the superclass endpoint yields a response that includes resources
of the superclass and resources of the subclass::

    >>> response = requests.get('https://example.com/api/employee')
    >>> document = json.loads(response.data)
    >>> resources = document['data']
    >>> employee, manager = resources
    >>> employee['type']
    'employee'
    >>> employee['id']
    '1'
    >>> manager['type']
    'manager'
    >>> manager['id']
    '2'

Deleting resources
..................

Assume the database contains an employee with ID 1 and a manager with ID 2.
You can only delete from the endpoint that matches the exact type of the
resource::

    >>> response = requests.delete('https://example.com/api/employee/2')
    >>> response.status_code
    404
    >>> response = requests.delete('https://example.com/api/manager/1')
    >>> response.status_code
    404
    >>> response = requests.delete('https://example.com/api/employee/1')
    >>> response.status_code
    204
    >>> response = requests.delete('https://example.com/api/manager/2')
    >>> response.status_code
    204
