"""Minimal TEST guest supervisor; reachable only through localhost QEMU forwards."""

import http.server
import json
import os
import subprocess
import time

processes = {}


def start():
    env = dict(os.environ, PYTHONPATH="/native:/site")
    for name, args in (
        (
            "app",
            [
                "/usr/bin/python3.12",
                "-m",
                "tokoin_native.abci_server",
                "--genesis",
                "/app-genesis.json",
                "--db",
                "/app.sqlite",
                "--port",
                "26658",
            ],
        ),
        ("node", ["/bin/cometbft", "start", "--home", "/node"]),
    ):
        if name not in processes or processes[name].poll() is not None:
            processes[name] = subprocess.Popen(
                args, env=env, stdout=open("/" + name + ".log", "ab"), stderr=subprocess.STDOUT
            )
            if name == "app":
                time.sleep(0.3)


def stop():
    for name in ("node", "app"):
        p = processes.get(name)
        if p and p.poll() is None:
            p.terminate()
            p.wait(timeout=10)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if req["action"] == "clock":
                time.clock_settime(time.CLOCK_REALTIME, req["unix_time"])
            elif req["action"] == "start":
                start()
            elif req["action"] == "stop":
                stop()
            else:
                raise ValueError("unsupported action")
            result = {"unix_time": time.time(), "monotonic": time.monotonic()}
            self.send_response(200)
        except Exception as error:
            result = {"error": str(error)}
            self.send_response(500)
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def do_GET(self):
        if self.path == "/logs":
            result = {
                n: open("/" + n + ".log").read() if os.path.exists("/" + n + ".log") else ""
                for n in ("app", "node")
            }
        else:
            result = {
                "unix_time": time.time(),
                "monotonic": time.monotonic(),
                "pid": os.getpid(),
                "kernel": os.uname().release,
                "clock": time.get_clock_info("time").implementation,
                "ntp_running": False,
            }
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


def main():
    # This file must never expose a clock-changing supervisor on the host.
    if os.getpid() != 1 or "agora_vm_test=1" not in open("/proc/cmdline").read().split():
        raise RuntimeError("TEST guest supervisor requires PID 1 and dedicated kernel boot marker")
    http.server.HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()  # noqa: S104 - guest only


if __name__ == "__main__":
    main()
