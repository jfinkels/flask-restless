Sorting
=======

Clients can sort according to the sorting protocol described in the `Sorting
<http://jsonapi.org/format/#fetching-sorting>`__ section of the JSON API
specification. Sorting by a nullable attribute will cause resources with null
attributes to appear first. The client can request case-insensitive sorting by
setting the query parameter ``ignorecase=1``.

Clients can also request grouping by using the ``group`` query parameter. For
example, if your database has two people with name ``'foo'`` and two people
with name ``'bar'``, a request like

.. sourcecode:: http

   GET /api/person?group=name HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "attributes": {
           "name": "foo",
         },
         "id": "1",
         "links": {
           "self": "http://example.com/api/person/1"
         },
         "relationships": {
           "articles": {
             "data": [],
             "links": {
               "related": "http://example.com/api/person/1/articles",
               "self": "http://example.com/api/person/1/relationships/articles"
             }
           }
         },
         "type": "person"
       },
       {
         "attributes": {
           "name": "bar",
         },
         "id": "3",
         "links": {
           "self": "http://example.com/api/person/3"
         },
         "relationships": {
           "articles": {
             "data": [],
             "links": {
               "related": "http://example.com/api/person/3/articles",
               "self": "http://example.com/api/person/3/relationships/articles"
             }
           }
         },
         "type": "person"
       },
     ],
     "links": {
       "first": "http://example.com/api/person?group=name&page[number]=1&page[size]=10",
       "last": "http://example.com/api/person?group=name&page[number]=1&page[size]=10",
       "next": null,
       "prev": null,
       "self": "http://example.com/api/person?group=name"
     },
     "meta": {
       "total": 2
     }
   }
