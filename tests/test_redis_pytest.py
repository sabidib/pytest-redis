"""Tests the pytest-redis with a running redis instance.

Tests should be launched from the root directory with:
py.test  --redis-port=<port> --redis-host=<host> --redis-list-key=<list_to_use>

"""


def test_consumption_of_item(testdir, redis_args, redis_connection):
    """Make sure that we can consume multiple items."""
    [redis_connection.lpush(redis_args['redis-list-key'],
                            "test_consumption_of_item.py::test_run" + str(i))
        for i in range(5)]

    # create a temporary pytest test module
    testdir.makepyfile("""
        def test_run0():
            assert True

        def test_run1():
            assert True

        def test_run2():
            assert True

        def test_run3():
            assert True

        def test_run4():
            assert True

        def test_run5():
            assert True
    """)

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '-v',
        '-p',
        'pytest_redis',
        *["--" + str(key) + "=" + str(val) for key, val in redis_args.items()]
    )

    result.stdout.fnmatch_lines_random([
        "*::test_run4 PASSED",
        "*::test_run3 PASSED",
        "*::test_run2 PASSED",
        "*::test_run1 PASSED",
        "*::test_run0 PASSED"
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_no_consumption_of_item(testdir, redis_args):
    """Make sure that we can consume multiple items."""
    # create a temporary pytest test module
    testdir.makepyfile("""
        def test_run_should_run():
            assert True
    """)

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '-v',
        '-p',
        'pytest_redis',
        *["--" + str(key) + "=" + str(val) for key, val in redis_args.items()]
    )

    result.stdout.fnmatch_lines_random([
        "*No items in redis queue*",
        "*::test_run_should_run PASSED"
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_rpop_from_queue(testdir, redis_connection, redis_args):
    """Specify rpop from redis queue with --redis-pop-type=rpop works."""
    [redis_connection.lpush(redis_args['redis-list-key'],
                            "test_rpop_from_queue.py::test_run" + str(i))
        for i in range(2)]
    # create a temporary pytest test module
    testdir.makepyfile("""
        def test_run0():
            assert True

        def test_run1():
            assert True
    """)

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '-v',
        '-p',
        'pytest_redis',
        '--redis-pop-type=rpop',
        *["--" + str(key) + "=" + str(val) for key, val in redis_args.items()]
    )

    # The order of the line match indicates if it was rpop-ed correctly
    result.stdout.fnmatch_lines([
        "*::test_run0 PASSED",
        "*::test_run1 PASSED"
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_lpop_from_queue(testdir, redis_connection, redis_args):
    """Specify rpop from redis queue with --redis-pop-type=rpop works."""
    [redis_connection.lpush(redis_args['redis-list-key'],
                            "test_lpop_from_queue.py::test_run" + str(i))
        for i in range(2)]
    # create a temporary pytest test module
    testdir.makepyfile("""
        def test_run0():
            assert True

        def test_run1():
            assert True
    """)

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '-v',
        '-p',
        'pytest_redis',
        '--redis-pop-type=lpop',
        *["--" + str(key) + "=" + str(val) for key, val in redis_args.items()]
    )
    # The order of the line match indicates if it was lpop-ed correctly
    result.stdout.fnmatch_lines([
        "*::test_run1 PASSED",
        "*::test_run0 PASSED"
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0



