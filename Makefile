.PHONY: default all clear acquire install filter normalize publish
default: all

RAW_DATA_DIR      := .dev/data/raw/
FILTERED_DATA_DIR := .dev/data/filtered/

specs      := indices.html dom.html input.html syntax.html
spec_etags := $(addprefix $(RAW_DATA_DIR), $(specs:.html=.etag))
spec_times := $(addprefix $(RAW_DATA_DIR), $(specs:.html=.time))
all_specs  := $(addprefix $(RAW_DATA_DIR), $(specs))
all_times  := $(spec_times) $(RAW_DATA_DIR)aria.time

all: publish

clear:
	rm --force $(all_specs) $(spec_etags) $(spec_times)
	rm --force $(RAW_DATA_DIR)aria.html $(RAW_DATA_DIR)aria.etag $(RAW_DATA_DIR)aria.time $(RAW_DATA_DIR)manifest.json
	rm --force --recursive $(FILTERED_DATA_DIR)
	rm --force --recursive dist/*/*

install:
	python3 -m pip install -r requirements.txt

publish: normalize
	# MAKE: 📦 Generate dist/json/*.json, dist/yaml/**/*.yaml, dist/NOTICE, dist/manifest.json.
	@python3 src/main.py

normalize: filter

filter: acquire
	# MAKE: 🧲 Extract raw HTML into faithful NDJSON records + manifest under .dev/data/filtered/
	@python3 src/filter.py

acquire: $(RAW_DATA_DIR)manifest.json

$(RAW_DATA_DIR):
	@mkdir -p $@

$(RAW_DATA_DIR)aria.html: | $(RAW_DATA_DIR)
	@touch $(RAW_DATA_DIR)aria.etag
	# MAKE: 📥 Acquire ARIA specification from https://w3c.github.io/aria/
	@curl --silent --show-error --fail \
	      --etag-compare $(RAW_DATA_DIR)aria.etag --etag-save $(RAW_DATA_DIR)aria.etag \
	      --dump-header $(RAW_DATA_DIR)aria.headers \
	      --output $@ \
	      https://w3c.github.io/aria/
	@grep --ignore-case '^last-modified:' $(RAW_DATA_DIR)aria.headers \
	    | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' \
	    > $(RAW_DATA_DIR)aria.time.new
	@if [ -s $(RAW_DATA_DIR)aria.time.new ]; then mv $(RAW_DATA_DIR)aria.time.new $(RAW_DATA_DIR)aria.time; \
	                                   else rm --force $(RAW_DATA_DIR)aria.time.new; fi
	@rm --force $(RAW_DATA_DIR)aria.headers

$(RAW_DATA_DIR)%.html: | $(RAW_DATA_DIR)
	# MAKE: 📥 Acquire HTML specification from https://html.spec.whatwg.org/multipage/$*.html
	@touch $(RAW_DATA_DIR)$*.etag
	@curl --silent --show-error --fail \
	     --etag-compare $(RAW_DATA_DIR)$*.etag --etag-save $(RAW_DATA_DIR)$*.etag \
	     --dump-header $(RAW_DATA_DIR)$*.headers \
	     --output $@ \
	     https://html.spec.whatwg.org/multipage/$*.html
	@grep --ignore-case '^last-modified:' $(RAW_DATA_DIR)$*.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' \
	     > $(RAW_DATA_DIR)$*.time.new
	@if [ -s $(RAW_DATA_DIR)$*.time.new ]; then mv $(RAW_DATA_DIR)$*.time.new $(RAW_DATA_DIR)$*.time; \
	                                 else rm --force $(RAW_DATA_DIR)$*.time.new; fi
	@rm --force $(RAW_DATA_DIR)$*.headers

$(RAW_DATA_DIR)manifest.json: $(all_specs) $(RAW_DATA_DIR)aria.html
	# MAKE: 📋 Generate manifest.json – collects all last‑modified timestamps
	@{ \
	    echo '{'; \
	    i=0; \
	    total=$(words $(all_times)); \
	    for f in $(all_times); do \
	        i=$$((i + 1)); \
	        name=$${f%.time}; \
	        name=$${name##*/};          # MAKE: strip directory, keep only filename \
	        printf '  "%s": "%s"' "$$name" "$$(cat $$f)"; \
	        [ $$i -lt $$total ] && echo ',' || echo; \
	    done; \
	    echo '}'; \
	} > $@