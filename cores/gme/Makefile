# arm64: scripts/build.sh gme   (Docker)   |   host check: make
#
# Unlike adl and opn this core is not ours - it is libretro's Game Music Emu,
# built from upstream as it stands. It is GPL-3.0 where ours are MIT, which is
# why it is built rather than vendored: the .so is gitignored, so nothing here
# redistributes a binary, and the revision below says exactly which source it
# came from.
GME := libretro-gme
# Pinned for the same reason as ADL_REV: what the device runs should change only
# when a commit here says so.
GME_REV ?= 1562f6207a066e9807243c89648d1cb44e411971

all: gme_libretro.so

$(GME)/Makefile:
	git init -q $(GME)
	git -C $(GME) remote add origin https://github.com/libretro/libretro-gme
	git -C $(GME) fetch -q --depth 1 origin $(GME_REV)
	git -C $(GME) checkout -q FETCH_HEAD

# Upstream's own Makefile; platform=unix is what it picks anyway, said out loud
# so a cross build in the container cannot guess something else from uname.
gme_libretro.so: $(GME)/Makefile
	$(MAKE) -C $(GME) platform=unix
	cp $(GME)/$@ $@

clean:
	rm -f gme_libretro.so
distclean: clean
	rm -rf $(GME)
.PHONY: all clean distclean
