/*
 * opn_libretro - YM2612/OPN2 synth as a libretro core (libOPNMIDI).
 * Content: a .wopn bank, required. libOPNMIDI carries no embedded bank, so
 *          unlike cores/adl this core cannot start without one.
 * MIDI in:  reads /dev/snd/midiC*D* directly (ALSA rawmidi, non-blocking) -
 *           independent of whether RetroArch was built with MIDI support.
 *           Override: environment variable OPN_MIDI_DEV=/dev/snd/midiC1D0
 * Controls: L/R = program -/+ (channel 1), A = panic, Select+Start = RetroArch menu
 * Output:   libOPNMIDI leaves headroom like libADLMIDI (single note measured at
 *           -24.9 dBFS), hence a fixed gain with saturation. Default 4 puts the
 *           four-voice demo at -5.7 dBFS. Override: OPN_GAIN=1..64.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include <glob.h>
#include <errno.h>
#include "../libretro.h"
#include <opnmidi.h>

#define SR   48000
#define FPS  60
#define FRAMES (SR / FPS)          /* 800 frames per retro_run */
#define W 320
#define H 240

static retro_environment_t        env_cb;
static retro_video_refresh_t      video_cb;
static retro_audio_sample_batch_t audio_batch_cb;
static retro_input_poll_t         input_poll_cb;
static retro_input_state_t        input_state_cb;
static retro_log_printf_t         log_cb;

static struct OPN2_MIDIPlayer *opn;
static uint16_t fb[W * H];
static int16_t  abuf[FRAMES * 2];
static int      midi_fd = -1;
static char     midi_path[256];
static uint8_t  chan_act[16];
static int      midi_fail_logged;          /* only complain about a missing device once */
static int      midi_retry;                /* frames until the next open() attempt */
static int      gain_q8 = 4 * 256;         /* output gain in 8.8 fixed point, OPN_GAIN */
static int      program;
static uint16_t prev_buttons;

/* ---- MIDI ------------------------------------------------------------ */
static uint8_t st_byte, st_data[2];
static int     st_need, st_got;

static void midi_open(void)
{
    const char *e = getenv("OPN_MIDI_DEV");
    if (midi_fd >= 0) { close(midi_fd); midi_fd = -1; }   /* never leak on a re-open */
    if (e) {
        strncpy(midi_path, e, sizeof midi_path - 1);
    } else {
        glob_t g;
        midi_path[0] = 0;
        if (glob("/dev/snd/midiC*D*", 0, NULL, &g) == 0 && g.gl_pathc > 0)
            strncpy(midi_path, g.gl_pathv[0], sizeof midi_path - 1);
        globfree(&g);
    }
    if (midi_path[0])
        midi_fd = open(midi_path, O_RDONLY | O_NONBLOCK);
    if (midi_fd >= 0) {
        log_cb(RETRO_LOG_INFO, "[opn] MIDI %s -> open\n", midi_path);
        midi_fail_logged = 0;
    } else if (!midi_fail_logged) {
        log_cb(RETRO_LOG_INFO, "[opn] MIDI %s -> FAILED, retrying once a second\n",
               midi_path[0] ? midi_path : "(no rawmidi device)");
        midi_fail_logged = 1;
    }
}

static void midi_msg(uint8_t st, uint8_t d1, uint8_t d2)
{
    int ch = st & 0x0f;
    switch (st & 0xf0) {
    case 0x90:
        if (d2) { opn2_rt_noteOn(opn, ch, d1, d2); chan_act[ch] = 255; }
        else      opn2_rt_noteOff(opn, ch, d1);
        break;
    case 0x80: opn2_rt_noteOff(opn, ch, d1); break;
    case 0xB0: opn2_rt_controllerChange(opn, ch, d1, d2); break;
    case 0xC0: opn2_rt_patchChange(opn, ch, d1); break;
    case 0xE0: opn2_rt_pitchBendML(opn, ch, d2, d1); break;
    default: break;
    }
}

static void midi_poll(void)
{
    uint8_t buf[256];
    ssize_t n;
    if (midi_fd < 0) {
        /* Hot-plug: the keyboard is usually plugged in after the core started. */
        if (++midi_retry >= FPS) { midi_retry = 0; midi_open(); }
        return;
    }
    while ((n = read(midi_fd, buf, sizeof buf)) > 0) {
        for (ssize_t i = 0; i < n; i++) {
            uint8_t b = buf[i];
            if (b >= 0xF8) continue;                 /* realtime */
            if (b & 0x80) {
                if (b >= 0xF0) { st_byte = 0; continue; } /* SysEx/Common */
                st_byte = b; st_got = 0;
                st_need = ((b & 0xf0) == 0xC0 || (b & 0xf0) == 0xD0) ? 1 : 2;
                continue;
            }
            if (!st_byte) continue;
            st_data[st_got++] = b;
            if (st_got == st_need) {
                midi_msg(st_byte, st_data[0], st_need == 2 ? st_data[1] : 0);
                st_got = 0;                         /* running status */
            }
        }
    }
}

/* ---- video ----------------------------------------------------------- */
static void rect(int x, int y, int w, int h, uint16_t c)
{
    for (int j = y; j < y + h && j < H; j++)
        for (int i = x; i < x + w && i < W; i++)
            fb[j * W + i] = c;
}

static void draw(void)
{
    memset(fb, 0, sizeof fb);
    rect(8, 8, 8, 8, midi_fd >= 0 ? 0x07E0 : 0xF800);      /* MIDI status */
    rect(24, 8, 2 + program, 8, 0xFFFF);                   /* program as a bar */
    for (int ch = 0; ch < 16; ch++) {                      /* channel activity */
        int h = chan_act[ch] * 180 / 255;
        rect(8 + ch * 19, 220 - h, 16, h, ch == 9 ? 0xFD20 : 0x3D9F);
        if (chan_act[ch] > 6) chan_act[ch] -= 6; else chan_act[ch] = 0;
    }
}

/* ---- libretro -------------------------------------------------------- */
static void fallback_log(enum retro_log_level l, const char *fmt, ...)
{ (void)l; va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a); }

void retro_set_environment(retro_environment_t cb)
{
    env_cb = cb;
    struct retro_log_callback lc;
    log_cb = cb(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &lc) ? lc.log : fallback_log;
}
void retro_set_video_refresh(retro_video_refresh_t cb)         { video_cb = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb)           { (void)cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch_cb = cb; }
void retro_set_input_poll(retro_input_poll_t cb)               { input_poll_cb = cb; }
void retro_set_input_state(retro_input_state_t cb)             { input_state_cb = cb; }

void retro_init(void) {}
void retro_deinit(void) {}
unsigned retro_api_version(void) { return RETRO_API_VERSION; }

void retro_get_system_info(struct retro_system_info *info)
{
    memset(info, 0, sizeof *info);
    info->library_name     = "opn";
    info->library_version  = "0.1";
    info->valid_extensions = "wopn";
    info->need_fullpath    = true;
}

void retro_get_system_av_info(struct retro_system_av_info *info)
{
    info->timing.fps         = FPS;
    info->timing.sample_rate = SR;
    info->geometry.base_width  = info->geometry.max_width  = W;
    info->geometry.base_height = info->geometry.max_height = H;
    info->geometry.aspect_ratio = 4.0f / 3.0f;
}

bool retro_load_game(const struct retro_game_info *game)
{
    enum retro_pixel_format fmt = RETRO_PIXEL_FORMAT_RGB565;
    if (!env_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &fmt)) return false;

    if (opn) { opn2_close(opn); opn = NULL; }   /* a second load must not leak */
    opn = opn2_init(SR);
    if (!opn) return false;
    opn2_switchEmulator(opn, OPNMIDI_EMU_MAME);    /* lighter than Nuked, enough for the RK3326 */
    opn2_setNumChips(opn, 1);
    opn2_setSoftPanEnabled(opn, 1);
    if (!game || !game->path || !game->path[0]) {
        /* libOPNMIDI has no embedded bank: without a .wopn there is nothing to play. */
        log_cb(RETRO_LOG_ERROR, "[opn] no bank - put a .wopn in /roms/opn\n");
        opn2_close(opn);
        opn = NULL;
        return false;
    }
    if (opn2_openBankFile(opn, game->path) < 0) {
        log_cb(RETRO_LOG_ERROR, "[opn] bank %s: %s\n", game->path, opn2_errorInfo(opn));
        opn2_close(opn);
        opn = NULL;
        return false;
    }
    log_cb(RETRO_LOG_INFO, "[opn] bank %s\n", game->path);
    const char *g = getenv("OPN_GAIN");
    if (g) {
        double v = atof(g);
        if (v > 0.0 && v <= 64.0) gain_q8 = (int)(v * 256.0 + 0.5);
    }
    log_cb(RETRO_LOG_INFO, "[opn] Gain %.2f\n", gain_q8 / 256.0);
    midi_open();
    return true;
}

void retro_unload_game(void)
{
    if (midi_fd >= 0) close(midi_fd);
    midi_fd = -1;
    if (opn) opn2_close(opn);
    opn = NULL;
}

void retro_run(void)
{
    input_poll_cb();
    uint16_t b = 0;
    for (int i = 0; i < 16; i++)
        if (input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, i)) b |= 1 << i;
    uint16_t pressed = b & ~prev_buttons;
    prev_buttons = b;

    if (pressed & (1 << RETRO_DEVICE_ID_JOYPAD_R)) program = (program + 1) & 127;
    if (pressed & (1 << RETRO_DEVICE_ID_JOYPAD_L)) program = (program + 127) & 127;
    if (pressed & ((1 << RETRO_DEVICE_ID_JOYPAD_R) | (1 << RETRO_DEVICE_ID_JOYPAD_L))) {
        opn2_rt_patchChange(opn, 0, program);
        log_cb(RETRO_LOG_INFO, "[opn] Program %d\n", program);
    }
    if (pressed & (1 << RETRO_DEVICE_ID_JOYPAD_A)) opn2_panic(opn);

    midi_poll();
    int got = opn2_generate(opn, FRAMES * 2, abuf);
    for (int i = 0; i < got; i++) {
        int32_t v = ((int32_t)abuf[i] * gain_q8) >> 8;
        abuf[i] = v > 32767 ? 32767 : v < -32768 ? -32768 : (int16_t)v;
    }
    audio_batch_cb(abuf, got > 0 ? got / 2 : 0);
    draw();
    video_cb(fb, W, H, W * sizeof(uint16_t));
}

/* ---- stubs ----------------------------------------------------------- */
void retro_set_controller_port_device(unsigned p, unsigned d) { (void)p; (void)d; }
void retro_reset(void) { if (opn) opn2_panic(opn); }
size_t retro_serialize_size(void) { return 0; }
bool retro_serialize(void *d, size_t s) { (void)d; (void)s; return false; }
bool retro_unserialize(const void *d, size_t s) { (void)d; (void)s; return false; }
void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned i, bool e, const char *c) { (void)i; (void)e; (void)c; }
bool retro_load_game_special(unsigned t, const struct retro_game_info *g, size_t n)
{ (void)t; (void)g; (void)n; return false; }
unsigned retro_get_region(void) { return RETRO_REGION_PAL; }
void *retro_get_memory_data(unsigned id) { (void)id; return NULL; }
size_t retro_get_memory_size(unsigned id) { (void)id; return 0; }
