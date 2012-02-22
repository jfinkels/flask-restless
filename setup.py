import os
from setuptools import setup


def read(fname):
    open(os.path.join(os.path.dirname(__file__), fname)).read()


def from_requirements_file():
    """Returns a list of required Python packages from the
    :file:`requirements.txt` file in this directory.

    """
    with open('requirements.txt', 'r') as f:
        requirements = f.read()
    return requirements.split()


setup(
    name='RESTfulEf',
    version='0.2',
    author='Lincoln de Sousa',
    author_email='lincoln@comum.org',
    description='A generic restful api generator based on elixir and flask',
    license='AGPLv3+',
    keywords='rest api flask elixir',
    url='http://projects.comum.org/restful',
    packages=('restful',),
    install_requires=from_requirements_file(),
    test_suite='tests.restful_tests',
    long_description=read('README'),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: Database',
        'Topic :: Database :: Front-Ends',
        'Topic :: Internet :: WWW/HTTP',
    ]
)
