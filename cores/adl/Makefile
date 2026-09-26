# arm64: scripts/build.sh adl   (Docker)   |   host check: make
CC ?= gcc
ADL := libADLMIDI
# Pinned: README's measured levels and tests/test_core_audio.py assert absolute
# numbers, so tracking upstream HEAD would change the audio without a commit here.
ADL_REV ?= d08c0ec06566ef080df50dca7aa7bfbd01d58be4
ADL_LIB := $(ADL)/build/libADLMIDI.a
CFLAGS += -O2 -fPIC -Wall -std=gnu11 -I$(ADL)/include

all: adl_libretro.so

$(ADL)/CMakeLists.txt:
	git init -q $(ADL)
	git -C $(ADL) remote add origin https://github.com/Wohlstand/libADLMIDI
	git -C $(ADL) fetch -q --depth 1 origin $(ADL_REV)
	git -C $(ADL) checkout -q FETCH_HEAD

$(ADL_LIB): $(ADL)/CMakeLists.txt
	cmake -S $(ADL) -B $(ADL)/build -DCMAKE_BUILD_TYPE=Release \
	  -DlibADLMIDI_STATIC=ON -DlibADLMIDI_SHARED=OFF -DWITH_MIDI_SEQUENCER=OFF \
	  -DWITH_EMBEDDED_BANKS=ON -DCMAKE_POSITION_INDEPENDENT_CODE=ON
	cmake --build $(ADL)/build -j

adl_libretro.so: adl_libretro.c ../libretro.h $(ADL_LIB)
	$(CC) $(CFLAGS) -shared -o $@ adl_libretro.c $(ADL_LIB) -lstdc++ -lm

clean:
	rm -f adl_libretro.so
distclean: clean
	rm -rf $(ADL)
.PHONY: all clean distclean
