"""
    Using Flask-Restless with the "requests" library
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This provides an example of using Flask-Restless on the server side to
    provide a ReSTful API and the Python `requests
    <http://docs.python-requests.org/en/latest/>`_ library on the client side
    to make HTTP requests to the server.

    To install the requests library::

        pip install "requests>1.0.3"

    (If you have ``requests`` version less then 1.0.3, just change the code
    below from ``requests.json()`` to ``requests.json``).

    Before executing the code in this module, you must first run the quickstart
    server example from this directory (that is, the ``examples/`` directory)::

        PYTHONPATH=.. python quickstart.py

    Now run this script from this directory to see some example requests using
    the ``requests`` library::

        python requests_client.py

    Remember, the client must specify the ``application/vnd.api+json``
    MIME type when sending requests.

    :copyright: 2013 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import json
import requests

url = 'http://127.0.0.1:5000/api/person'
headers = {'Accept': 'application/vnd.api+json'}
post_headers = {'Accept': 'application/vnd.api+json',
                'Content-Type': 'application/vnd.api+json'}

# Make a POST request to create an object in the database.
person = {
    'data': {
        'type': 'person',
        'attributes': {
            'name': 'Jeffrey',
        }
    }
}
response = requests.post(url, data=json.dumps(person), headers=post_headers)
assert response.status_code == 201

# Make a GET request for the entire collection.
response = requests.get(url, headers=headers)
assert response.status_code == 200
print(response.json())

# Make a GET request for an individual instance of the model.
response = requests.get(url + '/1', headers=headers)
assert response.status_code == 200
print(response.json())

# Use query parameters to make a search. `requests.get` doesn't like
# arbitrary query parameters, so be sure that you pass a dictionary
# whose values are strings to the keyword argument `params`.
filters = [dict(name='name', op='like', val='%y%')]
params = {'filter[objects]': json.dumps(filters)}
response = requests.get(url, params=params, headers=headers)
assert response.status_code == 200
print(response.json())
