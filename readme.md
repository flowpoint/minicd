mypy src/mycd/cli.py

pip install -e .[dev]


preferred buildpattern:

create a single ci.sh file at the repository root that runs everything for a commit
so you should have a ci.sh on every branch

a note about integration tests


this requires a correct git setup:
git config set pull.rebase true

git config set name
git config set email
