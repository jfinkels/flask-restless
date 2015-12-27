from flask import json
from flask import request
from sqlalchemy.exc import OperationalError

from .base import error_response
from .base import ModelView
from .helpers import evaluate_functions


class FunctionAPI(ModelView):
    """Provides method-based dispatching for :http:method:`get` requests which
    wish to apply SQL functions to all instances of a model.

    .. versionadded:: 0.4

    """

    def get(self):
        """Returns the result of evaluating the SQL functions specified in the
        body of the request.

        For a description of the request and response formats, see
        :ref:`functionevaluation`.

        """
        if 'functions' not in request.args:
            detail = 'Must provide `functions` query parameter'
            return error_response(400, detail=detail)
        functions = request.args.get('functions')
        try:
            data = json.loads(str(functions)) or []
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode JSON in `functions` query parameter'
            return error_response(400, cause=exception, detail=detail)
        try:
            result = evaluate_functions(self.session, self.model, data)
        except AttributeError as exception:
            detail = 'No such field "{0}"'.format(exception.field)
            return error_response(400, cause=exception, detail=detail)
        except KeyError as exception:
            detail = str(exception)
            return error_response(400, cause=exception, detail=detail)
        except OperationalError as exception:
            detail = 'No such function "{0}"'.format(exception.function)
            return error_response(400, cause=exception, detail=detail)
        return dict(data=result)
