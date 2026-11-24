# Morse Code Pack

Minecraft Java 26.3. The generator also reads legacy pack formats from
installed Minecraft versions such as 1.21.7.

## Build

Install Python 3.9+ and either FFmpeg with its `libvorbis` encoder on PATH or
the Python `soundfile` package with OGG/Vorbis support. No network access is
needed. Run from this directory:

```powershell
python build_all.py --extract-local --version 26.3
```

Use an installed vanilla client version matching the game you intend to play.
Omit `--version` to choose the newest locally installed complete release.
`--minecraft-dir` selects a non-default game directory. `--target-version`
overrides the client version used to read pack formats; normally it should
match `--version`.
The launcher must already have downloaded that version's asset objects and
client JAR. Pack formats and `en_us.json` are read from that JAR; the other
languages are read from the asset index and local objects.

Alternatively, put Minecraft language JSON files including `en_us.json` in
`input_lang` beside the script and run `python build_all.py`. The default
target is 26.3, so its client JAR must be installed to read the pack formats.
Use `--target-version VERSION` to select a different installed target. Only
the provided locales are generated; missing locale keys fall back to English
in Minecraft. With `--extract-local`, files in `input_lang` override the
corresponding local locales. Input JSON must map keys to strings.

The script creates `Morse_Code_Pack_RP` and `Morse_Code_Pack_DP` beside itself. It
refuses to overwrite existing pack folders. To rebuild safely, choose a new
parent directory with `--output PATH`. Run `python build_all.py --help` for
options.

## Install

1. Copy `Morse_Code_Pack_RP` into `.minecraft/resourcepacks`, then enable it in
   **Options → Resource Packs**. Place it above conflicting packs.
2. Copy `Morse_Code_Pack_DP` into `.minecraft/saves/<world>/datapacks` or the
   server world's `datapacks` directory. Run `/reload` or restart the world.
3. Press **G**, the default Quick Actions key. If other packs register quick
   actions, select “Morse Code Cheat Sheet” from the list instead. The key can
   be rebound under Controls. The chart and Close button intentionally use
   literal readable text, not translated text.
4. Turn on subtitles in Accessibility Settings if desired. Set Narrator with
   Ctrl+B; choose the appropriate narration mode and an available system
   voice.

For Minecraft 26.3, the generated resource pack uses
`min_format: [97, 1]` / `max_format: 97`, and the datapack uses
`min_format: [121, 0]` / `max_format: 121`. These modern format fields replace
the old `pack_format` and `supported_formats` fields; the generator reads the
correct legacy or modern schema from the selected client JAR. Minecraft
changes pack formats and assets over time, so build against the exact game
version you intend to use.

## Encoding and limitations

* International Morse is used for ASCII letters, numbers, and supported
  punctuation; `_` is a dash. Hangul syllables are decomposed into their
  initial, medial and final jamo, with compound jamo expanded to basic Korean
  telegraph/SKATS signals. Conjoining, compatibility and halfwidth modern
  jamo are supported. The chart shows all modern compatibility jamo.
* Signals within a letter/jamo are separated by one space, groups by three
  spaces, and word spaces by `/`. Slashes in the source are encoded as
  punctuation, not as word separators. Minecraft format arguments, section
  codes, literal `\\n`, actual newlines, `%%`, and `%n` are retained.
* Japanese, Chinese, other scripts, accented characters, emoji and other
  unmapped characters are **not transliterated**. Each is represented by an
  eight-dot escape group followed by six International Morse hexadecimal
  digits containing its Unicode code point. This is a project-specific
  fallback, not standard Morse for those languages. For example, `日` is
  `........` followed by the Morse digits for `0065E5` (with each signal
  space-separated in the pack). It keeps the output Morse-only, but can make
  text very long.
* Spacing is intended to help TTS distinguish symbols. Narrator delegates
  pronunciation to the operating system's voice and punctuation settings:
  no resource pack can guarantee that every dot or underscore will be spoken.
  Narrator also does not necessarily narrate every interface element.
* Resource packs only replace supplied translation entries and the five
  selected sound events. They cannot transform arbitrary server messages,
  player chat, item names supplied as literal text, graphics, or dynamic
  placeholder values, and cannot synthesize a beep sequence for every
  displayed Morse letter. The sound replacements are short feedback cues, not
  spoken text or per-character Morse playback. Existing item and experience
  pickup subtitle keys are preserved.
* Long Morse strings may overflow Minecraft's fixed-size controls. The chart
  is scrollable and uses one entry per line.

Korean telegraph chart and compound expansion:
https://morsecodes.net/alphabet/korean

## 라이선스

이 프로젝트의 코드는 GPL-3.0-only 라이선스로 제공됩니다. 전체 라이선스
내용은 [GNU GPL 버전 3](https://www.gnu.org/licenses/gpl-3.0.txt)에서
확인할 수 있습니다. Minecraft 게임 및 해당 언어 파일은 별도 권리와
라이선스가 적용됩니다.
