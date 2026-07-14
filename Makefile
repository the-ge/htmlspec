.PHONY: default clean
default: all ;

_state:
	make -C .state

clean:
	make -C .state clean
	rm -f spec-json/*.json

install:
	python3 -m pip install -r requirements.txt

dist:
	python3 src/main.py
	# generates `spec-json/*.json`, etc.
	# run `make -B dist` to force this to update

all: _state dist

