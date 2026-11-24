#!/usr/bin/env python3
"""Build the Morse Code Pack resource pack and quick-actions datapack.

Run ``python build_all.py --help`` and see README.md for installation,
encoding details, and the limitations of resource packs and Narrator.
"""

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
import wave
import zipfile
from functools import lru_cache


ROOT = Path(__file__).resolve().parent
INTERNATIONAL = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "._ _... _._. _.. . .._. __. .... .. .___ _._ ._.. __ _. "
    "___ .__. __._ ._. ... _ ...._ .._ ..._ .__ _.._ _.__ __.. "
    "_____ .____ ..___ ...__ ...._ ..... _.... __... ___.. ____.".split(),
))
INTERNATIONAL.update({
    ".": "._._._", ",": "__..__", "?": "..__..", "!": "_._.__",
    "-": "_...._", "/": "_.._.", ":": "___...", "(": "_.__.",
    ")": "_.__._", "'": ".____.", '"': "._.._.", "=": "_..._",
    "+": "._._.", "@": ".__._.", ";": "_._._.",
})

# The 26 basic Hangul telegraph assignments. Compound forms are expanded.
KOREAN = dict(zip(
    "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣㅐㅔ",
    "._.. .._. _... ..._ __ .__ __. _._ .__. _._. _.._ __.. "
    "___ .___ . .. _ ... ._ _. .... ._. _.. .._ __._ _.__".split(),
))
COMPOUNDS = {
    "ㄲ": "ㄱㄱ", "ㄸ": "ㄷㄷ", "ㅃ": "ㅂㅂ", "ㅆ": "ㅅㅅ", "ㅉ": "ㅈㅈ",
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ",
    "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ",
    "ㅄ": "ㅂㅅ", "ㅒ": "ㅑㅣ", "ㅖ": "ㅕㅣ", "ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ",
    "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
}
INITIAL = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
MEDIAL = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
FINAL = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
         "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
         "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")
CONJOINING = dict(zip(
    [chr(i) for i in range(0x1100, 0x1113)]
    + [chr(i) for i in range(0x1161, 0x1176)]
    + [chr(i) for i in range(0x11A8, 0x11C3)],
    list(INITIAL) + list(MEDIAL) + list(FINAL[1:]),
))
PROTECTED = re.compile(r"(%(?:\d+\$)?[sd]|%%|%n|§[^\r\n]|\\n|\r\n|\r|\n)")
LOCALE_NAME = re.compile(r"^[a-z0-9_]+\.json$")
ERROR_SIGNAL = "........"


def jamo_codes(jamo):
    """Return one Morse group per basic jamo, expanding compound forms."""
    return [KOREAN[part] for part in COMPOUNDS.get(jamo, jamo)]


@lru_cache(maxsize=16384)
def char_codes(char):
    """Map a character to groups; unmapped Unicode uses an explicit escape."""
    number = ord(char)
    if 0xAC00 <= number <= 0xD7A3:
        offset = number - 0xAC00
        parts = (INITIAL[offset // 588], MEDIAL[(offset % 588) // 28],
                 FINAL[offset % 28])
        return tuple(code for part in parts if part for code in jamo_codes(part))
    jamo = CONJOINING.get(char, char)
    # Normalize halfwidth Hangul only, not arbitrary characters or punctuation.
    if 0xFFA0 <= number <= 0xFFDC:
        normalized = unicodedata.normalize("NFKC", char)
        jamo = CONJOINING.get(normalized, normalized)
    if jamo in KOREAN or jamo in COMPOUNDS:
        return tuple(jamo_codes(jamo))
    if char.isascii() and char.upper() in INTERNATIONAL:
        return (INTERNATIONAL[char.upper()],)
    # Eight dots are an error/prosign, not one of our ordinary character codes.
    # Follow it with exactly six International Morse hex digits.
    return (ERROR_SIGNAL,) + tuple(INTERNATIONAL[digit] for digit in f"{number:06X}")


def encode(text):
    """Preserve Minecraft format tokens and render individually spaced signals."""
    pieces = []
    for part in PROTECTED.split(text):
        if not part:
            continue
        if PROTECTED.fullmatch(part):
            pieces.append(part)
            continue
        for char in part:
            if char.isspace():
                pieces.append("/")
            else:
                pieces.extend(" ".join(code) for code in char_codes(char))
    # Three spaces distinguish character/jamo groups from individual signals.
    # Newline characters remain exactly intact, including CRLF and literal \\n.
    output = []
    previous = ""
    for piece in pieces:
        if previous and previous not in ("\n", "\r", "\r\n", "\\n") and piece not in ("\n", "\r", "\r\n", "\\n"):
            output.append("   ")
        output.append(piece)
        previous = piece
    return "".join(output)


def read_json(path):
    with path.open(encoding="utf-8-sig") as file:
        return json.load(file)


def validate_language(value, source):
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(text, str)
        for key, text in value.items()
    ):
        raise ValueError(f"{source}: expected a JSON object of string values")
    return value


def local_languages(minecraft, version):
    """Read the selected launcher's local asset index and client JAR."""
    versions = minecraft / "versions"
    if not version:
        version = latest_installed_release(minecraft)
    if Path(version).name != version or version in ("", ".", ".."):
        raise ValueError("Version must be a version directory name.")
    metadata = read_json(versions / version / (version + ".json"))
    index_id = metadata.get("assetIndex", {}).get("id")
    if not isinstance(index_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", index_id):
        raise ValueError(f"{version}: no valid asset index ID in version metadata")
    index_path = minecraft / "assets" / "indexes" / (index_id + ".json")
    index = read_json(index_path)
    languages = {}
    for name, info in sorted(index["objects"].items()):
        prefix = "minecraft/lang/"
        if not name.startswith(prefix):
            continue
        locale = name[len(prefix):]
        if locale == "deprecated.json" or not LOCALE_NAME.fullmatch(locale):
            continue
        digest = info["hash"]
        if not re.fullmatch(r"[0-9a-f]{40}", digest):
            raise ValueError(f"Invalid asset hash for {name}")
        source = minecraft / "assets" / "objects" / digest[:2] / digest
        languages[locale] = validate_language(read_json(source), source)
    jar_path = versions / version / (version + ".jar")
    with zipfile.ZipFile(jar_path) as jar:
        for name in jar.namelist():
            prefix = "assets/minecraft/lang/"
            if (name.startswith(prefix) and name[len(prefix):] != "deprecated.json"
                    and LOCALE_NAME.fullmatch(name[len(prefix):])):
                locale = name[len(prefix):]
                # The client JAR supplies en_us; indexed translations take priority.
                if locale not in languages:
                    languages[locale] = validate_language(
                        json.loads(jar.read(name).decode("utf-8-sig")), f"{jar_path}: {name}"
                    )
    if not languages:
        raise ValueError(f"No Minecraft language files found for {version}")
    print(f"Loaded {len(languages)} languages from Minecraft {version} (asset index {index_id}).")
    return languages


def latest_installed_release(minecraft):
    candidates = []
    versions = minecraft / "versions"
    for directory in versions.iterdir():
        metadata_path = directory / (directory.name + ".json")
        if not directory.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = read_json(metadata_path)
            version_id = metadata.get("id", "")
            if (metadata.get("type") == "release"
                    and metadata.get("assetIndex", {}).get("id")
                    and (versions / version_id / (version_id + ".jar")).is_file()
                    and (minecraft / "assets" / "indexes" /
                         (metadata["assetIndex"]["id"] + ".json")).is_file()):
                candidates.append((metadata.get("releaseTime", ""), version_id))
        except (OSError, ValueError, TypeError):
            continue
    if not candidates:
        raise ValueError("No complete installed release found; specify --version.")
    return max(candidates)[1]


def load_languages(input_dir, minecraft, version, extract_local):
    languages = local_languages(minecraft, version) if extract_local else {}
    if input_dir.exists():
        if not input_dir.is_dir():
            raise ValueError(f"Not a directory: {input_dir}")
        for path in sorted(input_dir.glob("*.json")):
            if not LOCALE_NAME.fullmatch(path.name):
                raise ValueError(f"Invalid Minecraft locale filename: {path.name}")
            languages[path.name] = validate_language(read_json(path), path)
    if not languages:
        raise ValueError(f"No language JSON files in {input_dir}; use --extract-local or supply files.")
    if "en_us.json" not in languages:
        raise ValueError("en_us.json is required for Minecraft's English fallback.")
    return languages


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_wav(path, duration):
    rate = 44100
    count = round(rate * duration)
    fade = round(rate * 0.01)
    samples = bytearray()
    for i in range(count):
        envelope = min(1.0, i / fade, (count - 1 - i) / fade)
        sample = round(0.5 * 32767 * envelope * math.sin(2 * math.pi * 700 * i / rate))
        samples.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(samples)


def encode_ogg(wav, output):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(wav),
             "-c:a", "libvorbis", str(output)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        ffmpeg_error = result.stderr.strip()
    else:
        ffmpeg_error = "ffmpeg not found"
    try:
        import soundfile
    except ImportError as error:
        raise RuntimeError(f"OGG encoding failed ({ffmpeg_error}); install ffmpeg with libvorbis or soundfile.") from error
    try:
        data, rate = soundfile.read(str(wav), dtype="int16")
        soundfile.write(str(output), data, rate, format="OGG", subtype="VORBIS")
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeError(f"OGG encoding failed: ffmpeg: {ffmpeg_error}; soundfile: {error}") from error


def pack_meta(pack_version, pack_type, description):
    """Build pack.mcmeta from the version.json pack_version schema."""
    legacy_key = "resource" if pack_type == "resource" else "data"
    major_key = legacy_key + "_major"
    if major_key in pack_version:
        major = pack_version[major_key]
        minor = pack_version[legacy_key + "_minor"]
        return {"pack": {
            "min_format": [major, minor],
            "max_format": major,
            "description": description,
        }}
    pack_format = pack_version[legacy_key]
    return {"pack": {
        "pack_format": pack_format,
        "supported_formats": [pack_format, pack_format],
        "description": description,
    }}


def version_pack_data(minecraft, version):
    if Path(version).name != version or version in ("", ".", ".."):
        raise ValueError("Target version must be a version directory name.")
    jar_path = minecraft / "versions" / version / (version + ".jar")
    try:
        with zipfile.ZipFile(jar_path) as jar:
            metadata = json.loads(jar.read("version.json").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError(
            f"Cannot read pack formats for Minecraft {version} from {jar_path}"
        ) from error
    pack_version = metadata.get("pack_version")
    if not isinstance(pack_version, dict):
        raise ValueError(f"{jar_path}: version.json has no pack_version object")
    modern = "resource_major" in pack_version and "data_major" in pack_version
    legacy = "resource" in pack_version and "data" in pack_version
    if not modern and not legacy:
        raise ValueError(f"{jar_path}: unsupported pack_version schema")
    expected = ("resource_major", "resource_minor", "data_major", "data_minor") if modern else ("resource", "data")
    if any(type(pack_version.get(key)) is not int or pack_version[key] < 0 for key in expected):
        raise ValueError(f"{jar_path}: invalid pack_version values")
    return pack_version


def build_resource_pack(root, languages, scratch, pack_version):
    write_json(root / "pack.mcmeta", pack_meta(pack_version, "resource", "Morse Code Pack"))
    lang_dir = root / "assets" / "minecraft" / "lang"
    for name, data in sorted(languages.items()):
        print(f"Encoding {name} ({len(data)} entries)...", flush=True)
        write_json(lang_dir / name, {key: encode(value) for key, value in data.items()})
    sounds_dir = root / "assets" / "minecraft" / "sounds" / "morse"
    sounds_dir.mkdir(parents=True)
    for name, duration in (("dit", 0.08), ("dah", 0.24)):
        wav = scratch / (name + ".wav")
        write_wav(wav, duration)
        encode_ogg(wav, sounds_dir / (name + ".ogg"))
    events = {
        "ui.button.click": ("dit", None),
        "entity.item.pickup": ("dit", "subtitles.entity.item.pickup"),
        "entity.experience_orb.pickup": ("dit", "subtitles.entity.experience_orb.pickup"),
        "ui.toast.in": ("dah", None),
        "ui.toast.out": ("dit", None),
    }
    write_json(root / "assets" / "minecraft" / "sounds.json", {
        event: {"replace": True, "sounds": ["minecraft:morse/" + sound],
                **({"subtitle": subtitle} if subtitle else {})}
        for event, (sound, subtitle) in events.items()
    })


def build_datapack(root, pack_version):
    write_json(root / "pack.mcmeta", pack_meta(pack_version, "data", "Morse Code Pack"))
    write_json(root / "data" / "minecraft" / "tags" / "dialog" / "quick_actions.json",
               {"values": ["morse_code:cheat_sheet"]})
    sections = [
        ("Korean consonants", "ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"),
        ("Korean vowels", MEDIAL),
        ("English", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        ("Numbers", "0123456789"),
    ]
    body = []
    for heading, chars in sections:
        lines = [heading] + [
            f"{char}  {' '.join(jamo_codes(char)) if char in KOREAN or char in COMPOUNDS else INTERNATIONAL[char]}"
            for char in chars
        ]
        body.append({"type": "minecraft:plain_message", "width": 200,
                     "contents": {"text": "\n".join(lines)}})
    write_json(root / "data" / "morse_code" / "dialog" / "cheat_sheet.json", {
        "type": "minecraft:notice",
        "title": {"text": "Morse Code Cheat Sheet"},
        "body": body,
        "action": {"label": {"text": "Close"}},
    })


def default_minecraft_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / ".minecraft"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "minecraft"
    return Path.home() / ".minecraft"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-lang", type=Path, default=ROOT / "input_lang",
                        help="Directory of locale JSON files (default: input_lang beside this script).")
    parser.add_argument("--extract-local", action="store_true",
                        help="Read installed client asset objects and English from its JAR.")
    parser.add_argument("--minecraft-dir", type=Path, default=default_minecraft_dir(),
                        help="Minecraft game directory used with --extract-local.")
    parser.add_argument("--version", help="Installed release version; default: latest complete release.")
    parser.add_argument("--target-version",
                        help="Minecraft version whose pack format is used (default: --version or 26.3).")
    parser.add_argument("--output", type=Path, default=ROOT,
                        help="Parent directory for the two generated packs.")
    args = parser.parse_args(argv)
    if args.version and not args.extract_local:
        parser.error("--version requires --extract-local")
    args.output.mkdir(parents=True, exist_ok=True)
    destinations = [args.output / "Morse_Code_Pack_RP", args.output / "Morse_Code_Pack_DP"]
    for destination in destinations:
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing pack: {destination}. Choose a new --output.")
    target_version = args.target_version or args.version or (
        latest_installed_release(args.minecraft_dir) if args.extract_local else "26.3"
    )
    pack_version = version_pack_data(args.minecraft_dir, target_version)
    languages = load_languages(args.input_lang, args.minecraft_dir, args.version, args.extract_local)
    with tempfile.TemporaryDirectory(prefix="morse_code_", dir=args.output) as temporary:
        staging = Path(temporary)
        rp = staging / "Morse_Code_Pack_RP"
        dp = staging / "Morse_Code_Pack_DP"
        build_resource_pack(rp, languages, staging, pack_version)
        build_datapack(dp, pack_version)
        # Rename rather than merge: never overwrite an existing pack.
        rp.rename(destinations[0])
        dp.rename(destinations[1])
    print(f"Built {len(languages)} languages and both packs in {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        sys.exit(1)
