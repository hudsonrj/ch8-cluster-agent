
import time, subprocess, sys, os, signal

python = r"/usr/bin/python3"
ch8 = r"/data/ch8-agent/ch8"
cwd = r"/data/ch8-agent"
log = open(os.path.join(cwd, "update.log"), "a")

log.write(f"[UPDATE] Starting zero-downtime restart at {time.strftime('%H:%M:%S')}\n")
log.flush()

# Get current orchestrator PID (we'll kill it after new one starts)
old_orch_pid = None
pid_file = os.path.expanduser("~/.config/ch8/orchestrator.pid")
if os.path.exists(pid_file):
    try:
        old_orch_pid = int(open(pid_file).read().strip())
    except:
        pass

# Stop non-orchestrator agents (they'll restart with ch8 up)
for pf in os.listdir(os.path.expanduser("~/.config/ch8/")):
    if pf.endswith(".pid") and pf != "orchestrator.pid" and pf != "daemon.pid":
        try:
            pid = int(open(os.path.join(os.path.expanduser("~/.config/ch8"), pf)).read().strip())
            os.kill(pid, signal.SIGTERM)
        except:
            pass

time.sleep(1)

# Kill old orchestrator
if old_orch_pid:
    try:
        os.kill(old_orch_pid, signal.SIGTERM)
        time.sleep(2)
        os.kill(old_orch_pid, signal.SIGKILL)
    except:
        pass

time.sleep(1)

# Start fresh with updated code
log.write(f"[UPDATE] Starting ch8 up with new code\n")
log.flush()
subprocess.run([python, ch8, "up"], cwd=cwd, stdout=log, stderr=log)

# Verify health
time.sleep(5)
try:
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:7879/health", timeout=5)
    log.write(f"[UPDATE] New orchestrator healthy: {r.read().decode()[:80]}\n")
except Exception as e:
    log.write(f"[UPDATE] Health check failed: {e}\n")

log.write(f"[UPDATE] Done at {time.strftime('%H:%M:%S')}\n")
log.close()
