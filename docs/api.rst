API
===

.. module:: flask.ext.restless

This part of the documentation documents all the public classes and functions
in Flask-Restless.

.. autoclass:: APIManager

   .. automethod:: init_app

   .. automethod:: create_api

   .. automethod:: create_api_blueprint

.. autofunction:: url_for(model, instid=None, relationname=None, relationinstid=None, _apimanager=None, **kw)

.. autoclass:: ProcessingException
