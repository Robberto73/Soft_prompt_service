"""STUB: CoCoOp training script for CLIP-style models.

Placeholders: __DATASET_PATH__, __OUTPUT_DIR__, __NUM_VECTORS__,
              __CONTEXT_INIT__, __CLASS_TOKEN_POSITION__, __NET_DEPTH__.

This is NOT a real implementation; it merely simulates the run so that
status polling and log streaming can be exercised.
"""

import json
import sys
import time
from pathlib import Path


DATASET_PATH = r"__DATASET_PATH__"
OUTPUT_DIR = r"__OUTPUT_DIR__"
NUM_VECTORS = __NUM_VECTORS__
CONTEXT_INIT = "__CONTEXT_INIT__"
CLASS_TOKEN_POSITION = "__CLASS_TOKEN_POSITION__"
NET_DEPTH = __NET_DEPTH__


def main() -> int:
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "train.log"
    with log_path.open("a", encoding="utf-8") as log:
        line = (
            f"[stub-cocoop] meta-net depth={NET_DEPTH} num_vectors={NUM_VECTORS} "
            f"ctx={CONTEXT_INIT!r}"
        )
        print(line, flush=True)
        log.write(line + "\n")

        epochs = 4
        for epoch in range(1, epochs + 1):
            time.sleep(1.5)
            line = f"[stub-cocoop] epoch {epoch}/{epochs} acc={0.5 + 0.1*epoch:.2f}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        (out / "prompt_vectors.bin").write_bytes(b"\x00" * (NUM_VECTORS * 64))
        (out / "metrics.json").write_text(
            json.dumps(
                {
                    "epochs": epochs,
                    "final_accuracy": round(0.5 + 0.1 * epochs, 2),
                    "num_vectors": NUM_VECTORS,
                    "net_depth": NET_DEPTH,
                    "stub": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.write("[stub-cocoop] DONE\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
