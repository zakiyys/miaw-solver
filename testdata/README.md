# Test fixtures

A small, deterministic fixture set so the test suite behaves the same everywhere.

| File | Purpose |
|---|---|
| `sample.png` | Plain text image, used by the image round-trip test |
| `captcha_like.png` | Distorted-text image used in the tests and the README proof section |
| `audio_4c7n.wav` | Speech sample saying `"4 c 7 n"`; exercises the audio worker |

The audio fixture is generated (not recorded) so it carries no personal data:

```bash
python scripts/make_audio_fixture.py "4 c 7 n" testdata/audio_4c7n.wav
```

It needs `edge-tts` or `espeak-ng` plus `ffmpeg` to produce 16 kHz mono WAV,
which is what the speech model expects. The generated file is small enough to
commit; the generator means anyone can reproduce or replace it.
