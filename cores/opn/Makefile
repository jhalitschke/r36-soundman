# arm64: scripts/build.sh opn   (Docker)   |   host check: make
CC ?= gcc
OPN := libOPNMIDI
# Pinned for the same reason as cores/adl: the tests assert absolute levels.
OPN_REV ?= 8e0a0a6ac97a21f22c4b4d53d67a8d916d8c487b
OPN_LIB := $(OPN)/build/libOPNMIDI.a
CFLAGS += -O2 -fPIC -Wall -std=gnu11 -I$(OPN)/include

all: opn_libretro.so

$(OPN)/CMakeLists.txt:
	git init -q $(OPN)
	git -C $(OPN) remote add origin https://github.com/Wohlstand/libOPNMIDI
	git -C $(OPN) fetch -q --depth 1 origin $(OPN_REV)
	git -C $(OPN) checkout -q FETCH_HEAD

$(OPN_LIB): $(OPN)/CMakeLists.txt
	cmake -S $(OPN) -B $(OPN)/build -DCMAKE_BUILD_TYPE=Release \
	  -DlibOPNMIDI_STATIC=ON -DlibOPNMIDI_SHARED=OFF -DWITH_MIDI_SEQUENCER=OFF \
	  -DUSE_MAME_EMULATOR=ON -DCMAKE_POSITION_INDEPENDENT_CODE=ON
	cmake --build $(OPN)/build -j

opn_libretro.so: opn_libretro.c ../libretro.h $(OPN_LIB)
	$(CC) $(CFLAGS) -shared -o $@ opn_libretro.c $(OPN_LIB) -lstdc++ -lm

clean:
	rm -f opn_libretro.so
distclean: clean
	rm -rf $(OPN)
.PHONY: all clean distclean
