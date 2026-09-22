# The DataAgent admin console imports skills as a ZIP upload, not a directory.
# The archive is a build product: skills/ is the source of truth and the only
# thing under version control, so dist/ is gitignored and regenerated on demand.

SKILL := md2ossie
DIST  := dist

.PHONY: zip clean

## Produce dist/md2ossie.zip with `md2ossie/SKILL.md` at the archive root —
## the console expects the skill directory itself to be the top-level entry.
zip: clean
	@mkdir -p $(DIST)
	@cd skills && zip -q -r ../$(DIST)/$(SKILL).zip $(SKILL) -x '*.DS_Store'
	@echo "$(DIST)/$(SKILL).zip"
	@unzip -l $(DIST)/$(SKILL).zip | head -5

clean:
	@rm -rf $(DIST)
