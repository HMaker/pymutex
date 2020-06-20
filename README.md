# pymutex
POSIX's robust mutexes in Python that can be shared across processes.
The sharing is done by memory mapping a file that contains the mutex's state.
Mutex (mutual exclusion) is a sincronization primitive for concurrent tasks that allows one to
coordinate the concurrent access to shared resources. See [wikipedia page][1] about mutexes for more details.
## Usage
```python
import threading
import time
import pymutex

class Counter:

    def __init__(self):
        self.value = 0

def plus_one_thread(mutex, counter, times):
    for _ in range(times):
        mutex.lock()
        counter.value += 1
        mutex.unlock()

def minus_one_thread(mutex, counter, times):
    for _ in range(times):
        mutex.lock()
        counter.value -= 1
        mutex.unlock()

mutex = pymutex.SharedMutex('my_mutex_file')
counter = Counter()
t1 = threading.Thread(target=plus_one_thread, args=(mutex, counter, 100_000))
t2 = threading.Thread(target=plus_one_thread, args=(mutex, counter, 100_000))

mutex.lock() # make the threads wait
t1.start()
t2.start()
time.sleep(0.1)
mutex.unlock() # let threads work
t1.join()
t2.join()

print(f"Value should be zero: {counter.value}")
```

## Requeriments
1. It was tested only in Python 3.7, probably it works in python 3.8, 3.6 and 3.5 too;
2. `libpthread`, which comes by default in Linux systems.

There are no external dependencies.

## Testing
```
git clone https://github.com/HMaker/pymutex.git
cd pymutex
PYTHONPATH=. python -m unittest -v tests
```

[1]: https://en.wikipedia.org/wiki/Mutual_exclusion