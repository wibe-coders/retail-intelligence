# Spark smoke-test video

`hong-kong-passageway.mp4` is the only approved input for the initial DGX Spark RT-VLM smoke test.
It is a 10.777433-second, silent H.264 derivative of the full Wikimedia Commons video
[Pasejo en Hong Kong Island (2014)](https://commons.wikimedia.org/wiki/File:Pasejo_en_Hong_Kong_Island_(2014).webm).

## Provenance and terms

- Creator: Wikimedia Commons user [RG72](https://commons.wikimedia.org/wiki/User:RG72)
- Source date: October 20, 2014
- Source file: `Pasejo en Hong Kong Island (2014).webm`, SHA-256
  `5d15fffccf4ffbc95c8a1a56f7a7f83373bdfee162118192e38e9cb4b82da894`
- License: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
- Changes: the entire source video was resized from 1920×1080 to 960×540, transcoded from VP8 to
  H.264/yuv420p, stripped of audio and metadata, and packaged as MP4. No time range was removed.
- Fixture SHA-256: `8fef7d87a037714d2fc97f19faeac28a3ea41912d00fcced7032cc0674153dd4`

The creator published this footage as their own work under CC BY-SA 4.0. That license permits
redistribution and adaptation with attribution, a license link, identification of changes, and the
same license on the derivative. This fixture is distributed under those terms. It is a wide shot of
a public passageway: people remain distant, no face is shown close up, and no sensitive behavior is
visible.

## Expected observations

Record these expectations before model inference. A broadly sensible caption should recognize that:

- the camera moves forward through a brightly lit indoor shopping passageway with glass storefronts;
- one person ahead of the camera walks away and toward the left side of the passageway; and
- other people may appear far in the distance.

The generated caption does not need to use these exact words. Do not infer identity, intent, or a
specific retail interaction from this clip.

## Preflight

From the repository root, run:

```bash
python3 scripts/preflight_smoke_video.py
```

The command requires `ffmpeg` and `ffprobe`. It checks the exact checksum and media metadata,
completely decodes all 323 frames, confirms at least 80 distinct decoded frames, verifies that 80
evenly spaced source-frame indices contain no duplicates, and confirms the 448×448 request consumes
7,840 visual tokens.
