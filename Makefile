.PHONY: default clear publish all install
default: all

OUTDIR = .dev/data/raw/

specs      := indices.html dom.html input.html syntax.html
spec_etags := $(addprefix $(OUTDIR), $(specs:.html=.etag))
spec_times := $(addprefix $(OUTDIR), $(specs:.html=.time))
all_specs  := $(addprefix $(OUTDIR), $(specs))
all_times  := $(spec_times) $(OUTDIR)aria.time

all: $(all_specs) $(OUTDIR)aria.html $(OUTDIR)manifest.json publish

install:
	python3 -m pip install -r requirements.txt

publish:
	# Generates dist/json/*.json, dist/yaml/**/*.yaml, dist/NOTICE, dist/manifest.json.
	python3 src/main.py

clear:
	rm --force $(all_specs) $(spec_etags) $(spec_times)
	rm --force $(OUTDIR)aria.html $(OUTDIR)aria.etag $(OUTDIR)aria.time $(OUTDIR)manifest.json
	rm --force --recursive dist/*/*

$(OUTDIR):
	mkdir -p $@

$(OUTDIR)aria.html: | $(OUTDIR)
	# Acquire ARIA specification
	@touch $(OUTDIR)aria.etag
	curl --silent --show-error --fail \
	     --etag-compare $(OUTDIR)aria.etag \
	     --etag-save $(OUTDIR)aria.etag \
	     --dump-header $(OUTDIR)aria.headers \
	     --output $@ \
	     https://w3c.github.io/aria/
	@grep --ignore-case '^last-modified:' $(OUTDIR)aria.headers \
	 | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > $(OUTDIR)aria.time.new
	@if [ -s $(OUTDIR)aria.time.new ]; then \
	    mv $(OUTDIR)aria.time.new $(OUTDIR)aria.time; \
	else \
	    rm --force $(OUTDIR)aria.time.new; \
	fi
	@rm --force $(OUTDIR)aria.headers

$(OUTDIR)%.html: | $(OUTDIR)
	# Acquire HTML specification (pattern rule)
	@touch $(OUTDIR)$*.etag
	curl --silent --show-error --fail \
	     --etag-compare $(OUTDIR)$*.etag \
	     --etag-save $(OUTDIR)$*.etag \
	     --dump-header $(OUTDIR)$*.headers \
	     --output $@ \
	     https://html.spec.whatwg.org/multipage/$*.html
	@grep --ignore-case '^last-modified:' $(OUTDIR)$*.headers \
	 | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > $(OUTDIR)$*.time.new
	@if [ -s $(OUTDIR)$*.time.new ]; then \
	    mv $(OUTDIR)$*.time.new $(OUTDIR)$*.time; \
	else \
	    rm --force $(OUTDIR)$*.time.new; \
	fi
	@rm --force $(OUTDIR)$*.headers

$(OUTDIR)manifest.json: $(all_specs) $(OUTDIR)aria.html
	# Generate manifest.json – collects all last‑modified timestamps
	@{ \
	    echo '{'; \
	    i=0; \
	    total=$(words $(all_times)); \
	    for f in $(all_times); do \
	        i=$$((i + 1)); \
	        name=$${f%.time}; \
	        name=$${name##*/};          # strip directory, keep only filename \
	        printf '  "%s": "%s"' "$$name" "$$(cat $$f)"; \
	        [ $$i -lt $$total ] && echo ',' || echo; \
	    done; \
	    echo '}'; \
	} > $@