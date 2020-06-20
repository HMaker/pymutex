# MIT License

# Copyright (c) 2020 HMaker

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
import queue
import time
import subprocess
import tempfile
import secrets
import unittest
import logging
import warnings
from unittest import mock
from pymutex import mutex


BASEDIR = os.path.dirname(__file__)


class SharedMutexTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        mutex.configure_default_logging()
        cls.logger = logging.getLogger('pymutex')
        cls.logger.setLevel(logging.CRITICAL + 1) # turn off logging
        cls.mutex_filepath = make_temp_pathname()
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

    def test_thread_sincronization_across_processes(self):
        warnings.simplefilter("ignore", ResourceWarning) # ignore open file descriptors warning
        tmpfile = make_temp_pathname()
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

    def test_should_call_recover_shared_state_callback_when_a_thread_terminates_without_unlocking_the_mutex(self):
        t = threading.Thread(target=lambda: self.mutex.lock()) # make a deadlock
        t.start()
        t.join()
        self.mutex.lock() # try to lock a deadlock
        self.recover.assert_called_once_with()

    def _assert_deadlock_detection(self, mutex):
        try:
            mutex.lock()
            self.fail('deadlock not detected')
        except OSError as e:
            self.assertEqual(e.errno, errno.EDEADLOCK, f'Raised [{e.errno}: {os.strerror(e.errno)}] instead of EDEADLOCK.')

    def test_should_raise_OSError_EDEADLOCK_when_relock(self):
        self.mutex.lock()
        self._assert_deadlock_detection(self.mutex)

    def test_should_load_the_mutex_if_it_already_exists(self):
        mutex2 = mutex.SharedMutex(self.mutex_filepath, mock.Mock(return_value=True))
        self.mutex.lock()
        # if mutex2 == mutex, then deadlock will be detected
        self._assert_deadlock_detection(mutex2)

    def test_should_raise_PermissionError_when_unlock_not_owned_lock(self):
        with self.assertRaises(PermissionError):
            self.mutex.unlock()

    def test_should_not_cause_deadlock_when_the_mutex_while_locked_is_garbage_collected(self):
        with logger_level(self.logger, logging.DEBUG):
            print('')
            self.mutex.lock()
            self.mutex = None # The mutex was left locked
            gc.collect()
            self.setUp() # load the existing mutex
            locked = queue.Queue(maxsize=1)
            def trylock(locked):
                locked.put(self.mutex.lock())
            t = threading.Thread(target=trylock, args=(locked,))
            t.start()
        print("... Test result: ", end='', flush=True)
        try:
            result = locked.get(timeout=3)
            self.assertIsInstance(result, bool)
            self.assertTrue(result, 'Deadlock happened, could not lock the mutex.')
        except queue.Empty:
            self.fail('Deadlock happened, use Ctrl + C to exit.')

    def test_causes_deadlock_when_the_mutex_is_locked_and_its_finalizer_is_not_ran(self):
        self.mutex.lock()
        self.mutex._finalizer.detach() # remove the finalizer, the cleanup will not be done
        self.mutex = None
        gc.collect()
        self.setUp() # load the existing mutex
        locked = queue.Queue(maxsize=1)
        def trylock(locked):
            locked.put(self.mutex.lock(blocking=False))
        t = threading.Thread(target=trylock, args=(locked,))
        t.start()
        result = locked.get()
        self.assertIsInstance(result, bool)
        self.assertFalse(result, 'Deadlock did not happen, maybe the bug does not exists anymore?')


def make_temp_pathname():
    for _ in range(100):
        pathname = os.path.join(tempfile.gettempdir(), 'pymutex_' + secrets.token_hex(8))
        if not os.path.isfile(pathname):
            return pathname
    raise RuntimeError("Could not make an unique pathname...")

class logger_level:

    def __init__(self, logger: logging.Logger, level):
        self.logger = logger
        self.level = level

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.level)
        return self.logger

    def __exit__(self, *args):
        self.logger.setLevel(self.old_level)

class Counter:

    def __init__(self):
        self.value = 0


if __name__ == '__main__':
    unittest.main(verbosity=2)
