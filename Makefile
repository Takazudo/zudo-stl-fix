PYTHON ?= python3

.PHONY: test-engine verify-fixtures verify-hashes verify

test-engine:
	$(PYTHON) -m unittest discover -s engine -p 'test_stl_doctor.py' -v

verify-fixtures:
	$(PYTHON) scripts/verify_fixtures.py --repair

verify-hashes:
	$(PYTHON) scripts/verify_fixtures.py --hashes-only

verify: test-engine verify-fixtures
