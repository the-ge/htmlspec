.PHONY: default clear publish all install
default: all ;

_acquire:
	make -C .dev/state

clear:
	make -C .dev/state clear
	rm -f dist/*

install:
	python3 -m pip install -r requirements.txt

publish:
	# generates dist/json/*.json, dist/yaml/**/*.yaml, dist/NOTICE, dist/manifest.json
	python3 src/main.py

all: _acquire publish
