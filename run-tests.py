#!/usr/bin/env python

# add the current directory to the Python path
import os.path
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from unittest2 import main
from tests import suite

main(defaultTest='suite')
