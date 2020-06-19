# MIT License

# Copyright (c) 2020 Heraldo Lucena

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import os
import errno
import gc
import threading
import time
import subprocess
import tempfile
import secrets
import unittest
from unittest import mock
from pymutex import mutex

BASEDIR = os.path.dirname(__file__)

class SharedMutexTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mutex_filepath = maketempfilepath()
        return super().setUpClass()

    def setUp(self):
        self.recover = mock.Mock(return_value=True)
        self.mutex = mutex.SharedMutex(self.mutex_filepath, self.recover)

    def tearDown(self):
        os.remove(self.mutex_filepath)

    def _plus_one(self, counter, count):
        for _ in range(count):
            self.mutex.lock()
            counter.value += 1
            self.mutex.unlock()

    def _minus_one(self, counter, count):
        for _ in range(count):
            self.mutex.lock()
            counter.value -= 1
            self.mutex.unlock()

    @unittest.skip('none')
    def test_thread_sincronization_in_same_process(self):
        counter = Counter()
        t1 = threading.Thread(target=self._plus_one, args=(counter, 100_000))
        t2 = threading.Thread(target=self._minus_one, args=(counter, 100_000))
        self.mutex.lock()
        t1.start()
        time.sleep(0.01)
        t2.start()
        time.sleep(0.01)
        self.mutex.unlock()
        t1.join()
        t2.join()
        self.assertEqual(counter.value, 0)
        self.recover.assert_not_called()

    @unittest.skip('none')
    def test_thread_sincronization_across_processes(self):
        tmpfile = maketempfilepath()
        self.mutex.lock()
        p1 = subprocess.Popen(
            ['python', os.path.join(BASEDIR, '_process_sync_script.py'), self.mutex_filepath, tmpfile, str(100_000), '+'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8'
        )
        time.sleep(0.3)
        p2 = subprocess.Popen(
            ['python', os.path.join(BASEDIR, '_process_sync_script.py'), self.mutex_filepath, tmpfile, str(100_000), '-'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8'
        )
        time.sleep(0.3)
        self.mutex.unlock()
        e = p1.wait()
        if e != 0:
            p2.kill()
            self.fail('Test process exited with error:\n' + '\n'.join(p1.stderr.readlines()))
        e = p2.wait()
        if e != 0:
            self.fail('Test process exited with error:\n' + '\n'.join(p2.stderr.readlines()))
        self.assertEqual(p1.stdout.readline(), '0')
        self.assertEqual(p2.stdout.readline(), '0')

    @unittest.skip('none')
    def test_should_call_recover_shared_state_callback_when_a_thread_terminates_without_unlocking_the_mutex(self):
        t = threading.Thread(target=lambda: self.mutex.lock())
        t.start()
        t.join()
        self.mutex.lock()
        self.recover.assert_called_once_with()

    @unittest.skip('none')
    def test_should_raise_OSError_EDEADLOCK_when_relock(self):
        self.mutex.lock()
        try:
            self.mutex.lock()
            self.fail('Did not raise any exception')
        except OSError as e:
            self.assertEqual(e.errno, errno.EDEADLOCK, f'Raised [{e.errno} {os.strerror(e.errno)}] instead of EDEADLOCK.')

    @unittest.skip('none')
    def test_should_raise_PermissionError_when_unlock_not_owned_lock(self):
        with self.assertRaises(PermissionError):
            self.mutex.unlock()

    def test_should_not_cause_deadlock_when_the_mutex_while_locked_is_garbage_collected(self):
        self.mutex.lock()
        self.mutex = None
        gc.collect()
        self.setUp() # load the mutex
        t = threading.Thread(target=lambda: self.mutex.lock())
        t.start()
        t.join(mutex._MUTEX_LOCK_HEARTBEAT)
        self.assertFalse(t.is_alive(), 'Deadlock happened')

    def test_should_load_the_mutex_if_it_already_exists(self):
        mutex2 = mutex.SharedMutex(self.mutex_filepath, mock.Mock(return_value=True))
        self.mutex.lock()
        with self.assertRaises(OSError):
            mutex2.lock(blocking=False)

def maketempfilepath():
    for _ in range(100):
        file = os.path.join(tempfile.gettempdir(), 'pymutex_' + secrets.token_hex(8))
        if not os.path.isfile(file):
            return file
    raise RuntimeError("Could not make an unique path...")


class Counter:

    def __init__(self):
        self.value = 0


if __name__ == '__main__':
    unittest.main(verbosity=2)