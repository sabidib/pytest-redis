"""Tests the pytest-redis with a running redis instance.

Tests should be launched from the root directory with:
py.test --redis-port=<port> --redis-host=<host> --redis-list-key=<list_to_use>

"""
import multiprocessing
from multiprocessing import Pipe
import os.path

from _pytest.main import (EXIT_OK,
                          EXIT_NOTESTSCOLLECTED,
                          EXIT_TESTSFAILED,
                          EXIT_INTERRUPTED,
                          EXIT_USAGEERROR)


def default_pytest_redis_args():
    """Return default options for each pytest execution."""
    return ['-v', '-p', 'pytest_redis']


def get_option_array(option_dict):
    """Return cmdline options for a dict in '--key=val' form."""
    return ["--{}={}".format(k, v) for k, v in option_dict.items()]


def create_test_file(testdir, filename, text):
    """Create test file with the given name and text contents."""
    the_kwargs = {
        filename: text
    }
    ext = ""
    try:
        ext = filename.split(".")[-1]
    except:
        pass

    testdir.makefile(ext, **the_kwargs)


def get_standard_args(option_dict):
    """Return standard pytest redis_args combinbed with option dict."""
    return default_pytest_redis_args() + get_option_array(option_dict)


def create_test_dir(testdir, dirname):
    """Create test file with the given name and text contents."""
    testdir.mkdir(dirname)


def setup_multiple_consumer_processes(testdir, py_test_args, num_threads):
    """Return multiple threads that will run pytest with the given args."""
    def run_consumer(testdir, test_args, pipe_to_parent):
        result = testdir.runpytest(*test_args)
        pipe_to_parent.send([result.ret, result.outlines])

    ret = []
    for i in range(num_threads):
        parent_pipe_end, child_pipe_conn = Pipe()
        process = multiprocessing.Process(target=run_consumer,
                                          args=[testdir,
                                                py_test_args,
                                                child_pipe_conn])
        ret.append((process, parent_pipe_end))
    return ret



def test_external_arguments(testdir, redis_connection, redis_args):
    """Ensure that the plugin doesn't intefere with other plugins."""
    test_file_name = "test_external_arguments.py"
    create_test_file(testdir, test_file_name, """
        def test_run_should_run():
            assert True
    """)
    redis_connection.lpush(redis_args['redis-list-key'],
                           test_file_name + "::test_run_should_run")

    junitxml_filename = "pytest.xml"
    py_test_args = get_standard_args(redis_args) + \
        ['--junitxml=' + junitxml_filename]

    junitxml_path = str(testdir.tmpdir) + "/" + junitxml_filename

    result = testdir.runpytest(*py_test_args)
    assert os.path.exists(junitxml_path)
    assert result.ret == EXIT_OK


def test_multiple_consumers(testdir, redis_connection, redis_args):
    """Pull tests from multiple test runs simultaneously."""
    test_file_name = "test_multiple_consumers.py"

    create_test_file(testdir, test_file_name, """
        def test_multiple_consumers():
            assert True
    """)
    for i in range(100):
        redis_connection.lpush(redis_args['redis-list-key'],
                               test_file_name + "::test_multiple_consumers")

    py_test_args = get_standard_args(redis_args)

    processes = setup_multiple_consumer_processes(testdir, py_test_args, 5)

    for proc in processes:
        proc[0].start()

    for proc in processes:
        proc[0].join()
        exit_result = proc[1].recv()[0]

        assert exit_result == EXIT_OK

    assert redis_connection.llen(redis_args['redis-list-key']) == 0


def test_no_consumption_of_item(testdir, redis_args):
    """Make sure that we don't run tests when the list is empty."""
    test_file_name = "test_not_used"
    create_test_file(testdir, test_file_name, """
        def test_run_should_run():
            assert True
    """)
    py_test_args = get_standard_args(redis_args)
    result = testdir.runpytest(*py_test_args)
    assert result.ret == EXIT_NOTESTSCOLLECTED


def test_non_existent_test_name(testdir, redis_connection, redis_args):
    """Entire test should fail if a non-existent test is specfied."""
    test_file_name = "test_name.py"
    create_test_file(testdir, test_file_name, """
        def test_name_dne():
            assert True
    """)

    redis_connection.lpush(redis_args['redis-list-key'],
                           test_file_name + "::test_wrong_name")

    py_test_args = get_standard_args(redis_args)
    result = testdir.runpytest(*py_test_args)
    assert result.ret == EXIT_USAGEERROR


def test_module_test_name(testdir, redis_connection, redis_args):
    """Test path as a module name."""
    module_1_name = "test_module_1"
    module_1_test_filename = "test_module_1_file.py"
    module_1_test_filename_contents = """
        def test_does_exist():
            assert True
        def test_random_test():
            assert True
    """
    module_2_name = "test_module_2"
    module_2_test_filename = "test_module_2_file.py"
    module_2_test_filename_contents = """
        def test_does_exist_2():
            assert True
        def test_random_test_2():
            assert True
    """
    create_test_dir(testdir, module_1_name)
    create_test_file(testdir, module_1_name + "/" + module_1_test_filename,
                     module_1_test_filename_contents)
    create_test_dir(testdir, module_2_name)
    create_test_file(testdir, module_2_name + "/" + module_2_test_filename,
                     module_2_test_filename_contents)
    py_test_args = get_standard_args(redis_args)

    for module in [module_1_name, module_2_name]:
        redis_connection.lpush(redis_args['redis-list-key'], module)
        result = testdir.runpytest(*py_test_args)
        result.stdout.fnmatch_lines([
            "*" + module + "*PASSED",
            "*" + module + "*PASSED"
        ])
        assert result.ret == EXIT_OK


def test_lr_pop_from_list(testdir, redis_connection, redis_args):
    """Specify rpop from redis list with --redis-pop-type=rpop."""
    test_file_name = "test_lr_pop_from_list.py"

    create_test_file(testdir, test_file_name, """
        def test_run0():
            assert False

        def test_run1():
            assert True
    """)

    py_test_args = get_standard_args(redis_args)

    pop_options = ['rpop', 'lpop', 'invalid']

    for pop_dir in pop_options:
        cur_args = py_test_args + ["--redis-pop-type=" + pop_dir]
        # populate redis list with tests
        for ind in range(2):
            redis_connection.lpush(redis_args['redis-list-key'],
                                   test_file_name + "::test_run" + str(ind))

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
