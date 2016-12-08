Pagination
==========

Pagination works as described in the JSON API specification, via the
``page[number]`` and ``page[size]`` query parameters. Pagination respects
sorting, grouping, and filtering. The first page is page one. If no page number
is specified by the client, the first page will be returned. By default,
pagination is enabled and the page size is ten. If the page size specified by
the client is greater than the maximum page size as configured on the server,
then the query parameter will be ignored.

To set the default page size for collections of resources, use the
``page_size`` keyword argument to the :meth:`.APIManager.create_api` method.
To set the maximum page size that the client can request, use the
``max_page_size`` argument. Even if ``page_size`` is greater than
``max_page_size``, at most ``max_page_size`` resources will be returned in a
page. If ``max_page_size`` is set to ``0``, the
client will be able to specify arbitrarily large page sizes. If, further,
``page_size`` is set to ``0``, pagination will be
disabled by default, and any :http:method:`get` request that does not specify a
page size in its query parameters will get a response with all matching
results.

.. attention::

   Disabling pagination can result in arbitrarily large responses!

For example, to set each page to include only two results::

    apimanager.create_api(Person, page_size=2)

Then a :http:method:`get` request to ``/api/person?page[number]=2`` would yield
the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": [
       {
         "id": "3",
         "type": "person",
         "attributes": {
           "name": "John"
         }
       }
       {
         "id": "4",
         "type": "person",
         "attributes": {
           "name": "Paul"
         }
       }
     ],
     "links": {
       "first": "http://example.com/api/person?page[number]=1&page[size]=2",
       "last": "http://example.com/api/person?page[number]=3&page[size]=2",
       "next": "http://example.com/api/person?page[number]=3&page[size]=2",
       "prev": "http://example.com/api/person?page[number]=1&page[size]=2",
       "self": "http://example.com/api/person"
     },
     "meta": {
       "total": 6
     }
   }
