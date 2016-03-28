Flask-Restless
==============

**Flask-Restless** provides simple generation of ReSTful APIs for database
models defined using SQLAlchemy (or Flask-SQLAlchemy). The generated APIs
satisfy the requirements of the `JSON API`_ specification.

.. warning::

   This is a "beta" version, so there may be more bugs than usual. There are
   two fairly serious known issues with this version.

   First, updating relationships via `association proxies`_ is not working
   correctly. We cannot support many-to-many relationships until this is
   resolved. If you have any insight on how to fix this, please comment on
   GitHub issue #480.

   Second, we would like to make it easy to support serialization via third
   party serialization libraries such as `Marshmallow`_. In order to do this
   correctly, we need to separate serialization and deserialization into two
   parts each: (de)serializing a single resource and (de)serializing many
   resources from a JSON API document. I have not quite finished this yet. You
   can see the `updated Marshmallow example`_ on GitHub, but it will not work
   until the serialization code is updated. If you have any comments, please
   file a new issue on GitHub.

.. _JSON API: http://jsonapi.org
.. _association proxies: https://docs.sqlalchemy.org/en/latest/orm/extensions/associationproxy.html
.. _Marshmallow: https://marshmallow.readthedocs.org/
.. _updated Marshmallow example: https://github.com/jfinkels/flask-restless/compare/marshmallow-example


User's guide
------------

How to use Flask-Restless in your own projects. Much of the documentation in
this chapter assumes some familiarity with the terminology and interfaces of
the JSON API specification.

.. toctree::
   :maxdepth: 2

   installation
   quickstart
   basicusage
   requestformat
   customizing

API reference
-------------

A technical description of the classes, functions, and idioms of
Flask-Restless.

.. toctree::
   :maxdepth: 2

   api

Additional information
----------------------

Meta-information on Flask-Restless.

.. toctree::
   :maxdepth: 2

   similarprojects
   license
   changelog
