#!/bin/bash
#
#    curl example
#    ~~~~~~~~~~~~
#
#    This provides an example of using Flask-Restless on the server-side to
#    provide a ReSTful API and `curl <http://curl.haxx.se/>`_ on the client
#    side to make HTTP requests to the server.
#
#    In order to use this script, you must first run the quickstart server
#    example from this directory::
#
#        PYTHONPATH=.. python quickstart.py
#
#    Now run this script from this directory (that is, the ``examples/``
#    directory) to see some example requests made from curl::
#
#        ./curl.sh
#
#    The important thing to note in this example is that the client must
#    remember to specify the ``application/json`` MIME type when sending
#    requests.
#
#    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
#    :license: GNU AGPLv3+ or BSD

# We expect the server to be running at 127.0.0.1:5000, the Flask default.
HOST=127.0.0.1:5000

# The JSON API mimetype must be used for Accept and Content-Type headers.
MIMETYPE="application/vnd.api+json"

echo
echo "Making an initial GET request..."
echo
# curl makes GET requests by default.
#
# The Accept header is not required by the JSON API, but is good practice.
curl -H "Accept: $MIMETYPE" http://$HOST/api/person

echo
echo
echo "Making a POST request..."
echo
curl -H "Accept: $MIMETYPE" -H "Content-Type: $MIMETYPE" \
     -d '{"data": {"type": "person", "attributes": {"name": "Jeffrey",
         "birth_date": "3-12-1999"}}}' \
     http://$HOST/api/person

echo
echo
echo "Making a GET request for the entire collection..."
echo
curl -H "Accept: $MIMETYPE" http://$HOST/api/person

echo
echo
echo "Making a GET request for the added person..."
echo
curl -H "Accept: $MIMETYPE" http://$HOST/api/person/1
echo

echo
echo
echo "Searching for all people whose names contain a 'y'..."
echo
# Note: things like brackets (and spaces) should be URL encoded when making
# these requests.
curl -H "Accept: $MIMETYPE" \
     "http://$HOST/api/person?filter\[objects\]=\[\{\"name\":\"name\",\"op\":\"like\",\"val\":\"%y%\"\}\]"
echo
