# arm64: scripts/build.sh adl   (Docker)   |   Host-Check: make
CC ?= gcc
ADL := libADLMIDI
ADL_LIB := $(ADL)/build/libADLMIDI.a
CFLAGS += -O2 -fPIC -Wall -std=gnu11 -I$(ADL)/include

all: adl_libretro.so

$(ADL)/CMakeLists.txt:
	git clone --depth 1 https://github.com/Wohlstand/libADLMIDI $(ADL)

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
