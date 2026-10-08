# recording_samples/

Representative audio samples used for demos, manual testing, and forensic analysis in the Dhwani AI app.

## Layout

```
recording_samples/
└── demo/      ← Audio clips used in Voice Engine → Forensic Analysis demo scenarios
```

## Files in demo/

| File | Type | Description |
|------|------|-------------|
| `ElevenLabs_*.mp3` | Synthetic (ElevenLabs TTS) | High-confidence AI-generated voice — score ~93 |
| `hi--my-name-is-priyanshu--and-.wav` | Human | Real human speaker sample |
| `i-didn-t-expect-the-day-to-tur.wav` | Human | Real human speaker sample |
| `you-know-what-i-find-interesti.wav` | Human | Real human speaker sample |
| `test.wav` | Mixed | General test fixture |

## Notes

- These files are **not** used by automated unit tests. Unit-test audio fixtures live in `services/api/tests/fixtures/audio/`.
- Files here are selected to demonstrate the three canonical forensic cases:
  1. ElevenLabs synthetic (~93 risk score → HIGH)
  2. Ambient/degraded recording (~73 risk score → MEDIUM)
  3. Clean human voice (~12 risk score → LOW)
