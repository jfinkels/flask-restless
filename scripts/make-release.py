#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    make-release
    ~~~~~~~~~~~~

    Helper script that performs a release.  Does pretty much everything
    automatically for us.

    :copyright: (c) 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
import re
from datetime import datetime, date
from subprocess import Popen, PIPE

_date_clean_re = re.compile(r'(\d+)(st|nd|rd|th)')


def add_new_changelog_section(current_version, next_version):
    version_string = 'Version {}'.format(current_version)
    with open('CHANGES') as f:
        all_lines = f.readlines()
    stripped_lines = [l.strip() for l in all_lines]
    try:
        # get the index of the first occurrence of `version_string`
        line_num = stripped_lines.index(version_string)
    except:
        fail('Could not find "{}" in {}.'.format(version_string, 'CHANGES'))
    new_header = 'Version {}'.format(next_version)
    horizontal_rule = '-' * len(new_header)
    new_lines = [new_header + '\n', horizontal_rule + '\n', '\n',
                 'Not yet released.' + '\n', '\n']
    # insert the new lines into the list of all lines read from CHANGES
    all_lines[line_num:line_num] = new_lines
    # write the changes back to...CHANGES
    with open('CHANGES', 'w') as f:
        f.writelines(all_lines)


def parse_changelog():
    with open('CHANGES') as f:
        lineiter = iter(f)
        for line in lineiter:
            match = re.search('^Version\s+(.*)', line.strip())
            if match is None:
                continue
            # length = len(match.group(1))
            version = match.group(1).strip()
            if lineiter.next().count('-') != len(match.group(0)):
                continue
            while 1:
                change_info = lineiter.next().strip()
                if change_info:
                    break

            match = re.search(r'Released on (\w+\s+\d+,\s+\d+)',
                              change_info)
            if match is None:
                continue

            datestr = match.groups()[0]
            return version, parse_date(datestr)


def bump_version(version):
    try:
        parts = map(int, version.split('.'))
    except ValueError:
        fail('Current version is not numeric')
    if sys.argv[1] == 'major':
        parts = [parts[0] + 1, 0, 0]
    elif sys.argv[1] == 'minor':
        parts = [parts[0], parts[1] + 1, 0]
    else:
        parts[-1] += 1
    return '.'.join(map(str, parts))


def parse_date(string):
    string = _date_clean_re.sub(r'\1', string)
    return datetime.strptime(string, '%B %d, %Y')


def set_filename_version(filename, version_number, pattern):
    changed = []

    def inject_version(match):
        before, old, after = match.groups()
        changed.append(True)
        return before + version_number + after
    with open(filename) as f:
        contents = re.sub(r"^(\s*%s\s*=\s*')(.+?)(')(?sm)" % pattern,
                          inject_version, f.read())

    if not changed:
        fail('Could not find %s in %s', pattern, filename)

    with open(filename, 'w') as f:
        f.write(contents)


def set_init_version(version):
    info('Setting __init__.py version to %s', version)
    set_filename_version('flask_restless/__init__.py', version, '__version__')


def set_setup_version(version):
    info('Setting setup.py version to %s', version)
    set_filename_version('setup.py', version, 'version')


def build():
    Popen([sys.executable, 'setup.py', 'sdist', 'bdist_wheel']).wait()


def sign(version):
    bdist_wheel = 'dist/Flask_Restless-{0}-py2.py3-none-any.whl'
    bdist_wheel = bdist_wheel.format(version)
    sdist = 'dist/Flask-Restless-{0}.tar.gz'.format(version)
    Popen(['gpg', '--detach-sign', '-a', bdist_wheel]).wait()
    Popen(['gpg', '--detach-sign', '-a', sdist]).wait()


def upload(version):
    bdist_wheel = 'dist/Flask_Restless-{0}-py2.py3-none-any.whl'
    bdist_wheel = bdist_wheel.format(version)
    bdist_wheel_signature = '{0}.asc'.format(bdist_wheel)
    sdist = 'dist/Flask-Restless-{0}.tar.gz'.format(version)
    sdist_signature = '{0}.asc'.format(bdist_wheel)
    files = [sdist, sdist_signature, bdist_wheel, bdist_wheel_signature]
    Popen(['twine', 'upload'] + files).wait()


def fail(message, *args):
    print >> sys.stderr, 'Error:', message % args
    sys.exit(1)


def info(message, *args):
    print >> sys.stderr, message % args


def get_git_tags():
    process = Popen(['git', 'tag'], stdout=PIPE)
    return set(process.communicate()[0].splitlines())


def git_is_clean():
    return Popen(['git', 'diff', '--quiet']).wait() == 0


def make_git_commit(message, *args):
    message = message % args
    Popen(['git', 'commit', '-am', message]).wait()


def make_git_tag(tag):
    info('Tagging "%s"', tag)
    msg = '"Released version {}"'.format(tag)
    Popen(['git', 'tag', '-s', '-m', msg, tag]).wait()


def main():
    os.chdir(os.path.join(os.path.dirname(__file__), '..'))

    rv = parse_changelog()
    if rv is None:
        fail('Could not parse changelog')

    version, release_date = rv
    dev_version = bump_version(version) + '-dev'

    info('Releasing %s (release date %s)',
         version, release_date.strftime('%d/%m/%Y'))
    tags = get_git_tags()

    if version in tags:
        fail('Version "%s" is already tagged', version)
    if release_date.date() != date.today():
        fail('Release date is not today (%s != %s)')

    if not git_is_clean():
        fail('You have uncommitted changes in git')

    set_init_version(version)
    # set_setup_version(version)
    make_git_commit('Bump version number to %s', version)
    make_git_tag(version)
    build()
    sign(version)
    upload(version)
    set_init_version(dev_version)
    # set_setup_version(dev_version)
    add_new_changelog_section(version, dev_version)
    make_git_commit('Set development version number to %s', dev_version)
    print('*************************************')
    print('*                                   *')
    print('* Now run                           *')
    print('*                                   *')
    print('*     git push --tags origin master *')
    print('*                                   *')
    print('*************************************')


if __name__ == '__main__':
    main()
