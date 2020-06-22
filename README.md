# pymutex
POSIX's robust mutexes in Python that can be shared across processes.
The sharing is done by memory mapping a file that contains the mutex's state.
Mutex (mutual exclusion) is a sincronization primitive for concurrent tasks that allows one to
coordinate the concurrent access to shared resources. See [wikipedia page][1] about mutexes for more details.

The `pymutex.SharedMutex` implements the features that allows mutexes to be shared across processes, it is similar to named semaphores in a sense that its state is stored in a file of the filesystem and visible system-wide. When passing a `pathname` to its constructor, the SharedMutex will check whether that file already exists, if so it will try to load the stored mutex. If the file does not exists, it will be created in read-only mode, the SharedMutex instance that created the file is responsible for initializing a new mutex and storing it in that file. When other SharedMutex instances see the file already exists but is in read-only mode, they will pool the file and wait until it becomes writable.

## Requeriments
1. It was tested only in Python 3.7, probably it works in python 3.8, 3.6 and 3.5 too;
2. [libpthread][3], which comes by default in Linux systems.
   
    \* There are no external dependencies.

## Usage
`SharedMutex.lock(blocking, timeout)` locks/acquires the mutex, if the mutex is not available (other thread already acquired it), then the caller's thread blocks until the mutex becomes available. If a `timeout` is given (defaults to zero), the thread waits until `timeout` expires. If `blocking=False` is given (defaults to `True`), the call returns immediately, the returned value is `True` if the mutex was acquired, `False` otherwise.

`SharedMutex.unlock()` unlocks/releases the mutex, in effect it becomes available.<br>

`SharedMutex` uses a [logger][5] named `pymutex.SharedMutex` to log important events, this logger can be enabled with default configs by calling `pymutex.configure_default_logging()`. The default logger contains only one handler (StreamHandler) that logs to stdout.

### Example
The following code shows a classic example of data race. There are 2 threads that concurrently tries to
increment and decrement the counter's value. Python grants atomic operations on its data types, but it
won't try to coordinate the concurrent access to the counter's value, it is up to the application code.
The example below grants that the end counter's value will be zero by making sure that an increment
operation is followed by a decrement one (here the lock acquisition is done in a FIFO way, the first to ask will be the first to acquire):
```python
import threading
import time
import pymutex

class Counter:

    def __init__(self):
        self.value = 0

def increment_thread(mutex, counter, times):
    for _ in range(times):
        mutex.lock()
        counter.value += 1
        mutex.unlock()

def decrement_thread(mutex, counter, times):
    for _ in range(times):
        mutex.lock()
        counter.value -= 1
        mutex.unlock()

mutex = pymutex.SharedMutex('my_mutex_file')
counter = Counter()
t1 = threading.Thread(target=increment_thread, args=(mutex, counter, 100_000))
t2 = threading.Thread(target=decrement_thread, args=(mutex, counter, 100_000))

mutex.lock() # make the threads wait
t1.start()
t2.start()
time.sleep(0.1)
mutex.unlock() # let threads work
t1.join()
t2.join()

print(f"Value should be zero: {counter.value}")
```
Remove the `mutex.lock()` and `mutex.unlock()` from the `increment` and `decrement` loops to see what happens.

## Undefined behaviors
The POSIX's mutex configured with robustness and errorcheck type (internally identified as `PTHREAD_MUTEX_ROBUST_ERRORCHECK_NP` by pthread) is able to avoid several deadlock situations like 1) a thread holding the lock terminates without releasing it 2) a thread tries to lock an already owned lock 3) a thread tries to unlock a not owned lock, but it only works for valid mutexes. If a `SharedMutex` instance __owns the lock and is collected by the Python's garbage collector before the owner thread terminates__, all operations on __any__ instance of that mutex after that are undefined behavior. A [weakref finalizer][2] is registered for each instance of `SharedMutex` that notifies applications through logging when a mutex is left locked. Note that this problem will happen in any implementation since its due the fact that the mutex's pointer becomes invalid before the owner thread terminates, so when this thread finally terminates it will not be possible set the owner as dead in the mutex.

Since the `SharedMutex` is supposed to be shared across processes, the underlying pthread mutex will be never destoyed by calling `pthread_mutex_destroy`. The `SharedMutex` does not keeps track of the references to the same mutex, it just makes sure it will not leave the mutex in an invalid state. Internally all [pthread_mutex_destroy][4] does is just set the mutex type to an invalid value (-1), but before doing so it checks whether the mutex is robust, if it is and some other thread is waiting for this mutex, it returns `EBUSY` error. All other operations of `_timedlock`, `_trylock` and `_unlock` checks the mutex type to select the appropriate action. When the type can't be determined, `EINVAL` error is returned. But those checks are not done when initializing a mutex, __calling `pthread_mutex_init` in an already initialized shared mutex may cause undefined behaviors__.

The mutex's state is stored in a file which is memory mapped by processes that want to use them. Applications MUST ensure that all writes to that file will not make the mutex invalid. Ideally that file should be written only by `pthread_mutex_*` functions. The `SharedMutex` class gives write and read permissions only to the process's user where the mutex was initialized. This file MUST NOT persist more than one session, applications MUST remove the file when all threads interested in terminates. Internally pthread uses threads' ID and other volatile values, those values changes when the processes restart. __Operating an invalid mutex causes undefined behaviors__.


## Testing
```
git clone https://github.com/HMaker/pymutex.git
cd pymutex
PYTHONPATH=. python -m unittest -v tests
```
<br>
This work is licensed under MIT License, See LICENSE for more info.
<br>

[1]: https://en.wikipedia.org/wiki/Mutual_exclusion
[2]: https://docs.python.org/3.7/library/weakref.html#weakref.finalize
[3]: http://sourceware.org/git/?p=glibc.git;a=tree;f=nptl;hb=HEAD
[4]: http://sourceware.org/git/?p=glibc.git;a=blob;f=nptl/pthread_mutex_destroy.c;h=e2c9f8a39ffe81e046f370c34e86a3696bb431e9;hb=HEAD
[5]: https://docs.python.org/3/library/logging.html#logger-objects