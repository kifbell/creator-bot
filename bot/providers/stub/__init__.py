# Minimal valid MP3 — three silent MPEG1 Layer3 frames at 128kbps / 44100Hz.
# Sync word 0xFF 0xFB confirms MPEG1 Layer3 to any decoder.
# Multiple frames ensure at least one plays (some decoders skip frame 0).
_FRAME = (
    bytes([0xFF, 0xFB, 0x90, 0x64])  # header: MPEG1 Layer3 128k 44100 stereo
    + bytes(32)                        # side info — all zeros = silent
    + bytes(381)                       # main data — all zeros = silence
)
SILENT_MP3: bytes = _FRAME * 3
