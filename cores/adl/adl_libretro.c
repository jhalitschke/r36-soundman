/*
 * adl_libretro – OPL3-Synth als libretro-Core (libADLMIDI).
 * Content: .wopl-Bank (optional, sonst eingebettete Bank).
 * MIDI-In: liest /dev/snd/midiC*D* direkt (ALSA rawmidi, non-blocking) –
 *          unabhängig davon, ob RetroArch mit MIDI-Support gebaut ist.
 *          Override: Umgebungsvariable ADL_MIDI_DEV=/dev/snd/midiC1D0
 * Steuerung: L/R = Program -/+ (Kanal 1), A = Panic, Select+Start = RetroArch-Menü
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include <glob.h>
#include "../libretro.h"
#include <adlmidi.h>

#define SR   48000
#define FPS  60
#define FRAMES (SR / FPS)          /* 800 Frames pro retro_run */
#define W 320
#define H 240

static retro_environment_t        env_cb;
static retro_video_refresh_t      video_cb;
static retro_audio_sample_batch_t audio_batch_cb;
static retro_input_poll_t         input_poll_cb;
static retro_input_state_t        input_state_cb;
static retro_log_printf_t         log_cb;

static struct ADL_MIDIPlayer *adl;
static uint16_t fb[W * H];
static int16_t  abuf[FRAMES * 2];
static int      midi_fd = -1;
static char     midi_path[256];
static uint8_t  chan_act[16];
static int      program;
static uint16_t prev_buttons;

/* ---- MIDI ------------------------------------------------------------ */
static uint8_t st_byte, st_data[2];
static int     st_need, st_got;

static void midi_open(void)
{
    const char *e = getenv("ADL_MIDI_DEV");
    if (e) {
        strncpy(midi_path, e, sizeof midi_path - 1);
    } else {
        glob_t g;
        if (glob("/dev/snd/midiC*D*", 0, NULL, &g) == 0 && g.gl_pathc > 0)
            strncpy(midi_path, g.gl_pathv[0], sizeof midi_path - 1);
        globfree(&g);
    }
    if (midi_path[0])
        midi_fd = open(midi_path, O_RDONLY | O_NONBLOCK);
    log_cb(RETRO_LOG_INFO, "[adl] MIDI %s -> %s\n",
           midi_path[0] ? midi_path : "(kein rawmidi-Device)",
           midi_fd >= 0 ? "offen" : "FEHLER");
}

static void midi_msg(uint8_t st, uint8_t d1, uint8_t d2)
{
    int ch = st & 0x0f;
    switch (st & 0xf0) {
    case 0x90:
        if (d2) { adl_rt_noteOn(adl, ch, d1, d2); chan_act[ch] = 255; }
        else      adl_rt_noteOff(adl, ch, d1);
        break;
    case 0x80: adl_rt_noteOff(adl, ch, d1); break;
    case 0xB0: adl_rt_controllerChange(adl, ch, d1, d2); break;
    case 0xC0: adl_rt_patchChange(adl, ch, d1); break;
    case 0xE0: adl_rt_pitchBendML(adl, ch, d2, d1); break;
    default: break;
    }
}

static void midi_poll(void)
{
    uint8_t buf[256];
    ssize_t n;
    if (midi_fd < 0) return;
    while ((n = read(midi_fd, buf, sizeof buf)) > 0) {
        for (ssize_t i = 0; i < n; i++) {
            uint8_t b = buf[i];
            if (b >= 0xF8) continue;                 /* Realtime */
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
                st_got = 0;                         /* Running Status */
            }
        }
    }
}

/* ---- Video ----------------------------------------------------------- */
static void rect(int x, int y, int w, int h, uint16_t c)
{
    for (int j = y; j < y + h && j < H; j++)
        for (int i = x; i < x + w && i < W; i++)
            fb[j * W + i] = c;
}

static void draw(void)
{
    memset(fb, 0, sizeof fb);
    rect(8, 8, 8, 8, midi_fd >= 0 ? 0x07E0 : 0xF800);      /* MIDI-Status */
    rect(24, 8, 2 + program, 8, 0xFFFF);                   /* Program als Balken */
    for (int ch = 0; ch < 16; ch++) {                      /* Kanal-Aktivität */
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
    bool t = true;
    cb(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &t);
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
    info->library_name     = "adl";
    info->library_version  = "0.1";
    info->valid_extensions = "wopl";
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
    unsigned lat = 32;
    env_cb(RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY, &lat);

    adl = adl_init(SR);
    if (!adl) return false;
    adl_switchEmulator(adl, ADLMIDI_EMU_DOSBOX);   /* leichter als Nuked, reicht dem RK3326 */
    adl_setNumChips(adl, 1);
    adl_setSoftPanEnabled(adl, 1);
    if (game && game->path) {
        if (adl_openBankFile(adl, game->path) < 0) {
            log_cb(RETRO_LOG_ERROR, "[adl] Bank %s: %s\n", game->path, adl_errorInfo(adl));
            return false;
        }
        log_cb(RETRO_LOG_INFO, "[adl] Bank %s\n", game->path);
    } else {
        adl_setBank(adl, 0);
        log_cb(RETRO_LOG_INFO, "[adl] eingebettete Bank 0\n");
    }
    midi_open();
    return true;
}

void retro_unload_game(void)
{
    if (midi_fd >= 0) close(midi_fd);
    midi_fd = -1;
    if (adl) adl_close(adl);
    adl = NULL;
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
        adl_rt_patchChange(adl, 0, program);
        log_cb(RETRO_LOG_INFO, "[adl] Program %d\n", program);
    }
    if (pressed & (1 << RETRO_DEVICE_ID_JOYPAD_A)) adl_panic(adl);

    midi_poll();
    int got = adl_generate(adl, FRAMES * 2, abuf);
    audio_batch_cb(abuf, got > 0 ? got / 2 : 0);
    draw();
    video_cb(fb, W, H, W * sizeof(uint16_t));
}

/* ---- Stubs ----------------------------------------------------------- */
void retro_set_controller_port_device(unsigned p, unsigned d) { (void)p; (void)d; }
void retro_reset(void) { if (adl) adl_panic(adl); }
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
