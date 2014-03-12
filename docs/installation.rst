Downloading and installing Flask-Restless
=========================================

Flask-Restless can be downloaded from `its page on the Python Package Index
<http://pypi.python.org/pypi/Flask-Restless>`_. The development version can be
downloaded from `its page at GitHub
<http://github.com/jfinkels/flask-restless>`_. However, it is better to install
with ``pip`` (hopefully in a virtual environment provided by ``virtualenv``)::

    pip install Flask-Restless

Flask-Restless requires Python version 2.6, 2.7, or 3.3. Python 3.2 is not
supported by Flask and therefore cannot be supported by Flask-Restless.

Flask-Restless has the following dependencies (which will be automatically
installed if you use ``pip``):

* `Flask <http://flask.pocoo.org>`_ version 0.10 or greater
* `SQLAlchemy <http://sqlalchemy.org>`_ version 0.8 or greater
* `python-dateutil <http://labix.org/python-dateutil>`_ version strictly
  greater than 2.0
* `Flask-SQLAlchemy <http://packages.python.org/Flask-SQLAlchemy>`_, *only if*
  you want to define your models using Flask-SQLAlchemy (which we highly
  recommend)
