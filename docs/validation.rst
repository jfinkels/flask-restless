Validation
==========

Flask-Restless does not do any validation. It simply passes requests on to the
database directly. If you want database-level validation, you must implement it
in your own classes. However, Flask-Restless will capture exceptions and return
them as error responses with an error message in JSON as the body of the
response.

For example...
