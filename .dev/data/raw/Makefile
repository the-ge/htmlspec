.PHONY: default clear all
default: all ;

specs=indices.html dom.html input.html syntax.html
spec_etags=indices.etag dom.etag input.etag syntax.etag
spec_times=indices.time dom.time input.time syntax.time
all_times=$(spec_times) aria.time

clear:
	rm --force $(specs) $(spec_etags) $(spec_times) manifest.json
	rm --force aria.html aria.etag aria.time

aria.html:
	@touch aria.etag
	curl --silent --show-error --fail --etag-compare aria.etag --etag-save aria.etag --dump-header aria.headers --output aria.html https://w3c.github.io/aria/
	@grep --ignore-case '^last-modified:' aria.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > aria.time.new
	@if [ -s aria.time.new ]; then mv aria.time.new aria.time; else rm --force aria.time.new; fi
	@rm --force aria.headers

%.html:
	@touch $*.etag
	curl --silent --show-error --fail --etag-compare $*.etag --etag-save $*.etag --dump-header $*.headers --output $@ https://html.spec.whatwg.org/multipage/$@
	@grep --ignore-case '^last-modified:' $*.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > $*.time.new
	@if [ -s $*.time.new ]; then mv $*.time.new $*.time; else rm --force $*.time.new; fi
	@rm --force $*.headers

manifest.json: $(specs) aria.html
	@{ \
		echo '{'; \
		i=0; \
		total=$(words $(all_times)); \
		for f in $(all_times); do \
			i=$$((i + 1)); \
			name=$${f%.time}; \
			printf '  "%s": "%s"' "$$name" "$$(cat $$f)"; \
			[ $$i -lt $$total ] && echo ',' || echo; \
		done; \
		echo '}'; \
	} > $@

all: $(specs) aria.html manifest.json
