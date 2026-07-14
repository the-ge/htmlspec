.PHONY: default clean
default: all ;

clean:
	make -C contrib clean
	rm -f spec-json/*.json

_contrib:
	make -C contrib

install:
	python3 -m pip install -r requirements.txt

dist:
	python3 src/parse.py
	# generates `spec-json/*.json`, etc.
	# run `make -B dist` to force this to update

all: _contrib dist

