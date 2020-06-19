import sys
import time
import ctypes
import mmap
import os
from pymutex import mutex

mutex_file = sys.argv[1]
tmp_mmap_file = sys.argv[2]
repetitions = int(sys.argv[3])
if sys.argv[4] == '+':
    plus = True
elif sys.argv[4] == '-':
    plus = False
else:
    raise ValueError("Invalid op sign")

try:
    fd = os.open(tmp_mmap_file, os.O_CREAT | os.O_EXCL | os.O_TRUNC | os.O_RDWR)
    assert os.write(fd, b'\x00' * 8) == 8
except FileExistsError:
    fd = os.open(tmp_mmap_file, os.O_RDWR)

buf = mmap.mmap(fd, 0, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
counter = ctypes.c_int.from_buffer(buf)
my_mutex = mutex.SharedMutex(mutex_file, lambda: True)

if plus:
    for _ in range(repetitions):
        my_mutex.lock()
        counter.value += 1
        my_mutex.unlock()
else:
    for _ in range(repetitions):
        my_mutex.lock()
        counter.value -= 1
        my_mutex.unlock()

time.sleep(0.1)
try:
    os.remove(tmp_mmap_file)
except FileNotFoundError:
    pass
print(counter.value, end='')
os.close(fd)
counter = None
buf.close()
