PYTHON ?= ../../apps/api/.venv/bin/python
DIST := dist

.PHONY: zip schemas clean

schemas:
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) generate_output_schemas.py

# Each archive includes its own shared resources; fixtures and budgets stay local.
zip: schemas
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) build_packages.py --output-dir $(DIST)

clean:
	@rm -rf $(DIST)
