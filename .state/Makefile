.PHONY: default clean
default: all ;

specs=indices.html dom.html input.html syntax.html
spec_etags=indices.etag dom.etag input.etag syntax.etag
spec_times=indices.time dom.time input.time syntax.time

clean:
	rm --force $(specs) $(spec_etags) $(spec_times)
	rm --force aria.html aria.etag aria.time

aria.html:
	@touch aria.etag
	curl --silent --show-error --fail --etag-compare aria.etag --etag-save aria.etag --dump-header aria.headers --output aria.html https://w3c.github.io/aria/
	@grep --ignore-case '^last-modified:' aria.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > aria.time
	@rm --force aria.headers

%.html:
	@touch $*.etag
	curl --silent --show-error --fail --etag-compare $*.etag --etag-save $*.etag --dump-header $*.headers --output $@ https://html.spec.whatwg.org/multipage/$@
	@grep --ignore-case '^last-modified:' $*.headers | sed 's/^[Ll]ast-[Mm]odified: //;s/\r$$//' > $*.time
	@rm --force $*.headers

all: $(specs) aria.html
