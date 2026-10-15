PYTHON ?= python3

.PHONY: test-engine test-worker test-app build-helper build-app package-local verify-fixtures verify-hashes verify

test-engine:
	$(PYTHON) -m unittest discover -s engine -p 'test_stl_doctor.py' -v

test-worker:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

test-app:
	swift test --package-path app

# The packaging pipeline deliberately verifies the helper and native app together.
# These aliases all run the full macOS build, tests and relocated-helper smoke.
build-helper build-app package-local:
	bash scripts/build-macos.sh

verify-fixtures:
	$(PYTHON) scripts/verify_fixtures.py --repair

verify-hashes:
	$(PYTHON) scripts/verify_fixtures.py --hashes-only

verify: test-engine test-worker verify-fixtures verify-hashes
