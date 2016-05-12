"""Tests the pytest-redis with a running redis instance.

Tests should be launched from the root directory with:
py.test --redis-port=<port> --redis-host=<host> --redis-list-key=<list_to_use>

"""
# Exit value when everything is okay
from _pytest.main import EXIT_OK
# Exit value when no tests are collected
from _pytest.main import EXIT_NOTESTSCOLLECTED
# Exit value whenever a single test fails
from _pytest.main import EXIT_TESTSFAILED
# Exit value when an exception is thrown by parser or KeyboardInterrupt
from _pytest.main import EXIT_INTERRUPTED


def default_pytest_redis_args():
    """Return default options for each pytest execution."""
    return ['-v', '-p', 'pytest_redis']


def get_option_array(option_dict):
    """Return cmdline options for a dict in '--key=val' form."""
    return ["--{}={}".format(k, v) for k, v in option_dict.items()]


def test_external_arguments(testdir, redis_connection, redis_args):
    """Ensure that the plugin doesn't intefere with other plugins."""
    import os.path
    tmp_test_filename = "test_external_arguments.py"
    testdir.makepyfile("""
        def test_run_should_run():
            assert True
    """)
    redis_connection.lpush(redis_args['redis-list-key'],
                           tmp_test_filename + "::test_run_should_run")

    junitxml_filename = "pytest.xml"
    py_test_args = default_pytest_redis_args() + \
        get_option_array(redis_args) + \
        ['--junitxml=' + junitxml_filename]

    junitxml_path = str(testdir.tmpdir) + "/" + junitxml_filename

    result = testdir.runpytest(*py_test_args)
    assert os.path.exists(junitxml_path)
    assert result.ret == EXIT_OK

def test_no_consumption_of_item(testdir, redis_args):
    """Make sure that we don't run tests when the list is empty."""
    testdir.makepyfile("""
        def test_run_should_run():
            assert True
    """)
    py_test_args = default_pytest_redis_args() + get_option_array(redis_args)

    result = testdir.runpytest(*py_test_args)
    assert result.ret == EXIT_NOTESTSCOLLECTED


def test_lr_pop_from_list(testdir, redis_connection, redis_args):
    """Specify rpop from redis list with --redis-pop-type=rpop."""
    tmp_test_filename = "test_lr_pop_from_list.py"

    testdir.makepyfile("""
        def test_run0():
            assert False

        def test_run1():
            assert True
    """)

    py_test_args = default_pytest_redis_args() + get_option_array(redis_args)

    pop_options = ['rpop', 'lpop', 'invalid']

    for pop_dir in pop_options:
        cur_args = py_test_args + ["--redis-pop-type=" + pop_dir]
        # populate redis list with tests
        for ind in range(2):
            redis_connection.lpush(redis_args['redis-list-key'],
                                   tmp_test_filename + "::test_run" + str(ind))

        result = testdir.runpytest(*cur_args)
        if pop_dir == 'rpop':
            result.stdout.fnmatch_lines([
                "*::test_run0 FAILED",
                "*::test_run1 PASSED"
            ])
            assert result.ret == EXIT_TESTSFAILED
        elif pop_dir == 'lpop':
            result.stdout.fnmatch_lines([
                "*::test_run1 PASSED",
                "*::test_run0 FAILED"
            ])
            assert result.ret == EXIT_TESTSFAILED
        elif pop_dir == 'invalid':
            # Clean up redis list because we have an invalid cmd line opt
            redis_connection.rpop(redis_args['redis-list-key'])
            redis_connection.rpop(redis_args['redis-list-key'])
            assert result.ret == EXIT_INTERRUPTED
