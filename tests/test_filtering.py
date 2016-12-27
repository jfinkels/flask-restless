# test_filtering.py - unit tests for filtering resources in client requests
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Unit tests for filtering resources in client requests."""
from datetime import date
from datetime import datetime
from datetime import time
from operator import gt
# In Python 3...
try:
    from urllib.parse import unquote
# In Python 2...
except ImportError:
    from urlparse import unquote
from unittest2 import skip

from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import select
from sqlalchemy import Time
from sqlalchemy import Unicode
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask_restless import register_operator

from .helpers import check_sole_error
from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


class SearchTestBase(ManagerTestBase):
    """Provides a search method that simplifies a fetch request with filtering
    query parameters.

    """

    def search(self, url, filters=None, single=None):
        """Convenience function for performing a filtered :http:method:`get`
        request.

        `url` is the ``path`` part of the URL to which the request will be
        sent.

        If `filters` is specified, it must be a Python list containing filter
        objects. It specifies how to set the ``filter[objects]`` query
        parameter.

        If `single` is specified, it must be a Boolean. It specifies how to set
        the ``filter[single]`` query parameter.

        """
        if filters is None:
            filters = []
        # The value provided to the `separators` keyword argument
        # minimizes whitespace.
        filters_str = dumps(filters, separators=(',', ':'))
        params = {'filter[objects]': filters_str}
        if single is not None:
            params['filter[single]'] = 1 if single else 0
        return self.app.get(url, query_string=params)


class TestFiltering(SearchTestBase):
    """Tests for filtering resources.

    For more information, see the `Filtering`_ section of the JSON API
    specification.

    .. _Filtering: http://jsonapi.org/format/#fetching-filtering

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application,
        and creates the ReSTful API endpoints for the models used in the test
        methods.

        """
        super(TestFiltering, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            publishtime = Column(DateTime)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles'))

            @hybrid_property
            def has_comments(self):
                return len(self.comments) > 0

            @has_comments.expression
            def has_comments(cls):
                return select([func.count(self.Comment.id)]).\
                    where(self.Comment.article_id == cls.id).\
                    label('num_comments') > 0

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            birthday = Column(Date)
            birth_datetime = Column(DateTime)
            bedtime = Column(Time)

            @hybrid_property
            def is_minor(self):
                if not hasattr(self, 'age') or self.age is None:
                    return False
                return self.age <= 18

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            content = Column(Unicode)
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship(Person, backref=backref('comments'))

        self.Article = Article
        self.Person = Person
        self.Comment = Comment
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        self.manager.create_api(Comment)

    def test_bad_filter(self):
        """Tests that providing a bad filter parameter causes an error
        response.

        """
        query_string = {'filter[objects]': 'bogus'}
        response = self.app.get('/api/person', query_string=query_string)
        assert response.status_code == 400
        # TODO check error messages here

    def test_bad_filter_relation(self):
        """Tests for providing a bad filter parameter for fetching a
        relation.

        """
        query_string = {'filter[objects]': 'bogus'}
        response = self.app.get('/api/person/1/articles',
                                query_string=query_string)
        check_sole_error(response, 400, ['Unable to decode', 'filter object'])

    def test_bad_filter_relationship(self):
        """Test for providing a bad filter parameter for fetching
        relationship objects.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        query_string = {'filter[objects]': 'bogus'}
        response = self.app.get('/api/person/1/relationships/articles',
                                query_string=query_string)
        assert response.status_code == 400
        # TODO check error messages here

    def test_like(self):
        """Tests for filtering using the ``like`` operator."""
        person1 = self.Person(name=u'Jesus')
        person2 = self.Person(name=u'Mary')
        person3 = self.Person(name=u'Joseph')
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='name', op='like', val='%s%')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert len(people) == 2
        assert ['Jesus', 'Joseph'] == sorted(person['attributes']['name']
                                             for person in people)

    def test_single(self):
        """Tests for requiring a single resource response to a filtered
        request.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='id', op='equals', val='1')]
        response = self.search('/api/person', filters, single=True)
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '1'

    def test_single_relationship(self):
        """Tests for requiring a single relationship object in a
        response to a filtered request.

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        filters = [dict(name='id', op='equals', val='1')]
        response = self.search('/api/person/1/relationships/articles', filters,
                               single=True)
        assert response.status_code == 200
        document = loads(response.data)
        article = document['data']
        # Check that this is just a resource identifier object and not a
        # full resource object representing the Article.
        assert ['id', 'type'] == sorted(article)
        assert article['type'] == 'article'
        assert article['id'] == '1'

    def test_single_too_many(self):
        """Tests that requiring a single resource response returns an error if
        the filtered request would have returned more than one resource.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        response = self.search('/api/person', single=True)
        # TODO should this be a 404? Maybe 409 is better?
        assert response.status_code == 404
        # TODO check the error message here.

    def test_single_too_few(self):
        """Tests that requiring a single resource response yields an error
        response if the filtered request would have returned zero resources.

        """
        response = self.search('/api/person', single=True)
        # TODO should this be a 404? Maybe 409 is better?
        assert response.status_code == 404
        # TODO check the error message here.

    def test_single_wrong_format(self):
        """Tests that providing an incorrectly formatted argument to
        ``filter[single]`` yields an error response.

        """
        params = {'filter[single]': 'bogus'}
        response = self.app.get('/api/person', query_string=params)
        assert response.status_code == 400
        # TODO check the error message here.

    def test_relation_single_wrong_format(self):
        """Tests that providing an incorrectly formatted argument to
        ``filter[single]`` yields an error response when fetching a
        relation.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        params = {'filter[single]': 'bogus'}
        response = self.app.get('/api/person/1/articles', query_string=params)
        assert response.status_code == 400
        # TODO check the error message here.

    def test_relationship_single_wrong_format(self):
        """Tests that providing an incorrectly formatted argument to
        ``filter[single]`` yields an error response when fetching
        relationship.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        query_string = {'filter[single]': 'bogus'}
        response = self.app.get('/api/person/1/relationships/articles',
                                query_string=query_string)
        assert response.status_code == 400
        # TODO check the error message here.

    def test_in_list(self):
        """Tests for a filter object checking for a field with value in a
        specified list of acceptable values.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='id', op='in', val=[2, 3])]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert len(people) == 2
        assert ['2', '3'] == sorted(person['id'] for person in people)

    def test_any_in_to_many(self):
        """Test for filtering using the ``any`` operator with a sub-filter
        object on a to-many relationship.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        comment1 = self.Comment(content=u"that's cool!", author=person1)
        comment2 = self.Comment(content=u'i like turtles', author=person2)
        comment3 = self.Comment(content=u'not cool dude', author=person3)
        self.session.add_all([person1, person2, person3])
        self.session.add_all([comment1, comment2, comment3])
        self.session.commit()
        # Search for any people who have comments that contain the word "cool".
        filters = [dict(name='comments', op='any',
                        val=dict(name='content', op='like', val='%cool%'))]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['1', '3'] == sorted(person['id'] for person in people)

    def test_any_with_boolean(self):
        """Tests for nesting a Boolean formula under an ``any`` filter.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article1 = self.Article(id=1, publishtime=datetime(1900, 1, 1))
        article2 = self.Article(id=2, publishtime=datetime(2000, 1, 1))
        article1.author = person1
        article2.author = person2
        self.session.add_all([person1, person2, article1, article2])
        self.session.commit()
        # Filter by only those people that have articles published after
        # 1-1-1950 and before 1-1-2050.
        filters = [{
            'name': 'articles',
            'op': 'any',
            'val': {
                'and': [
                    {
                        'name': 'publishtime',
                        'op': '>',
                        'val': '1950-1-1'
                    },
                    {
                        'name': 'publishtime',
                        'op': '<',
                        'val': '2050-1-1'
                    }
                ]
            }
        }]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == [person['id'] for person in people]

    def test_has_in_to_one(self):
        """Test for filtering using the ``has`` operator with a sub-filter
        object on a to-one relationship.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        comment1 = self.Comment(content=u"that's cool!", author=person1)
        comment2 = self.Comment(content=u"i like turtles", author=person2)
        comment3 = self.Comment(content=u"not cool dude", author=person3)
        self.session.add_all([person1, person2, person3])
        self.session.add_all([comment1, comment2, comment3])
        self.session.commit()
        # Search for any comments whose author has ID equals to 1.
        filters = [dict(name='author', op='has',
                        val=dict(name='id', op='gt', val=1))]
        response = self.search('/api/comment', filters)
        document = loads(response.data)
        comments = document['data']
        assert ['2', '3'] == sorted(comment['id'] for comment in comments)

    def test_has_with_boolean(self):
        """Tests for nesting a Boolean formula under a ``has`` filter.

        """
        person1 = self.Person(id=1, bedtime=time(2))
        person2 = self.Person(id=2, bedtime=time(4))
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article1.author = person1
        article2.author = person2
        self.session.add_all([person1, person2, article1, article2])
        self.session.commit()
        # Filter by only those articles with an author that has a
        # bedtime greater than 1:00 and less than 3:00.
        filters = [{
            'name': 'author',
            'op': 'has',
            'val': {
                'and': [
                    {
                        'name': 'bedtime',
                        'op': '>',
                        'val': '1:00'
                    },
                    {
                        'name': 'bedtime',
                        'op': '<',
                        'val': '3:00'
                    }
                ]
            }
        }]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        assert ['1'] == [article['id'] for article in articles]

    def test_has_with_has(self):
        """Tests for nesting a ``has`` filter beneath another ``has`` filter.

        """
        for i in range(5):
            person = self.Person(id=i)
            article = self.Article(id=i)
            comment = self.Comment(id=i)
            article.author = person
            comment.author = person
            comment.article = article
            self.session.add_all([article, person, comment])
        self.session.commit()
        # Search for any comments whose articles have authors with id < 3.
        id_filter = dict(name='id', op='lt', val=3)
        author_filter = dict(name='author', op='has', val=id_filter)
        article_filter = dict(name='article', op='has', val=author_filter)
        filters = [article_filter]
        response = self.search('/api/comment', filters)
        document = loads(response.data)
        comments = document['data']
        assert ['0', '1', '2'] == sorted(comment['id'] for comment in comments)

    def test_any_with_any(self):
        """Tests for nesting an ``any`` filter beneath another ``any`` filter.

        """
        for i in range(5):
            person = self.Person(id=i)
            article = self.Article(id=i)
            comment = self.Comment(id=i)
            article.author = person
            comment.author = person
            comment.article = article
            self.session.add_all([article, person, comment])
        self.session.commit()
        # Search for any people whose articles have any comment with id < 3.
        id_filter = dict(name='id', op='lt', val=3)
        comments_filter = dict(name='comments', op='any', val=id_filter)
        articles_filter = dict(name='articles', op='any', val=comments_filter)
        filters = [articles_filter]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['0', '1', '2'] == sorted(person['id'] for person in people)

    def test_has_with_any(self):
        """Tests for nesting a ``has`` filter beneath an ``any`` filter."""
        for i in range(5):
            person = self.Person(id=i)
            article = self.Article(id=i)
            comment = self.Comment(id=i)
            article.author = person
            comment.author = person
            comment.article = article
            self.session.add_all([article, person, comment])
        self.session.commit()
        # Search for any articles with comments whose author has id < 3.
        id_filter = dict(name='id', op='lt', val=3)
        author_filter = dict(name='author', op='has', val=id_filter)
        comments_filter = dict(name='comments', op='any', val=author_filter)
        filters = [comments_filter]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        assert ['0', '1', '2'] == sorted(article['id'] for article in articles)

    def test_any_with_has(self):
        """Tests for nesting an ``any`` filter beneath a ``has`` filter."""
        for i in range(5):
            person = self.Person(id=i)
            article = self.Article(id=i)
            content = u'me' if i % 2 else u'you'
            comment = self.Comment(id=i, content=content)
            article.author = person
            comment.author = person
            self.session.add_all([article, person, comment])
        self.session.commit()
        # Search for any articles with an author who has made comments that
        # include the word "me".
        content_filter = dict(name='content', op='like', val='%me%')
        comment_filter = dict(name='comments', op='any', val=content_filter)
        author_filter = dict(name='author', op='has', val=comment_filter)
        filters = [author_filter]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        assert ['1', '3'] == sorted(article['id'] for article in articles)

    def test_comparing_fields(self):
        """Test for comparing the value of two fields in a filter object."""
        person1 = self.Person(id=1, age=1)
        person2 = self.Person(id=2, age=3)
        person3 = self.Person(id=3, age=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='age', op='eq', field='id')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['1', '3'] == sorted(person['id'] for person in people)

    def test_date_yyyy_mm_dd(self):
        """Test for date parsing in filter objects with dates of the form
        ``1969-07-20``.

        """
        person1 = self.Person(id=1, birthday=date(1969, 7, 20))
        person2 = self.Person(id=2, birthday=date(1900, 1, 2))
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='birthday', op='eq', val='1969-07-20')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['1'] == sorted(person['id'] for person in people)

    def test_date_english(self):
        """Tests for date parsing in filter object with dates of the form ``2nd
        Jan 1900``.

        """
        person1 = self.Person(id=1, birthday=date(1969, 7, 20))
        person2 = self.Person(id=2, birthday=date(1900, 1, 2))
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='birthday', op='eq', val='2nd Jan 1900')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_times(self):
        """Test for time parsing in filter objects."""
        person1 = self.Person(id=1, bedtime=time(17))
        person2 = self.Person(id=2, bedtime=time(19))
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='bedtime', op='eq', val='19:00')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_datetimes(self):
        """Test for datetime parsing in filter objects."""
        person1 = self.Person(id=1, birth_datetime=datetime(1900, 1, 2))
        person2 = self.Person(id=2, birth_datetime=datetime(1969, 7, 20))
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='birth_datetime', op='eq', val='1969-07-20')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_datetime_to_date(self):
        """Tests that a filter object with a datetime value and a field with a
        ``Date`` type automatically converts the datetime to a date.

        """
        person1 = self.Person(id=1, birthday=date(1969, 7, 20))
        person2 = self.Person(id=2, birthday=date(1900, 1, 2))
        self.session.add_all([person1, person2])
        self.session.commit()
        datestring = '2nd Jan 1900 14:35'
        filters = [dict(name='birthday', op='eq', val=datestring)]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_datetime_to_time(self):
        """Test that a datetime gets truncated to a time if the model has a
        time field.

        """
        person1 = self.Person(id=1, bedtime=time(1, 2))
        person2 = self.Person(id=2, bedtime=time(14, 35))
        self.session.add_all([person1, person2])
        self.session.commit()
        datetimestring = datetime(1900, 1, 2, 14, 35).isoformat()
        filters = [dict(name='bedtime', op='eq', val=datetimestring)]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_bad_date(self):
        """Tests that an invalid date causes an error."""
        filters = [dict(name='birthday', op='eq', val='bogus')]
        response = self.search('/api/person', filters)
        assert response.status_code == 400
        # TODO check error message here

    def test_bad_time(self):
        """Tests that an invalid time causes an error."""
        filters = [dict(name='bedtime', op='eq', val='bogus')]
        response = self.search('/api/person', filters)
        assert response.status_code == 400
        # TODO check error message here

    def test_bad_datetime(self):
        """Tests that an invalid datetime causes an error."""
        filters = [dict(name='created_at', op='eq', val='bogus')]
        response = self.search('/api/person', filters)
        assert response.status_code == 400
        # TODO check error message here

    def test_bad_name(self):
        """Tests that an invalid ``name`` element causes an error."""
        filters = [dict(name='bogus__field', op='eq', val='whatever')]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['no such field', 'bogus__field'])

    def test_search_boolean_formula(self):
        """Tests for Boolean formulas of filters in a search query."""
        person1 = self.Person(id=1, name=u'John', age=10)
        person2 = self.Person(id=2, name=u'Paul', age=20)
        person3 = self.Person(id=3, name=u'Luke', age=30)
        person4 = self.Person(id=4, name=u'Matthew', age=40)
        self.session.add_all([person1, person2, person3, person4])
        self.session.commit()
        # This searches for people whose name is John, or people older than age
        # 10 who have a "u" in their names. This should return three people:
        # John, Paul, and Luke.
        filters = [{'or': [{'and': [dict(name='name', op='like', val='%u%'),
                                    dict(name='age', op='ge', val=10)]},
                           dict(name='name', op='eq', val='John')]
                    }]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert len(people) == 3
        assert ['1', '2', '3'] == sorted(person['id'] for person in people)

    def test_dates_in_boolean_formulas(self):
        """Tests that dates are correctly handled in recursively defined
        boolean formula filters.

        For more information, see issue #423.

        """
        person1 = self.Person(id=1, birthday=date(1990, 1, 1))
        person2 = self.Person(id=2, birthday=date(1991, 1, 1))
        person3 = self.Person(id=3, birthday=date(1992, 1, 1))
        person4 = self.Person(id=4, birthday=date(1993, 1, 1))
        self.session.add_all([person1, person2, person3, person4])
        self.session.commit()
        filters = [
            {
                'and': [
                    {
                        'name': 'birthday',
                        'op': '>',
                        'val': '1990-1-1'
                    },
                    {
                        'name': 'birthday',
                        'op': '<',
                        'val': '1993-1-1'
                    }
                ]
            }
        ]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert len(people) == 2
        assert ['2', '3'] == sorted(person['id'] for person in people)

    @skip("I'm not certain in what situations an invalid value should cause"
          " a SQLAlchemy error")
    def test_invalid_value(self):
        """Tests for an error response on an invalid value in a filter object.

        """
        filters = [dict(name='age', op='>', val='should not be a string')]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['invalid', 'argument', 'value'])

    def test_invalid_field(self):
        """Tests for an error response on an invalid field name in a filter
        object.

        """
        filters = [dict(name='foo', op='>', val=2)]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['no such field', 'foo'])

    def test_invalid_other(self):
        """Tests that an invalid field name for the "other" field causes
        an error.

        """
        filters = [{'name': 'age', 'op': 'eq', 'field': 'bogus'}]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['no such field', 'bogus'])

    def test_invalid_operator(self):
        """Tests for an error response on an invalid operator in a filter
        object.

        """
        filters = [dict(name='age', op='bogus', val=2)]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['unknown', 'operator', 'bogus'])

    def test_missing_argument(self):
        """Tests that filter requests with a missing ``'val'`` causes an error
        response.

        """
        filters = [dict(name='name', op='==')]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['expected', 'argument', 'operator',
                                         'none'])

    def test_missing_fieldname(self):
        """Tests that filter requests with a missing ``'name'`` causes an error
        response.

        """
        filters = [dict(op='==', val='foo')]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['missing', 'field', 'name'])

    def test_missing_operator(self):
        """Tests that filter requests with a missing ``'op'`` causes an error
        response.

        """
        filters = [dict(name='age', val=3)]
        response = self.search('/api/person', filters)
        check_sole_error(response, 400, ['missing', 'operator'])

    def test_to_many_relation(self):
        """Tests for filtering a to-many relation."""
        person = self.Person(id=1)
        articles = [self.Article(id=i) for i in range(5)]
        person.articles = articles
        self.session.add(person)
        self.session.add_all(articles)
        self.session.commit()
        filters = [dict(name='id', op='gt', val=2)]
        response = self.search('/api/person/1/articles', filters)
        document = loads(response.data)
        articles = document['data']
        assert ['3', '4'] == sorted(article['id'] for article in articles)

    def test_hybrid_property(self):
        """Test for filtering on a hybrid property.

        In this test, the hybrid attribute and the SQL expression are of
        the same type.

        """
        person1 = self.Person(id=1, age=10)
        person2 = self.Person(id=2, age=20)
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='is_minor', op='==', val=True)]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        self.assertEqual(len(people), 1)
        person = people[0]
        self.assertEqual(person['id'], '1')

    def test_hybrid_expression(self):
        """Test for filtering on a hybrid property with a separate expression.

        For more information, see GitHub issue #562.

        """
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        comment = self.Comment(id=1)
        comment.article = article1
        self.session.add_all([article1, article2, comment])
        self.session.commit()

        filters = [{'name': 'has_comments', 'op': '==', 'val': True}]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        self.assertEqual(['1'], sorted(article['id'] for article in articles))

        filters = [{'name': 'has_comments', 'op': '==', 'val': False}]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        self.assertEqual(['2'], sorted(article['id'] for article in articles))

    def test_urlencode_pagination_links(self):
        """Test that filter objects in pagination links are URL-encoded.

        For more information, see GitHub issue #553.

        """
        people = [self.Person(id=i) for i in range(30)]
        self.session.add_all(people)
        self.session.commit()
        filters = [dict(name='id', op='gte', val=0)]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        links = document['links']
        expected = 'filter[objects]=[{"name":"id","op":"gte","val":0}]'
        self.assertIn(expected, unquote(links['first']))
        self.assertIn(expected, unquote(links['last']))


class TestSimpleFiltering(ManagerTestBase):
    """Unit tests for "simple" filter query parameters.

    These are filters of the form

    .. sourcecode:: http

       GET /comments?filter[post]=1,2&filter[author]=12 HTTP/1.1

    """

    def setUp(self):
        super(TestSimpleFiltering, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            age = Column(Integer)

        class Tag(self.Base):
            __tablename__ = 'tag'
            name = Column(Unicode, primary_key=True)
            id = Column(Integer)

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship(Person)
            tag_name = Column(Unicode, ForeignKey('tag.name'))
            tag = relationship(Tag)

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Comment)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        self.manager.create_api(Article)
        self.manager.create_api(Person)
        self.manager.create_api(Tag)

    def test_single_foreign_key(self):
        """Tests for filtering resources by relationship foreign key."""
        for i in range(1, 3):
            comment = self.Comment(id=i)
            article = self.Article(id=i)
            comment.article = article
            self.session.add_all([article, comment])
        self.session.commit()
        query_string = {'filter[article]': 1}
        response = self.app.get('/api/comment', query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['1'] == sorted(comment['id'] for comment in comments)

    def test_multiple_foreign_keys(self):
        """Tests for filtering resources by those having a relationship
        foreign key in a given set of keys.

        """
        for i in range(1, 4):
            comment = self.Comment(id=i)
            article = self.Article(id=i)
            comment.article = article
            self.session.add_all([article, comment])
        self.session.commit()
        query_string = {'filter[article]': ','.join(['1', '2'])}
        response = self.app.get('/api/comment', query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_multiple_relationships(self):
        for i in range(1, 4):
            comment = self.Comment(id=i)
            article = self.Article(id=i)
            person = self.Person(id=i)
            comment.article = article
            comment.author = person
            self.session.add_all([article, comment, person])
        self.session.commit()
        query_string = {'filter[article]': ','.join(['1', '2']),
                        'filter[author]': 2}
        response = self.app.get('/api/comment', query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['2'] == sorted(comment['id'] for comment in comments)

    def test_primary_key_string(self):
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        tag1 = self.Tag(name=u'foo')
        tag2 = self.Tag(name=u'bar')
        comment1.tag = tag1
        comment2.tag = tag2
        self.session.add_all([comment1, comment2, tag1, tag2])
        self.session.commit()
        query_string = {'filter[tag]': u'foo'}
        response = self.app.get('/api/comment', query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['1'] == sorted(comment['id'] for comment in comments)

    def test_custom_primary_key(self):
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        tag1 = self.Tag(id=1, name=u'foo')
        tag2 = self.Tag(id=2, name=u'bar')
        comment1.tag = tag1
        comment2.tag = tag2
        self.session.add_all([comment1, comment2, tag1, tag2])
        self.session.commit()
        # TODO This won't work, since the other API for Tag still exists.
        self.manager.create_api(self.Tag, primary_key='id')
        query_string = {'filter[tag]': 1}
        response = self.app.get('/api/comment', query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['1'] == sorted(comment['id'] for comment in comments)

    def test_field_name(self):
        """Tests for filtering by field name."""
        person1 = self.Person(id=1, age=10)
        person2 = self.Person(id=2, age=20)
        person3 = self.Person(id=3, age=10)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        query_string = {'filter[age]': 10}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        assert ['1', '3'] == sorted(person['id'] for person in people)

    def test_simple_and_complex(self):
        """Tests for requests that employ both simple filtering and
        (complex) filter objects.

        """
        person1 = self.Person(id=1, age=10)
        person2 = self.Person(id=2, age=20)
        person3 = self.Person(id=3, age=10)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [{'name': 'id', 'op': '<', 'val': 3}]
        query_string = {
            'filter[age]': 10,
            'filter[objects]': dumps(filters)
        }
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        assert ['1'] == sorted(person['id'] for person in people)

    def test_to_many_filter_by_relation(self):
        """Tests for simple filtering on a to-many relation endpoint."""
        article = self.Article(id=1)
        self.session.add(article)
        for i in range(1, 3):
            comment = self.Comment(id=i)
            tag = self.Tag(name=u'{0}'.format(i))
            comment.article = article
            comment.tag = tag
            self.session.add_all([comment, tag])
        self.session.commit()
        # There are two comments on article 1, each with a distinct
        # tag. Let's choose the sole comment on the article with tag
        # '1'.
        query_string = {'filter[tag]': '1'}
        response = self.app.get('/api/article/1/comments',
                                query_string=query_string)
        document = loads(response.data)
        comments = document['data']
        assert ['1'] == sorted(comment['id'] for comment in comments)


class TestOperators(SearchTestBase):
    """Tests for each SQLAlchemy operator supported by Flask-Restless."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application,
        and creates the ReSTful API endpoints for the models used in the test
        methods.

        """
        super(TestOperators, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            # age = Column(Integer)
            # birthday = Column(Date)

        # class Comment(self.Base):
        #     __tablename__ = 'comment'
        #     id = Column(Integer, primary_key=True)
        #     content = Column(Unicode)
        #     author_id = Column(Integer, ForeignKey('person.id'))
        #     author = relationship('Person', backref=backref('comments'))

        self.Person = Person
        # self.Comment = Comment
        self.Base.metadata.create_all()
        self.manager.create_api(Person)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        # self.manager.create_api(Comment)

    def test_equals(self):
        """Tests for the ``eq`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        for op in '==', 'eq', 'equals', 'equal_to':
            filters = [dict(name='id', op=op, val=1)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['1'] == sorted(person['id'] for person in people)

    def test_not_equal(self):
        """Tests for the ``neq`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        for op in '!=', 'ne', 'neq', 'not_equal_to', 'does_not_equal':
            filters = [dict(name='id', op=op, val=1)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['2'] == sorted(person['id'] for person in people)

    def test_greater_than(self):
        """Tests for the ``gt`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        for op in '>', 'gt':
            filters = [dict(name='id', op=op, val=1)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['2'] == sorted(person['id'] for person in people)

    def test_less_than(self):
        """Tests for the ``lt`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        for op in '<', 'lt':
            filters = [dict(name='id', op=op, val=2)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['1'] == sorted(person['id'] for person in people)

    def test_greater_than_or_equal(self):
        """Tests for the ``gte`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        for op in '>=', 'ge', 'gte', 'geq':
            filters = [dict(name='id', op=op, val=2)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['2', '3'] == sorted(person['id'] for person in people)

    def test_less_than_or_equal(self):
        """Tests for the ``lte`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        for op in '<=', 'le', 'lte', 'leq':
            filters = [dict(name='id', op=op, val=2)]
            response = self.search('/api/person', filters)
            document = loads(response.data)
            people = document['data']
            assert ['1', '2'] == sorted(person['id'] for person in people)

    def test_like(self):
        """Tests for the ``like`` operator."""
        person1 = self.Person(name=u'foo')
        person2 = self.Person(name=u'bar')
        person3 = self.Person(name=u'baz')
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='name', op='like', val='%ba%')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['bar', 'baz'] == sorted(person['attributes']['name']
                                        for person in people)

    def test_not_like(self):
        """Tests for the ``not_like`` operator."""
        person1 = self.Person(name=u'foo')
        person2 = self.Person(name=u'bar')
        person3 = self.Person(name=u'baz')
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='name', op='not_like', val='%fo%')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['bar', 'baz'] == sorted(person['attributes']['name']
                                        for person in people)

    def test_ilike(self):
        """Tests for the ``ilike`` operator."""
        person1 = self.Person(name=u'foo')
        person2 = self.Person(name=u'bar')
        person3 = self.Person(name=u'baz')
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='name', op='ilike', val='%BA%')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['bar', 'baz'] == sorted(person['attributes']['name']
                                        for person in people)

    def test_in(self):
        """Tests for the ``in`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='id', op='in', val=[1, 3])]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['1', '3'] == sorted(person['id'] for person in people)

    def test_not_in(self):
        """Tests for the ``not_in`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        person3 = self.Person(id=3)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        filters = [dict(name='id', op='not_in', val=[1, 3])]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_is_null(self):
        """Tests for the ``is_null`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2, name=u'foo')
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='name', op='is_null')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['1'] == sorted(person['id'] for person in people)

    def test_is_not_null(self):
        """Tests for the ``is_not_null`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2, name=u'foo')
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [dict(name='name', op='is_not_null')]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_negation(self):
        """Test for the ``not`` operator."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        filters = [{'not': {'name': 'id', 'op': 'lt', 'val': 2}}]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        assert ['2'] == sorted(person['id'] for person in people)

    def test_compare_equals_to_null(self):
        """Tests that an attempt to compare the value of a field to ``None``
        using the ``eq`` operator yields an error response, indicating that the
        user should use the ``is_null` operation instead.

        """
        filters = [dict(name='name', op='eq', val=None)]
        response = self.search('/api/person', filters)
        keywords = ['compare', 'value', 'NULL', 'use', 'is_null', 'operator']
        check_sole_error(response, 400, keywords)

    def test_custom_operator(self):
        """Test for a custom operator provided by the user.

        For more information, see GitHub pull request #590.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        register_operator('my_gt', gt)
        filters = [dict(name='id', op='my_gt', val=1)]
        response = self.search('/api/person', filters)
        document = loads(response.data)
        people = document['data']
        self.assertEqual(['2'], [person['id'] for person in people])


class TestAssociationProxy(SearchTestBase):
    """Test for filtering on association proxies."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application,
        and creates the ReSTful API endpoints for the models used in the test
        methods.

        """
        super(TestAssociationProxy, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            tags = association_proxy('articletags', 'tag',
                                     creator=lambda tag: ArticleTag(tag=tag))

        class ArticleTag(self.Base):
            __tablename__ = 'articletag'
            article_id = Column(Integer, ForeignKey('article.id'),
                                primary_key=True)
            article = relationship(Article, backref=backref('articletags'))
            tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
            tag = relationship('Tag')
            # TODO this dummy column is required to create an API for this
            # object.
            id = Column(Integer)

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Article = Article
        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        self.manager.create_api(ArticleTag)
        self.manager.create_api(Tag)

    def test_any(self):
        """Tests for filtering on a many-to-many relationship via an
        association proxy backed by an association object.

        """
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article3 = self.Article(id=3)
        tag1 = self.Tag(name=u'foo')
        tag2 = self.Tag(name=u'bar')
        tag3 = self.Tag(name=u'baz')
        article1.tags = [tag1, tag2]
        article2.tags = [tag2, tag3]
        article3.tags = [tag3, tag1]
        self.session.add_all([article1, article2, article3])
        self.session.add_all([tag1, tag2, tag3])
        self.session.commit()
        filters = [dict(name='tags', op='any',
                        val=dict(name='name', op='eq', val='bar'))]
        response = self.search('/api/article', filters)
        document = loads(response.data)
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
