.PHONY: default clean
default: all ;

_state:
	make -C .dev/state

clean:
	make -C .dev/state clean
	rm -f dist/json/*.json

install:
	python3 -m pip install -r requirements.txt

dist:
	python3 src/main.py
	# generates `dist/json/*.json`, etc.
	# run `make -B dist` to force this to update

all: _state dist

