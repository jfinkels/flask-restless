"""
    flask.ext.restless.helpers
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Helper functions for Flask-Restless.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""


def partition(l, condition):
    """Returns a pair of lists, the left one containing all elements of `l` for
    which `condition` is ``True`` and the right one containing all elements of
    `l` for which `condition` is ``False``.

    `condition` is a function that takes a single argument (each individual
    element of the list `l`) and returns either ``True`` or ``False``.

    """
    return filter(condition, l), filter(lambda x: not condition(x), l)


def unicode_keys_to_strings(dictionary):
    """Returns a new dictionary with the same mappings as `dictionary`, but
    with each of the keys coerced to a string (by calling :func:`str(key)`).

    This function is intended to be used for Python 2.5 compatibility when
    unpacking a dictionary to provide keyword arguments to a function or
    method. For example::

        >>> def func(a=1, b=2):
        ...     return a + b
        ...
        >>> d = {u'a': 10, u'b': 20}
        >>> func(**d)
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
        TypeError: func() keywords must be strings
        >>> func(**unicode_keys_to_strings(d))
        30

    """
    return dict((str(k), v) for k, v in dictionary.iteritems())
