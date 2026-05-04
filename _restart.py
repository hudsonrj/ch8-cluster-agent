
import time, subprocess, sys, os
time.sleep(3)
python = r"/usr/bin/python3"
ch8 = r"/data/ch8-agent/ch8"
cwd = r"/data/ch8-agent"
log = open(os.path.join(cwd, "update.log"), "a")
# Stop everything
subprocess.run([python, ch8, "down"], cwd=cwd, stdout=log, stderr=log)
time.sleep(2)
# Start fresh
subprocess.run([python, ch8, "up"], cwd=cwd, stdout=log, stderr=log)
log.close()
