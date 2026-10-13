"""
id_generator.py - Automatic unique node_id generator for the Live Node Agent.

Each node gets a persistent identity derived from its hostname and a UUID4 hash.
The identity is saved to a local file (.node_id or .node_id_<suffix>) so the
node retains the same ID across restarts.

The optional *suffix* parameter lets you run multiple simulated agents on the
same machine without them sharing an identity file.
"""

import os
import uuid
import socket
import re

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _id_file_path(suffix: str = "") -> str:
    fname = ".node_id" if not suffix else f".node_id_{suffix}"
    return os.path.join(_AGENT_DIR, fname)


def get_or_create_node_id(suffix: str = "") -> str:
    """
    Returns the persistent unique node_id for this host (+ optional suffix).

    - If the identity file already exists, the saved ID is returned as-is.
    - Otherwise, a new ID is generated, saved, and returned.

    Args:
        suffix: Appended to both the file name and the generated node_id so
                multiple agents on the same machine each maintain distinct IDs.
    """
    configured_id = os.getenv("NODE_ID", "").strip()
    if configured_id:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,128}", configured_id):
            raise ValueError("NODE_ID must be 3-128 characters using letters, digits, '.', '_' or '-'.")
        return configured_id

    id_file = _id_file_path(suffix)

    if os.path.exists(id_file):
        try:
            with open(id_file, "r", encoding="utf-8") as fh:
                node_id = fh.read().strip()
                if node_id:
                    return node_id
        except Exception as exc:
            print(f"[ID GENERATOR WARN] Could not read identity file ({exc}). Re-generating.")

    import hashlib
    # Build a new ID: node_<clean_hostname>_<hw_hash>_<uuid>[_suffix]
    raw_hostname  = socket.gethostname()
    clean_host    = re.sub(r"[^a-zA-Z0-9_-]", "", raw_hostname).lower()[:12]
    try:
        hw_node = uuid.getnode()
        hw_hash = hashlib.sha256(str(hw_node).encode()).hexdigest()[:6]
    except Exception:
        hw_hash = "000000"
    rand_part     = uuid.uuid4().hex[:6]
    suffix_part   = f"_{suffix}" if suffix else ""
    node_id       = f"node_{clean_host}_{hw_hash}_{rand_part}{suffix_part}"

    try:
        with open(id_file, "w", encoding="utf-8") as fh:
            fh.write(node_id)
        print(f"[ID GENERATOR] Generated new persistent Node ID: '{node_id}' -> {id_file}")
    except Exception as exc:
        print(f"[ID GENERATOR WARN] Could not persist identity file ({exc})")

    return node_id


if __name__ == "__main__":
    print(f"Default node_id : {get_or_create_node_id()}")
    print(f"Suffixed node_id: {get_or_create_node_id(suffix='sim2')}")
