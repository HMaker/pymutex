# pymutex
POSIX's robust mutexes in Python that can be shared across processes.
The sharing is done by memory mapping a file that contains the mutex's state.
Mutex (mutual exclusion) is a sincronization primitive for concurrent tasks that allows one to
coordinate the concurrent access to shared resources. See [wikipedia page][1] about mutexes for more details.

The `pymutex.SharedMutex` implements the features that allows mutexes to be shared across processes, it is similar to named semaphores in a sense that its state is stored in a file of the filesystem and visible system-wide. When passing a `pathname` to its constructor, the SharedMutex will check whether that file already exists, if so it will try to load the stored mutex. If the file does not exists, it will be created in read-only mode, the SharedMutex instance that created the file is responsible for initializing a new mutex and storing it in that file. When other SharedMutex instances see the file already exists but is in read-only mode, they will pool the file and wait until it becomes writable.

## Usage
The following code shows a classic example of data races. There are 2 threads that concurrently tries to
increment and decrement the counter's value. Python grants atomic operations on its data types, but it
won't try to coordinate the concurrent access to the counter's value, it is up to the application code.
The example below grants that the end counter's value will be zero by making sure that an increment
operation is followed by a decrement one.
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

## Requeriments
1. It was tested only in Python 3.7, probably it works in python 3.8, 3.6 and 3.5 too;
2. `libpthread`, which comes by default in Linux systems.

There are no external dependencies.

## Known deadlock situations
The POSIX's mutex configured with robustness and errorcheck type is able to avoids several deadlock situations like 1) a thread holding the lock terminates without releasing it 2) a thread tries to lock an already owned lock 3) a thread tries to unlock a not owned lock, but it only works with valid mutexes. If a mutex is locked and collected by the Python's garbage collector, all operations on the mutex after that are undefined behavior. To avoid that, a weakref finalizer is registered for each instance of `SharedMutex` that makes sure the mutex is not locked when garbage collected. Applications MUST follow the rules that allows those finalizers to work, see [weakref.finalize][2] for full documentation.

Since the `SharedMutex` is supposed to be shared across processes, the underlying pthread mutex will be never destoyed by calling `pthread_mutex_destroy`. The `SharedMutex` does not keeps track of the references to the same mutex, it just makes sure it will not leave the mutex in an invalid state. Applications MUST ensure that the mutex is not destroyed, if so, they MUST notify all threads waiting for the mutex. Operating a destroyed mutex is undefined behavior.

The mutex's state is stored in a file which is memory mapped by processes that want to use them. Applications MUST ensure that all writes to that file will not make the mutex invalid. Ideally that file should be written only by `pthread_mutex_*` functions. The `SharedMutex` class gives write and read permissions only to the process's user where the mutex was initialized.


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