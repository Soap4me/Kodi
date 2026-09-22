ADDON_ID := plugin.video.soap4.me
VERSION  := $(shell sed -n 's/.*<addon [^>]*version="\([^"]*\)".*/\1/p' addon.xml | head -n 1)
DIST     := dist
ZIP      := $(DIST)/$(ADDON_ID)-$(VERSION).zip

.PHONY: zip clean

zip:
	@test -n "$(VERSION)" || { echo "no version found in addon.xml" >&2; exit 1; }
	@git diff --quiet HEAD -- || echo "warning: uncommitted changes are not included in the zip" >&2
	mkdir -p $(DIST)
	git archive --format=zip --prefix=$(ADDON_ID)/ -o $(ZIP) HEAD
	@echo "built $(ZIP)"

clean:
	rm -rf $(DIST)
