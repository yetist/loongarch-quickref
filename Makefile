PYTHON ?= .venv/bin/python
PDF := loongarch-quickref.pdf

.PHONY: all pdf check clean distclean

all: pdf

pdf:
	$(PYTHON) build.py

check:
	$(PYTHON) validate.py

clean:
	rm -rf build

distclean: clean
	rm -f $(PDF)
