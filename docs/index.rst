Flask-Restless
==============

**Flask-Restless** provides simple generation of ReSTful APIs for database
models defined using SQLAlchemy (or Flask-SQLAlchemy). The generated APIs
satisfy the requirements of the `JSON API`_ specification.

.. warning::

   This is a "beta" version, so there may be more bugs than usual. There is one
   serious known issue with this version: updating relationships via
   `association proxies`_ is not working correctly. If you have any insight on
   how to fix this, please file a new issue at the `GitHub issue tracker`_.

.. _JSON API: http://jsonapi.org
.. _association proxies: https://docs.sqlalchemy.org/en/latest/orm/extensions/associationproxy.html
.. _GitHub issue tracker: https://github.com/jfinkels/flask-restless/issues


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
