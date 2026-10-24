PYTHON ?= python3

.PHONY: test check check-public firmware

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
	$(PYTHON) -m unittest discover -s scripts -p 'test_*.py' -v
	$(PYTHON) -m unittest discover -s host -p 'test_*.py' -v
	$(PYTHON) -m unittest discover -s web -p 'test_*.py' -v
	$(MAKE) -C firmware/forward-3s test
	$(MAKE) -C firmware/manual-hold test
	$(MAKE) -C firmware/commissioning test

check-public:
	$(PYTHON) scripts/check_public_tree.py

check: test check-public

firmware:
	$(MAKE) -C firmware/forward-3s all
