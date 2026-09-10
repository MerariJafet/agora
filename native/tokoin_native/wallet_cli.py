"""Offline TEST wallet CLI. Passwords are interactive; transactions are never broadcast."""

import argparse
import getpass
import json
import os
import stat
import sys
import warnings
from pathlib import Path

from .core import Invalid, address, canonical, digest, initial_state, require
from .wallet_file import _atomic_write, backup_wallet, create_wallet, load_wallet, restore_wallet

MAX_JSON_BYTES = 1_000_000


def _read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), "regular JSON file required")
        raw = source.read(MAX_JSON_BYTES + 1)
    require(len(raw) <= MAX_JSON_BYTES, "JSON input exceeds size limit")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except RecursionError:
        raise Invalid("JSON nesting exceeds parser limits") from None
    canonical(value)
    return value


def _password(confirm=False):
    # getpass otherwise falls back to an echoed stdin password on some terminals.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Wallet password: ")
        if confirm:
            require(password == getpass.getpass("Repeat wallet password: "),
                    "password confirmation mismatch")
    return password.encode("utf-8")


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid CLI arguments; consult --help.\n")


def _parser():
    parser = SafeParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "address", "sign", "backup", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--genesis", type=Path, required=True)
        command.add_argument("--wallet", type=Path, required=True)
        if name in ("backup", "restore"):
            command.add_argument("--destination", type=Path, required=True)
        if name == "sign":
            command.add_argument("--nonce", type=int, required=True)
            command.add_argument("--kind", choices=["transfer"], required=True)
            command.add_argument("--payload", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        genesis = _read_json(args.genesis)
        initial_state(genesis)  # Reject partial, incompatible, or economic/non-TEST genesis.
        chain_id = genesis["chain_id"]
        genesis_hash = digest("tokoin.genesis.v2", genesis)
        password = _password(confirm=args.command == "create")
        if args.command == "create":
            wallet = create_wallet(args.wallet, password, chain_id, genesis_hash)
            public_key = wallet.public_key
        elif args.command in ("backup", "restore"):
            action = backup_wallet if args.command == "backup" else restore_wallet
            public_key = action(args.wallet, args.destination, password, chain_id, genesis_hash)
        else:
            wallet = load_wallet(args.wallet, password, chain_id, genesis_hash)
            public_key = wallet.public_key
        identity = {"mode": genesis["mode"], "chain_id": chain_id,
                    "genesis_hash": genesis_hash, "address": address(public_key)}
        if args.command == "sign":
            payload = _read_json(args.payload)
            require(type(payload) is dict and set(payload) == {"to", "amount"},
                    "transfer requires recipient and integer amount")
            from .core import integer, valid_address

            valid_address(payload["to"])
            integer(payload["amount"], 1)
            integer(args.nonce, 1)
            # Identity is displayed before signing; no secret or plaintext key is printed.
            print(json.dumps(identity | {"nonce": args.nonce, "kind": args.kind,
                                         "to": payload["to"], "amount_units": payload["amount"]}),
                  file=sys.stderr, flush=True)
            tx = wallet.sign_transaction(genesis, args.nonce, args.kind, payload)
            _atomic_write(args.output, canonical(tx) + b"\n")
            identity["signed_transaction_file"] = str(args.output)
            identity["broadcast"] = False
        elif args.command in ("backup", "restore"):
            identity["destination"] = str(args.destination)
        print(json.dumps(identity, sort_keys=True))
        return 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, getpass.GetPassWarning, EOFError):
        # Do not render potentially sensitive contents or crypto exception internals.
        print("Wallet operation rejected; check network, input, password and destination.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
