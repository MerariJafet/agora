"""CometBFT 0.38 ABCI2 socket adapter, loopback-only isolated TEST networks."""

import argparse
import json
import socketserver
import threading
from pathlib import Path
from typing import cast

from .core import Invalid, canonical, digest, require, transition
from .store import Store
from .vendor.tendermint.abci import types_pb2 as pb

MAX_FRAME = 2_000_000


def decode(raw):
    require(len(raw) <= 64_000, "tx bytes limit")
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise Invalid("invalid or too deeply nested JSON") from error
    require(canonical(value) == raw, "noncanonical encoding")
    return value


class Application:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()

    def handle(self, request):
        kind = request.WhichOneof("value")
        with self.lock:
            return self._handle(kind, getattr(request, kind))

    def _handle(self, kind, req):
        store = self.store
        state, genesis = store.state, store.genesis
        response = pb.Response()
        out = getattr(response, kind)
        out.SetInParent()
        if kind == "echo":
            out.message = req.message
        elif kind == "info":
            out.data = "TOKOIN TEST native ABCI; economic recognition disabled"
            out.version, out.app_version = "0.2.0", 3
            out.last_block_height = state["height"]
            out.last_block_app_hash = bytes.fromhex(digest("tokoin.state.v2", state))
        elif kind == "init_chain":
            require(req.chain_id == genesis["chain_id"], "chain ID mismatch")
            require(json.loads(req.app_state_bytes) == genesis, "app genesis mismatch")
            require(req.initial_height in (0, 1), "unsupported initial height")
            validators = sorted(
                [{"public_key": v.pub_key.ed25519.hex(), "power": v.power} for v in req.validators],
                key=lambda v: v["public_key"],
            )
            require(
                len(validators) >= 4 and validators == genesis["consensus_validators"],
                "consensus validator set mismatch",
            )
            require(req.time.seconds == genesis["timestamp"], "genesis time mismatch")
            out.app_hash = bytes.fromhex(digest("tokoin.state.v2", state))
        elif kind == "check_tx":
            try:
                transition(genesis, state, [decode(req.tx)], state["height"] + 1, state["time"])
                out.code = 0
            except (Invalid, ValueError, KeyError, TypeError) as error:
                out.code, out.log = 1, str(error)[:200]
        elif kind == "prepare_proposal":
            store.fault("before_prepare_proposal")
            selected: list[bytes] = []
            size = 0
            for raw in req.txs:
                if size + len(raw) > min(req.max_tx_bytes, 1_000_000):
                    continue
                try:
                    candidate = [decode(tx) for tx in [*selected, raw]]
                    transition(genesis, state, candidate, req.height, req.time.seconds)
                except (Invalid, ValueError, KeyError, TypeError):
                    continue
                selected.append(raw)
                size += len(raw)
            out.txs.extend(selected)
            store.fault("after_prepare_proposal")
        elif kind == "process_proposal":
            store.fault("before_process_proposal")
            try:
                transition(
                    genesis, state, [decode(tx) for tx in req.txs], req.height, req.time.seconds
                )
                out.status = pb.ResponseProcessProposal.ACCEPT
            except (Invalid, ValueError, KeyError, TypeError):
                out.status = pb.ResponseProcessProposal.REJECT
            store.fault("after_process_proposal")
        elif kind == "finalize_block":
            updated = store.prepare([decode(tx) for tx in req.txs], req.height, req.time.seconds)
            out.tx_results.extend(pb.ExecTxResult(code=0) for _ in req.txs)
            out.app_hash = bytes.fromhex(digest("tokoin.state.v2", updated))
        elif kind == "commit":
            store.commit()
            out.retain_height = 0  # Retain full block history for genesis replay.
        elif kind == "query":
            out.height = state["height"]
            if req.prove or req.height not in (0, state["height"]):
                out.code, out.log = 1, "historical/proof query unsupported; replay blocks to verify"
            elif req.path == "/state":
                out.value = canonical(state)
            elif req.path == "/manifest":
                out.value = canonical(store.manifest())
            elif req.path == "/explorer":
                out.value = canonical(store.export())
            else:
                out.code, out.log = 1, "unknown query"
        elif kind == "offer_snapshot":
            out.result = pb.ResponseOfferSnapshot.REJECT
        elif kind == "apply_snapshot_chunk":
            out.result = pb.ResponseApplySnapshotChunk.REJECT_SNAPSHOT
        elif kind == "verify_vote_extension":
            out.status = pb.ResponseVerifyVoteExtension.REJECT
        elif kind not in ("flush", "list_snapshots", "load_snapshot_chunk", "extend_vote"):
            raise Invalid("unsupported ABCI request")
        return response


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def read_frame(stream):
    size = 0
    for i in range(5):
        byte = read_exact(stream, 1)[0]
        size |= (byte & 127) << (7 * i)
        if not byte & 128:
            require(size <= MAX_FRAME, "ABCI frame too large")
            return read_exact(stream, size)
    raise Invalid("invalid ABCI length prefix")


def frame(raw):
    prefix = bytearray()
    size = len(raw)
    while size >= 128:
        prefix.append((size & 127) | 128)
        size >>= 7
    return bytes(prefix) + bytes([size]) + raw


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            while True:
                request = pb.Request.FromString(read_frame(self.rfile))
                try:
                    response = cast(Server, self.server).application.handle(request)
                except (Invalid, ValueError, KeyError, TypeError) as error:
                    response = pb.Response(exception=pb.ResponseException(error=str(error)[:200]))
                self.wfile.write(frame(response.SerializeToString()))
                self.wfile.flush()
        except (EOFError, ConnectionError, Invalid):
            return


class Server(socketserver.ThreadingTCPServer):
    application: Application
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--genesis", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    store = Store(args.db, json.loads(args.genesis.read_text()))
    with Server(("127.0.0.1", args.port), Handler) as server:
        server.application = Application(store)
        server.serve_forever()


if __name__ == "__main__":
    main()
