.PHONY: default clear publish normalize all install
default: all

OUTDIR = .dev/data/raw/
NORMDIR = .dev/data/normalized/

specs      := indices.html dom.html input.html syntax.html
spec_etags := $(addprefix $(OUTDIR), $(specs:.html=.etag))
spec_times := $(addprefix $(OUTDIR), $(specs:.html=.time))
all_specs  := $(addprefix $(OUTDIR), $(specs))
all_times  := $(spec_times) $(OUTDIR)aria.time

all: publish

install:
	python3 -m pip install -r requirements.txt

publish: normalize
	# MAKE: 📦 Generate dist/json/*.json, dist/yaml/**/*.yaml, dist/NOTICE, dist/manifest.json.
	@python3 src/main.py

normalize: $(OUTDIR)manifest.json
	# MAKE: 🧲 Extract raw HTML into faithful NDJSON records + manifest under .dev/data/normalized/
	@python3 src/normalize.py

clear:
	rm --force $(all_specs) $(spec_etags) $(spec_times)
	rm --force $(OUTDIR)aria.html $(OUTDIR)aria.etag $(OUTDIR)aria.time $(OUTDIR)manifest.json
	rm --force --recursive $(NORMDIR)
	rm --force --recursive dist/*/*

$(OUTDIR):
	mkdir -p $@

$(OUTDIR)aria.html: | $(OUTDIR)
	@touch $(OUTDIR)aria.etag
	# MAKE: 📥 Acquire ARIA specification from https://w3c.github.io/aria/
	@curl --silent --show-error --fail \
	      --etag-compare $(OUTDIR)aria.etag --etag-save $(OUTDIR)aria.etag \
	      --dump-header $(OUTDIR)aria.headers \
	      --output $@ \
	      https://w3c.github.io/aria/
	@grep --ignore-case '^last-modified:' $(OUTDIR)aria.headers \
	    | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' \
	    > $(OUTDIR)aria.time.new
	@if [ -s $(OUTDIR)aria.time.new ]; then mv $(OUTDIR)aria.time.new $(OUTDIR)aria.time; \
	                                   else rm --force $(OUTDIR)aria.time.new; fi
	@rm --force $(OUTDIR)aria.headers

$(OUTDIR)%.html: | $(OUTDIR)
	# MAKE: 📥 Acquire HTML specification from https://html.spec.whatwg.org/multipage/$*.html
	@touch $(OUTDIR)$*.etag
	@curl --silent --show-error --fail \
	     --etag-compare $(OUTDIR)$*.etag --etag-save $(OUTDIR)$*.etag \
	     --dump-header $(OUTDIR)$*.headers \
	     --output $@ \
	     https://html.spec.whatwg.org/multipage/$*.html
	@grep --ignore-case '^last-modified:' $(OUTDIR)$*.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' \
	     > $(OUTDIR)$*.time.new
	@if [ -s $(OUTDIR)$*.time.new ]; then mv $(OUTDIR)$*.time.new $(OUTDIR)$*.time; \
	                                 else rm --force $(OUTDIR)$*.time.new; fi
	@rm --force $(OUTDIR)$*.headers

$(OUTDIR)manifest.json: $(all_specs) $(OUTDIR)aria.html
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