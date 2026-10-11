"""Execute a notebook with this Python environment and save its real outputs."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/02_demand_experiment.ipynb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", nargs="?", type=Path, default=NOTEBOOK)
    args = parser.parse_args()
    path = args.notebook.resolve()
    notebook = nbformat.read(path, as_version=4)
    with tempfile.TemporaryDirectory(prefix="supplysignal-notebook-") as directory:
        scratch = Path(directory)
        kernel = scratch / "kernels" / "supplysignal"
        kernel.mkdir(parents=True)
        (kernel / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "SupplySignal verification", "language": "python",
        }))
        os.environ["IPYTHONDIR"] = str(scratch / "ipython")
        os.environ["MPLCONFIGDIR"] = str(scratch / "matplotlib")
        os.environ["JUPYTER_RUNTIME_DIR"] = str(scratch / "runtime")
        os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
        manager = KernelManager(
            kernel_name="supplysignal",
            kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernel.parent)]),
        )
        NotebookClient(
            notebook, km=manager, timeout=600, allow_errors=False,
            resources={"metadata": {"path": str(ROOT)}},
        ).execute(cleanup_kc=True)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not all(cell.execution_count is not None for cell in code):
        raise RuntimeError("Notebook execution was incomplete")
    nbformat.validate(notebook)
    nbformat.write(notebook, path)
    print(f"Executed {len(code)} code cells; saved outputs in {path}")


if __name__ == "__main__":
    main()
