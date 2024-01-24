set -euo pipefail
python -m venv venv
pip install -e .[test]
pytest
mypy --strict .
pip wheel .
