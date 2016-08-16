Inclusion of related resources
==============================

*For more information on client-side included resources, see* `Inclusion of
Related Resources`_ *in the JSON API specification.*

By default, no related resources will be included in a compound document on
requests that would return data. For the client to request that the response
includes related resources in a compound document, use the ``include`` query
parameter. For example, to fetch a single resource and include all resources
related to it, the request

.. sourcecode:: http

   GET /api/person/1?include=articles HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "links": {
         "self": "http://example.com/api/person/1"
       },
       "relationships": {
         "articles": {
           "data": [
             {
               "id": "1",
               "type": "article"
             }
           ],
           "links": {
             "related": "http://example.com/api/person/1/articles",
             "self": "http://example.com/api/person/1/relationships/articles"
           }
         }
       },
       "type": "person"
     }
     "included": [
       {
         "id": "1",
         "links": {
           "self": "http://example.com/api/article/1"
         },
         "relationships": {
           "author": {
             "data": {
               "id": "1",
               "type": "person"
             },
             "links": {
               "related": "http://example.com/api/article/1/author",
               "self": "http://example.com/api/article/1/relationships/author"
             }
           }
         },
         "type": "article"
       }
     ]
   }

To specify a default set of related resources to include when the client does
not specify any `include` query parameter, use the ``includes`` keyword
argument to the :meth:`.APIManager.create_api` method.

.. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes
