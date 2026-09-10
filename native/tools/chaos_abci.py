"""Explicit TEST-only ABCI fault wrapper; production Application remains unmodified."""

import argparse
import json
import time
from pathlib import Path

from tokoin_native.abci_server import Application, Handler, Server, pb
from tokoin_native.core import MODE
from tokoin_native.store import Store


class ChaosApplication(Application):
    def __init__(self, store, control):
        super().__init__(store)
        if store.genesis["mode"] != MODE or not store.genesis["chain_id"].startswith(
            "tokoin-test-"
        ):
            raise ValueError("TEST genesis required")
        self.control = control

    def _handle(self, kind, req):
        faults = json.loads(self.control.read_text())
        if kind == "prepare_proposal" and faults.get("hold_proposal"):
            print(json.dumps({"event": "proposal_held", "height": req.height}), flush=True)
            deadline = time.monotonic() + 15
            while (
                json.loads(self.control.read_text()).get("hold_proposal")
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
        if kind == "prepare_proposal" and faults.get("invalid_proposal"):
            print(
                json.dumps({"event": "invalid_proposal_injected", "height": req.height}), flush=True
            )
            return pb.Response(
                prepare_proposal=pb.ResponsePrepareProposal(txs=[b"TEST_INVALID_JSON"])
            )
        result = super()._handle(kind, req)
        if (
            kind == "process_proposal"
            and result.process_proposal.status == pb.ResponseProcessProposal.REJECT
        ):
            print(json.dumps({"event": "proposal_rejected", "height": req.height}), flush=True)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genesis", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--control", type=Path, required=True)
    args = parser.parse_args()
    store = Store(args.db, json.loads(args.genesis.read_text()))
    with Server(("127.0.0.1", args.port), Handler) as server:
        server.application = ChaosApplication(store, args.control)
        server.serve_forever()


if __name__ == "__main__":
    main()
