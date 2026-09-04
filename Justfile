[private]
default:
    @just --list

# Build tailcat snap.
build:
    snapcraft pack

# Format the functional test suite with ruff.
fmt:
    cd tests && uv run ruff format .

# Lint the functional test suite with ruff.
lint:
    cd tests && uv run ruff check .

# Run the functional test suite for the tailcat snap.
test:
    cd tests && uv run pytest functional/
