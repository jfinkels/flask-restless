Downloading and installing Flask-Restless
=========================================

Flask-Restless can be downloaded from the `Python Package Index`. The
development version can be downloaded from `GitHub`_. However, it is better to
install with ``pip`` (in a virtual environment provided by ``virtualenv``)::

    pip install Flask-Restless

Flask-Restless supports all Python versions that Flask supports, which
currently include versions 2.6, 2.7, 3.3, and 3.4.

Flask-Restless has the following dependencies (which will be automatically
installed if you use ``pip``):

* `Flask <http://flask.pocoo.org>`_ version 0.10 or greater
* `SQLAlchemy <http://sqlalchemy.org>`_ version 0.8 or greater
* `mimerender <http://mimerender.readthedocs.org>`_ version 0.5.2 or greater
* `python-dateutil <http://labix.org/python-dateutil>`_ version strictly
  greater than 2.2
* `Flask-SQLAlchemy <http://packages.python.org/Flask-SQLAlchemy>`_, *only if*
  you want to define your models using Flask-SQLAlchemy (which we recommend)

.. _Python Package Index: https://pypi.python.org/pypi/Flask-Restless
.. _GitHub: https://github.com/jfinkels/flask-restless>
