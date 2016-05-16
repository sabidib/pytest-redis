"""pytest-redis queue plugin implementation."""
import sys
from _pytest.terminal import TerminalReporter
import _pytest.runner
import redis
from _pytest.main import NoMatch


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


def pytest_collection(session, genitems=True):
    """We hook into the collection call and do the collection ourselves."""
    hook = session.config.hook
    try:
        items = perform_collect_and_run(session)
    finally:
        hook.pytest_collection_finish(session=session)
    session.testscollected = len(items)
    return items


def perform_collect_and_run(session):
    """Collect and run tests streaming from the redis queue."""
    # This mimics the internal pytest collect loop, but shortened
    # while running tests as soon as they are found.
    session._initialpaths = set()
    session._initialparts = []
    session._notfound = []
    session.items = []
    redis_list = redis_test_generator(session.config, session.config.args)

    for arg in redis_list:
        parts = session._parsearg(arg)
        session._initialpaths.add(parts[0])
        arg = "::".join(map(str, parts))
        session.trace("processing argument", arg)
        session.trace.root.indent += 1
        try:
            for x in session._collect(arg):
                items = session.genitems(x)
                for item in items:
                    _pytest.runner.pytest_runtest_protocol(item, None)
                    session.items.append(item)
        except NoMatch:
            # we are inside a make_report hook so
            # we cannot directly pass through the exception
            session._notfound.append((arg, sys.exc_info()[1]))

        session.trace.root.indent -= 1
    return session.items


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

    while val is not None:
        yield val
        val = retrieve_test_from_redis(r_client,
                                       redis_list_key,
                                       redis_pop_type)


def pytest_runtest_protocol(item, nextitem):
    """Called when an item is run. Returning true stops the hook chain."""
    return True
