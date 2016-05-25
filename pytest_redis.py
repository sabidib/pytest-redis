"""pytest-redis queue plugin implementation."""
import os

import redis
import pytest
import itertools

from _pytest.terminal import TerminalReporter
import _pytest.runner
from _pytest.main import NoMatch
from _pytest.main import EXIT_NOTESTSCOLLECTED, EXIT_OK


def pytest_addoption(parser):
    """Add command line options to py.test command."""
    parser.addoption('--redis-host', metavar='redis_host',
                     type=str, help='The host of the redis instance.',
                     required=True)
    parser.addoption('--redis-port', metavar='redis_port',
                     type=str, help='The port of the redis instance.',
                     required=True)
    parser.addoption('--redis-pop-type', metavar='redis_pop_type',
                     type=str,
                     help=('Indicates which side the of the redis list '
                           'a test is removed from.'),
                     choices=['RPOP', 'rpop', 'LPOP', 'lpop'],
                     default="RPOP")
    parser.addoption('--redis-push-type', metavar='redis_push_type',
                     type=str,
                     help=('Indicates which side the of the redis list '
                           'a test is pushed to, if tests are ever pushed.'),
                     choices=['RPUSH', 'rpush', 'LPUSH', 'lpush'],
                     default="LPUSH")
    parser.addoption('--redis-list-key', metavar='redis_list_key',
                     type=str,
                     help=('The key of the redis list containing '
                           'the test paths to execute.'),
                     required=True)
    parser.addoption('--redis-backup-list-key',
                     metavar='redis_backup_list_key',
                     type=str,
                     default=None,
                     help=('The key of the redis list where tests '
                           'that have been ran are pushed to. If the main '
                           'redis list specified by redis-list-key is empty '
                           'then this list is polled for the next tests.'
                           'If the main redis-list-key is not empty then ran '
                           'tests are pushed to this list.'),
                     required=False)


def push_tests_to_redis(redis_connection, list_key, redis_push_type, element):
    """Push a test path from the redis queue."""
    val = None
    if redis_push_type.lower() == "lpush":
        val = redis_connection.lpush(list_key, element)
    elif redis_push_type.lower() == "rpush":
        val = redis_connection.rpush(list_key, element)
    return val


def retrieve_test_from_redis(redis_connection, list_key, redis_pop_type):
    """Remove and return a test path from the redis queue."""
    val = None
    if redis_pop_type.lower() == "lpop":
        val = redis_connection.lpop(list_key)
    elif redis_pop_type.lower() == "rpop":
        val = redis_connection.rpop(list_key)
    return val


def pytest_collection(session, genitems=True):
    """We hook into the collection call and do the collection ourselves."""
    hook = session.config.hook
    try:
        items = perform_collect_and_run(session)
    finally:
        hook.pytest_collection_finish(session=session)
    session.testscollected = len(items)
    return items


def get_redis_connection(config):
    """Get a redis connection base on config args."""
    redis_host = config.getoption('redis_host')
    redis_port = config.getoption('redis_port')
    r_client = redis.StrictRedis(host=redis_host,
                                 port=redis_port)
    return r_client


def determine_redis_list_key_to_use(session, redis_connection,
                                    redis_pop_type, redis_push_type):
    """Determine generator for tests from the state of the main and backup list.

    We use the cmdline args along with the empty state of the main and backup
    lists to determine if the generator for the test paths that
    should be returned.

    If the main redis list (specified by 'redis_list_key') is not empty,
    return the generator for that list.

    If the main redis list is empty then the backup redis list(specified by
    'redis_backup_list_key') is checked to see if it is empty.
    If it is not empty, then pop all elements off and push them onto
    the main redis list and then return a generator for that list.

    Finally, if both lists are empty, return the main redis list
    iterator as is.
    """
    redis_list_key = session.config.getoption("redis_list_key")
    backup_list_key = session.config.getoption("redis_backup_list_key")

    final_redis_list = None

    if redis_connection.llen(redis_list_key) == 0 and backup_list_key is not None:
        # Check if the backup redist list is empty
        if redis_connection.llen(backup_list_key) != 0:
            # Push tests to the main redis list
            prev_list = redis_test_generator(session.config,
                                             redis_connection,
                                             backup_list_key,
                                             redis_pop_type)
            for test in prev_list:
                push_tests_to_redis(redis_connection, redis_list_key,
                                    redis_push_type, test)
        final_redis_list = redis_test_generator(session.config,
                                                redis_connection,
                                                redis_list_key,
                                                redis_pop_type)
    else:
        final_redis_list = redis_test_generator(session.config,
                                                redis_connection,
                                                redis_list_key,
                                                redis_pop_type)

    return final_redis_list


def perform_collect_and_run(session):
    """Collect and run tests streaming from the redis queue."""
    # This mimics the internal pytest collect loop, but shortened
    # while running tests as soon as they are found.
    term = TerminalReporter(session.config)

    redis_connection = get_redis_connection(session.config)
    redis_push_type = session.config.getoption('redis_push_type')
    redis_pop_type = session.config.getoption('redis_pop_type')

    redis_list = determine_redis_list_key_to_use(session,
                                                 redis_connection,
                                                 redis_pop_type,
                                                 redis_push_type)

    backup_list_key = session.config.getoption("redis_backup_list_key")

    hook = session.config.hook
    session._initialpaths = set()
    session._initialparts = []
    session._notfound = []
    session.items = []
    for arg in redis_list:
        term.write(os.linesep)
        if backup_list_key:
            push_tests_to_redis(redis_connection, backup_list_key,
                                redis_push_type, arg)
        parts = session._parsearg(arg)
        session._initialparts.append(parts)
        session._initialpaths.add(parts[0])
        arg = "::".join(map(str, parts))
        session.trace("processing argument", arg)
        session.trace.root.indent += 1
        try:
            for x in session._collect(arg):
                items = session.genitems(x)
                new_items = []
                for item in items:
                    new_items.append(item)
                hook.pytest_collection_modifyitems(session=session,
                                                   config=session.config,
                                                   items=new_items)
                for item in new_items:
                    session.items.append(item)
                    _pytest.runner.pytest_runtest_protocol(item, None)
        except NoMatch:
            # we are inside a make_report hook so
            # we cannot directly pass through the exception
            raise pytest.UsageError("Could not find" + arg)

        session.trace.root.indent -= 1
    return session.items


def redis_test_generator(config, redis_connection, redis_list_key,
                         redis_pop_type):
    """A generator that pops and returns test paths from the redis list key."""
    term = TerminalReporter(config)

    val = retrieve_test_from_redis(redis_connection,
                                   redis_list_key,
                                   redis_pop_type)

    if val is None:
        term.write("No items in redis list '%s'\n" % redis_list_key)

    while val is not None:
        yield val
        val = retrieve_test_from_redis(redis_connection,
                                       redis_list_key,
                                       redis_pop_type)


def pytest_runtest_protocol(item, nextitem):
    """Called when an item is run. Returning true stops the hook chain."""
    return True


def pytest_sessionfinish(session, exitstatus):
    """Called when the entire test session is completed."""
    # adjust the return value to return EXIT_OK
    # when no tests are collected.
    if session.exitstatus == EXIT_NOTESTSCOLLECTED:
        session.exitstatus = EXIT_OK
        return EXIT_OK
    else:
        return session.exitstatus
