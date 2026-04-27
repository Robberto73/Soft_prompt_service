"""STUB: CoOp training script for video-LLM models.

Placeholders are substituted by `optimization.prompt_generator`:
    __DATASET_PATH__, __OUTPUT_DIR__, __NUM_VECTORS__, __CONTEXT_INIT__,
    __CLASS_TOKEN_POSITION__, __NET_DEPTH__.

This file is intentionally minimal — it imitates a CoOp training run so
the rest of the system (status polling, logs, exit codes) can be tested
end-to-end without PyTorch / CLIP / a real GPU.
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

    epochs = 5
    with log_path.open("a", encoding="utf-8") as log:
        msg = (
            f"[stub-coop] dataset={DATASET_PATH} num_vectors={NUM_VECTORS} "
            f"ctx_init={CONTEXT_INIT!r} pos={CLASS_TOKEN_POSITION} "
            f"depth={NET_DEPTH}"
        )
        print(msg, flush=True)
        log.write(msg + "\n")

        for epoch in range(1, epochs + 1):
            time.sleep(1.5)
            line = f"[stub-coop] epoch {epoch}/{epochs} loss={1.0/epoch:.3f}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        (out / "prompt_vectors.bin").write_bytes(b"\x00" * (NUM_VECTORS * 32))
        (out / "metrics.json").write_text(
            json.dumps(
                {
                    "epochs": epochs,
                    "final_loss": round(1.0 / epochs, 3),
                    "num_vectors": NUM_VECTORS,
                    "stub": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.write("[stub-coop] DONE\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
