# pytest-redis 
A pytest plugin that reads test paths from a redis queue.


## Usage
The plugin should be installed to the python import path with:

```
git clone https://github.com/sabidib/pytest-redis.git
cd pytest-redis
python setup.py install
```

The plugin can be launched with :

```
py.test -p pytest_redis --redis-host=<redis-host> --redis-port=<redis-port> --redis-list-key=<redis-list-key> [--redis-pop-type=<default RPOP>] 
```

This will connect to the a redis instance located at `<redist-host>:<redis-post>` and attempts to remove elements from the list given by the key `redis-list-key`. If `--redis-pop-type` is not set, then it will by default `RPOP` from the list. Valid values for `--redis-pop-type` are `RPOP, LPOP`.

Each element removed from the list should be a complete path to a test function, class, module or directory i.e `test/utils/test_strings.py::test_reverse` or `test/utils/test_strings`.

The plugin continues to pop elements off the list until the list is empty at which points all the tests are run.

## Testing

To run the tests, you must have a running redis host running:

```
python setup.py install
py.test -vv --redis-host=<redis-host> --redis-port=<redis-port> --redis-list-key=<redis-list-key> 
```
If the `<redis-list-key>` already has a list the test will prompt you to add `--force` option in order to empty the list and continue with the testing.



