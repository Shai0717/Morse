import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

import build_all as build


class MorseTests(unittest.TestCase):
    def test_international_and_korean(self):
        self.assertEqual(build.char_codes("A"), ("._",))
        self.assertEqual(build.char_codes("/"), ("_.._.",))
        self.assertEqual(build.char_codes("한"), (".___", ".", ".._."))
        self.assertEqual(build.char_codes("값"), ("._..", ".", ".__", "__."))
        self.assertEqual(build.char_codes("ㄲ"), ("._..", "._.."))
        self.assertEqual(build.char_codes("ᆪ"), ("._..", "__."))
        self.assertEqual(build.char_codes("ﾡ"), ("._..",))
        self.assertEqual(build.encode("A B"), ". _   /   _ . . .")

    def test_preserves_formats_and_newlines(self):
        source = "A%1$s§a%d%%\\nB\n%s"
        result = build.encode(source)
        self.assertEqual(build.PROTECTED.findall(result), build.PROTECTED.findall(source))
        self.assertIn("\\n", result)
        self.assertIn("\n", result)

    def test_unknown_unicode_is_encoded_as_six_hex_digits(self):
        self.assertEqual(build.char_codes("日"), (build.ERROR_SIGNAL,) + tuple(
            build.INTERNATIONAL[c] for c in "0065E5"
        ))
        self.assertEqual(build.char_codes("😀"), (build.ERROR_SIGNAL,) + tuple(
            build.INTERNATIONAL[c] for c in "01F600"
        ))
        self.assertTrue(set(build.encode("日本語😀")) <= {".", "_", " "})

    def test_local_asset_index_and_jar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version = root / "versions" / "1.21.7"
            version.mkdir(parents=True)
            (version / "1.21.7.json").write_text(json.dumps({
                "id": "1.21.7", "type": "release",
                "releaseTime": "2025-01-01", "assetIndex": {"id": "26"},
            }), encoding="utf-8")
            with zipfile.ZipFile(version / "1.21.7.jar", "w") as jar:
                jar.writestr("assets/minecraft/lang/en_us.json", '{"key":"Hi"}')
                jar.writestr("assets/minecraft/lang/deprecated.json", '{"removed":["key"]}')
            digest = "a" * 40
            index = root / "assets" / "indexes" / "26.json"
            index.parent.mkdir(parents=True)
            index.write_text(json.dumps({"objects": {
                "minecraft/lang/ko_kr.json": {"hash": digest}
            }}), encoding="utf-8")
            blob = root / "assets" / "objects" / "aa" / digest
            blob.parent.mkdir(parents=True)
            blob.write_text('{"key":"한"}', encoding="utf-8")
            languages = build.local_languages(root, None)
            self.assertEqual(set(languages), {"en_us.json", "ko_kr.json"})
            self.assertEqual(languages["ko_kr.json"]["key"], "한")

    def test_pack_metadata_schemas(self):
        modern = {"resource_major": 97, "resource_minor": 1,
                  "data_major": 121, "data_minor": 0}
        self.assertEqual(build.pack_meta(modern, "resource", "rp"), {
            "pack": {"min_format": [97, 1], "max_format": 97, "description": "rp"}
        })
        self.assertEqual(build.pack_meta(modern, "data", "dp"), {
            "pack": {"min_format": [121, 0], "max_format": 121, "description": "dp"}
        })
        legacy = {"resource": 64, "data": 81}
        self.assertEqual(build.pack_meta(legacy, "resource", "rp"), {
            "pack": {"pack_format": 64, "supported_formats": [64, 64], "description": "rp"}
        })
        self.assertEqual(build.pack_meta(legacy, "data", "dp"), {
            "pack": {"pack_format": 81, "supported_formats": [81, 81], "description": "dp"}
        })

    @unittest.skipUnless(shutil.which("ffmpeg"), "integration test requires ffmpeg")
    def test_complete_build_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            source.mkdir()
            (source / "en_us.json").write_text('{"item":"Hi %s"}', encoding="utf-8")
            version_dir = root / "versions" / "26.3"
            version_dir.mkdir(parents=True)
            with zipfile.ZipFile(version_dir / "26.3.jar", "w") as jar:
                jar.writestr("version.json", json.dumps({"pack_version": {
                    "resource_major": 97, "resource_minor": 1,
                    "data_major": 121, "data_minor": 0,
                }}))
            out = root / "out"
            args = ["--input-lang", str(source), "--minecraft-dir", str(root), "--output", str(out)]
            build.main(args)
            rp, dp = out / "Morse_Code_Pack_RP", out / "Morse_Code_Pack_DP"
            self.assertEqual(json.loads((rp / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]["min_format"], [97, 1])
            self.assertEqual(json.loads((dp / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]["min_format"], [121, 0])
            self.assertEqual(json.loads((rp / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]["description"], "Morse Code Pack")
            self.assertEqual(json.loads((dp / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]["description"], "Morse Code Pack")
            language = json.loads((rp / "assets" / "minecraft" / "lang" / "en_us.json").read_text(encoding="utf-8"))
            self.assertEqual(language["item"], build.encode("Hi %s"))
            sounds = json.loads((rp / "assets" / "minecraft" / "sounds.json").read_text(encoding="utf-8"))
            self.assertEqual(sounds["entity.item.pickup"]["subtitle"], "subtitles.entity.item.pickup")
            self.assertTrue((rp / "assets" / "minecraft" / "sounds" / "morse" / "dit.ogg").read_bytes().startswith(b"OggS"))
            tag = json.loads((dp / "data" / "minecraft" / "tags" / "dialog" / "quick_actions.json").read_text(encoding="utf-8"))
            self.assertEqual(tag["values"], ["morse_code:cheat_sheet"])
            dialog = json.loads((dp / "data" / "morse_code" / "dialog" / "cheat_sheet.json").read_text(encoding="utf-8"))
            self.assertEqual(dialog["type"], "minecraft:notice")
            self.assertIn("ㄱ  ._..", dialog["body"][0]["contents"]["text"])
            with self.assertRaises(FileExistsError):
                build.main(args)


if __name__ == "__main__":
    unittest.main()
