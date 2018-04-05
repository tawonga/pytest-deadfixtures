"""
Some functions are basically copy n' paste version of code already in pytest.
Precisely the get_fixtures, get_used_fixturesdefs and write_docstring funtions.
"""
from collections import namedtuple
from itertools import combinations
from textwrap import dedent

import _pytest.config
import py
from _pytest.compat import getlocation

AvailableFixture = namedtuple(
    'AvailableFixture',
    'relpath, argname, fixturedef'
)

CachedFixture = namedtuple(
    'CachedFixture',
    'fixturedef, relpath, result'
)


def pytest_addoption(parser):
    group = parser.getgroup('deadfixtures')
    group.addoption(
        '--dead-fixtures',
        action='store_true',
        dest='deadfixtures',
        default=False,
        help='Show fixtures not being used'
    )
    group.addoption(
        '--dup-fixtures',
        action='store_true',
        dest='showrepeated',
        default=False,
        help='Show duplicated fixtures'
    )


def pytest_cmdline_main(config):
    if config.option.deadfixtures:
        _show_dead_fixtures(config)
        return 0


def _show_dead_fixtures(config):
    from _pytest.main import wrap_session
    return wrap_session(config, show_dead_fixtures)


def get_best_relpath(func, curdir):
    loc = getlocation(func, curdir)
    return curdir.bestrelpath(loc)


def get_fixtures(session):
    available = []
    seen = set()
    fm = session._fixturemanager
    curdir = py.path.local()

    for argname, fixturedefs in fm._arg2fixturedefs.items():
        assert fixturedefs is not None
        if not fixturedefs:
            continue
        for fixturedef in fixturedefs:
            loc = getlocation(fixturedef.func, curdir)
            if (fixturedef.argname, loc) in seen:
                continue

            seen.add((fixturedef.argname, loc))

            module = fixturedef.func.__module__

            if (
                not module.startswith("_pytest.") and
                not module.startswith("pytest_") and
                not ('site-packages' in loc)
            ):
                available.append(AvailableFixture(
                    curdir.bestrelpath(loc),
                    fixturedef.argname,
                    fixturedef
                ))

    available.sort()
    return available


def get_used_fixturesdefs(session):
    fixturesdefs = []
    for test_function in session.items:
        try:
            info = test_function._fixtureinfo
        except AttributeError:
            # doctests items have no _fixtureinfo attribute
            continue
        if not info.name2fixturedefs:
            # this test item does not use any fixtures
            continue

        for _, fixturedefs in sorted(info.name2fixturedefs.items()):
            if fixturedefs is None:
                continue
            fixturesdefs.append(fixturedefs[-1])
    return fixturesdefs


def write_docstring(tw, doc):
    INDENT = "    "
    doc = doc.rstrip()
    if "\n" in doc:
        firstline, rest = doc.split("\n", 1)
    else:
        firstline, rest = doc, ""

    if firstline.strip():
        tw.line(INDENT + firstline.strip())

    if rest:
        for line in dedent(rest).split("\n"):
            tw.write(INDENT + line + "\n")


def write_fixtures(tw, fixtures, write_docs):
    for fixture in fixtures:
        tplt = 'Fixture name: {}, location: {}'
        tw.line(tplt.format(fixture.argname, fixture.relpath))
        doc = fixture.fixturedef.func.__doc__ or ''
        if write_docs and doc:
            write_docstring(tw, doc)


cached_fixtures = []


def pytest_fixture_post_finalizer(fixturedef):
    if hasattr(fixturedef, 'cached_result'):
        curdir = py.path.local()
        loc = getlocation(fixturedef.func, curdir)

        cached_fixtures.append(
            CachedFixture(
                fixturedef,
                curdir.bestrelpath(loc),
                fixturedef.cached_result[0]
            )
        )


def pytest_sessionfinish(session, exitstatus):
    if exitstatus or not session.config.getvalue('showrepeated'):
        return exitstatus

    def result_same_type(a, b):
        return isinstance(a.result, type(b.result))

    def equal_result(a, b):
        if not a.result or not b.result:
            return False
        if hasattr(a.result, '__dict__') or hasattr(b.result, '__dict__'):
            return a.result.__dict__ == b.result.__dict__
        return a.result == b.result

    def same_loc(a, b):
        return a.relpath == b.relpath

    tw = _pytest.config.create_terminal_writer(session.config)

    tw.line('\n\nYou may have some duplicate fixtures:', red=True)
    tplt = 'Fixture name: {}, location: {}'
    for a, b in combinations(cached_fixtures, 2):
        if result_same_type(a, b) and equal_result(a, b) and not same_loc(a, b):
            tw.line(tplt.format(a.fixturedef.argname, a.relpath))
            tw.line(tplt.format(b.fixturedef.argname, b.relpath))


def show_dead_fixtures(config, session):
    session.perform_collect()
    tw = _pytest.config.create_terminal_writer(config)
    verbose = config.getvalue('verbose')

    used_fixtures = get_used_fixturesdefs(session)
    available_fixtures = get_fixtures(session)

    unused_fixtures = [fixture for fixture in available_fixtures
                       if fixture.fixturedef not in used_fixtures]

    tw.line()
    if unused_fixtures:
        tw.line(
            'Hey there, I believe the following fixture(s) are not being used:',
            red=True
        )
        write_fixtures(tw, unused_fixtures, verbose)
    else:
        tw.line('Cool, every declared fixture is being used.', green=True)
