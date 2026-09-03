# Asset catalog

Released assets use:

```text
assets/<DRUIID|HAZY>/<CATEGORY>/<PACK_NAME>/<VERSION>/
```

Allowed categories:

- `MIDI`
- `DRUMS`
- `SAMPLES`
- `SERUM2`
- `RACKS`
- `GROOVES`
- `TOOLS`

Every released version requires `manifest.json`, checksums, validation records, dependency/version metadata, and original material only. Binary assets are tracked with Git LFS. Do not commit local experiments or unvalidated native presets here.
