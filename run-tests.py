#!/usr/bin/env python

# add the current directory to the Python path
import os.path
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import unittest2
from tests import suite

def main():
    unittest2.main(defaultTest='suite')

if __name__ == '__main__':
    main()
