PYTHON ?= .venv/bin/python
PDF := loongarch-quickref.pdf
PDF_VEC := loongarch-quickref-vector.pdf

.PHONY: all pdf pdf-vec check check-vec clean distclean

all: pdf pdf-vec

pdf:
	$(PYTHON) build.py

pdf-vec:
	$(PYTHON) build.py --content content-vec.yaml

check:
	$(PYTHON) validate.py

check-vec:
	$(PYTHON) validate.py --content content-vec.yaml

clean:
	rm -rf build

distclean: clean
	rm -f $(PDF) $(PDF_VEC)
