"""pytest-redis queue plugin implementation."""
from _pytest.terminal import TerminalReporter
import _pytest.runner
import redis
# Exit value when everything is okay
from _pytest.main import EXIT_OK
# Exit value when no tests are collected
from _pytest.main import EXIT_NOTESTSCOLLECTED
# Exit value whenever a single test fails
from _pytest.main import EXIT_TESTSFAILED
# Exit value when an exception is thrown by parser or KeyboardInterrupt
from _pytest.main import EXIT_INTERRUPTED
# Exit value when incorrect cmdline args are passed
from _pytest.main import EXIT_USAGEERROR
# Exit value when an internal error occurs
from _pytest.main import EXIT_INTERNALERROR


tests_collected = 0


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
                     help=('The key of the redis list containing '
                           'the test paths to execute.'),
                     choices=['RPOP', 'rpop', 'LPOP', 'lpop'],
                     default="RPOP")
    parser.addoption('--redis-list-key', metavar='redis_list_key',
                     type=str,
                     help=('The key of the redis list containing '
                           'the test paths to execute.'),
                     required=True)


def retrieve_test_from_redis(redis_connection, list_key, command):
    """Remove and return a test path from the redis queue."""
    val = None
    if command.lower() == "lpop":
        val = redis_connection.lpop(list_key)
    elif command.lower() == "rpop":
        val = redis_connection.rpop(list_key)
    return val


def redis_test_generator(config, args_to_prepend):
    """A generator that pops and returns test paths from the redis list."""
    term = TerminalReporter(config)

    redis_host = config.getoption('redis_host')
    redis_port = config.getoption('redis_port')
    redis_pop_type = config.getoption('redis_pop_type')
    redis_list_key = config.getoption('redis_list_key')

    r_client = redis.StrictRedis(host=redis_host,
                                 port=redis_port)

    val = retrieve_test_from_redis(r_client,
                                   redis_list_key,
                                   redis_pop_type)

    if val is None:
        term.write("No items in redis list '%s'\n" % redis_list_key)
        term.write("Running all tests\n")

    while val is not None:
        yield val
        val = retrieve_test_from_redis(r_client,
                                       redis_list_key,
                                       redis_pop_type)


def pytest_cmdline_main(config):
    """Convert the args to pull from a redis queue."""
    config.args = redis_test_generator(config, config.args)


def pytest_runtest_protocol(item, nextitem):
    """Called when an item is run. Returning true stops the hook chain."""
    return True


def pytest_itemcollected(item):
    """Called when an item is found in the collection.

    We jump the gun and execute the item in place instead of
    waiting for the run test loop.
    """
    global tests_collected
    tests_collected += 1
    _pytest.runner.pytest_runtest_protocol(item, None)


def pytest_sessionfinish(session, exitstatus):
    """Called when the entire test session is completed."""
    global tests_collected
    session.testscollected = tests_collected
    # default returns
    if (session.exitstatus == EXIT_INTERRUPTED or
       session.exitstatus == EXIT_INTERNALERROR or
       session.exitstatus == EXIT_USAGEERROR):
        return session.exitstatus

    # adjust the return value because py.test doesn't know
    # we run + collect tests
    if session.exitstatus == EXIT_NOTESTSCOLLECTED:
        if tests_collected == 0:
            return EXIT_NOTESTSCOLLECTED
        elif session.testsfailed:
            return EXIT_TESTSFAILED
        else:
            return EXIT_OK
    else:
        return session.exitstatus
