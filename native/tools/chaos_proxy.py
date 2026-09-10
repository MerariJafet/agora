"""Loopback TCP edge faults. Loss closes a stream: it is NOT IP packet loss."""

import asyncio
import threading
from urllib.parse import urlparse


def require_loopback(endpoint):
    p = urlparse(endpoint)
    if p.scheme not in {"tcp", "http"} or p.hostname != "127.0.0.1" or not p.port:
        raise ValueError("Only explicit IPv4 loopback endpoints are authorized")
    return p.port


class EdgeProxy:
    def __init__(self, port, target):
        require_loopback(f"tcp://127.0.0.1:{port}")
        require_loopback(f"tcp://127.0.0.1:{target}")
        self.port, self.target = port, target
        self.enabled, self.delay, self.drop_every = True, 0, 0
        self.chunks, self.dropped, self.connections = 0, 0, set()

    def configure(self, enabled=True, delay=0, drop_every=0):
        self.enabled, self.delay, self.drop_every = enabled, delay, drop_every
        if not enabled:
            for writer in list(self.connections):
                writer.close()

    async def relay(self, reader, writer):
        while self.enabled:
            data = await reader.read(65536)
            if not data:
                break
            self.chunks += 1
            if self.drop_every and self.chunks % self.drop_every == 0:
                self.dropped += 1
                break
            if self.delay:
                await asyncio.sleep(self.delay)
            if not self.enabled:
                break
            writer.write(data)
            await writer.drain()

    async def accept(self, reader, writer):
        remote = None
        try:
            if not self.enabled:
                return
            upstream, remote = await asyncio.open_connection("127.0.0.1", self.target)
            self.connections.update((writer, remote))
            tasks = [
                asyncio.create_task(self.relay(reader, remote)),
                asyncio.create_task(self.relay(upstream, writer)),
            ]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, ConnectionError):
            pass
        finally:
            for stream in (writer, remote):
                if stream:
                    stream.close()
                    self.connections.discard(stream)


class ProxyMesh:
    def __init__(self, base, targets):
        self.edges = {
            (i, j): EdgeProxy(base + i * 4 + j, targets[j])
            for i in range(4)
            for j in range(4)
            if i != j
        }
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.servers = asyncio.run_coroutine_threadsafe(self.start(), self.loop).result(10)

    async def start(self):
        return [
            await asyncio.start_server(e.accept, "127.0.0.1", e.port) for e in self.edges.values()
        ]

    def faults(self, groups=None, delay=0, drop_every=0):
        async def apply():
            for (i, j), edge in self.edges.items():
                enabled = groups is None or any(i in g and j in g for g in groups)
                edge.configure(enabled, delay, drop_every)

        asyncio.run_coroutine_threadsafe(apply(), self.loop).result(10)

    def close(self):
        self.faults(groups=[])

        async def stop():
            for server in self.servers:
                server.close()
                await server.wait_closed()

        asyncio.run_coroutine_threadsafe(stop(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
