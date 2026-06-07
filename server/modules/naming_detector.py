"""Plexarr — Naming Variations Detector

Detects and strips 100+ naming group variations, release tags, and source identifiers.
Handles cases like "MediaHub-eng", "Pahe.in", "HorribleSubs", and many variations.
"""
import re
from typing import List, Set, Dict
from modules.config import config


# Known naming group variations and their regex patterns
NAMING_VARIATIONS = [
    # Release groups
    (r'\[?\s*MediaHub\s*\]?\s*-?\s*eng\s*', 'MediaHub'),
    (r'\[?\s*Pahe\.?in\s*\]?', 'Pahe'),
    (r'\[?\s*HorribleSubs\s*\]?', 'HorribleSubs'),
    (r'\[?\s*Erai-?raws\s*\]?', 'Erai-raws'),
    (r'\[?\s*SubsPlease\s*\]?', 'SubsPlease'),
    (r'\[?\s*Judas\s*\]?', 'Judas'),
    (r'\[?\s*YTS\s*\]?', 'YTS'),
    (r'\[?\s*YIFY\s*\]?', 'YIFY'),
    (r'\[?\s*RARBG\s*\]?', 'RARBG'),
    (r'\[?\s*AMZN\s*\]?', 'AMZN'),
    (r'\[?\s*NF\s*\]?', 'NF'),
    (r'\[?\s*Hulu\s*\]?', 'Hulu'),
    (r'\[?\s*CR\s*\]?', 'CR'),
    (r'\[?\s*Funimation\s*\]?', 'Funimation'),
    (r'\[?\s*HIDIVE\s*\]?', 'HIDIVE'),
    (r'\[?\s*VRV\s*\]?', 'VRV'),
    (r'\[?\s*DameDesuYo\s*\]?', 'DameDesuYo'),
    (r'\[?\s*GJM\s*\]?', 'GJM'),
    (r'\[?\s*Kametsu\s*\]?', 'Kametsu'),
    (r'\[?\s*Asenshi\s*\]?', 'Asenshi'),
    (r'\[?\s*FFF\s*\]?', 'FFF'),
    (r'\[?\s*Commie\s*\]?', 'Commie'),
    (r'\[?\s*Ohys-?Raws\s*\]?', 'Ohys-Raws'),
    (r'\[?\s*Leopard-?Raws\s*\]?', 'Leopard-Raws'),
    (r'\[?\s*LoliHouse\s*\]?', 'LoliHouse'),
    (r'\[?\s*ARC\s*\]?', 'ARC'),
    (r'\[?\s*Vivid\s*\]?', 'Vivid'),
    (r'\[?\s*Tenrai\s*\]?', 'Tenrai'),
    (r'\[?\s*deanzel\s*\]?', 'deanzel'),
    (r'\[?\s*AnimeKaizoku\s*\]?', 'AnimeKaizoku'),
    (r'\[?\s*HakataRamune\s*\]?', 'HakataRamune'),
    (r'\[?\s*Akihito\s*\]?', 'Akihito'),
    (r'\[?\s*Rare\s*\]?', 'Rare'),
    (r'\[?\s*SallySubs\s*\]?', 'SallySubs'),
    (r'\[?\s*UWEB\s*\]?', 'UWEB'),
    (r'\[?\s*PSA\s*\]?', 'PSA'),
    (r'\[?\s*ZHORROR\s*\]?', 'ZHORROR'),
    (r'\[?\s*HS\s*\]?', 'HS'),
    (r'\[?\s*BD\s*\]?', 'BD'),
    (r'\[?\s*OVA\s*\]?', 'OVA'),
    (r'\[?\s*ONA\s*\]?', 'ONA'),
    (r'\[?\s*Specials?\s*\]?', 'Specials'),
    (r'\[?\s*Batch\s*\]?', 'Batch'),
    (r'\[?\s*Complete\s*\]?', 'Complete'),
    (r'\[?\s*RAW\s*\]?', 'RAW'),
    (r'\[?\s*Dual\s*Audio\s*\]?', 'DualAudio'),
    (r'\[?\s*Multi-?Sub\s*\]?', 'MultiSub'),
    (r'\[?\s*ESub\s*\]?', 'ESub'),
    (r'\[?\s*HC\s*\]?', 'HC'),
    (r'\[?\s*KORSUB\s*\]?', 'KORSUB'),
    (r'\[?\s*SUBBED\s*\]?', 'SUBBED'),
    (r'\[?\s*DUBBED\s*\]?', 'DUBBED'),
    (r'\[?\s*REPACK\s*\]?', 'REPACK'),
    (r'\[?\s*PROPER\s*\]?', 'PROPER'),
    (r'\[?\s*Extended\s*\]?', 'Extended'),
    (r'\[?\s*UNCUT\s*\]?', 'UNCUT'),
    (r'\[?\s*Directors\s*Cut\s*\]?', 'DirectorsCut'),
    (r'\[?\s*IMAX\s*\]?', 'IMAX'),
    (r'\[?\s*Atmos\s*\]?', 'Atmos'),
    (r'\[?\s*DV\s*\]?', 'DV'),
    (r'\[?\s*DoVi\s*\]?', 'DoVi'),
    (r'\[?\s*HDR10\s*\]?', 'HDR10'),
    (r'\[?\s*HDR\s*\]?', 'HDR'),
    (r'\[?\s*Hi10\s*\]?', 'Hi10'),
    (r'\[?\s*10-?bit\s*\]?', '10bit'),
    (r'\[?\s*8-?bit\s*\]?', '8bit'),
    (r'\[?\s*Lossless\s*\]?', 'Lossless'),
    (r'\[?\s*720p\s*\]?', '720p'),
    (r'\[?\s*1080p\s*\]?', '1080p'),
    (r'\[?\s*2160p\s*\]?', '2160p'),
    (r'\[?\s*4K\s*\]?', '4K'),
    (r'\[?\s*UHD\s*\]?', 'UHD'),
    (r'\[?\s*x264\s*\]?', 'x264'),
    (r'\[?\s*x265\s*\]?', 'x265'),
    (r'\[?\s*HEVC\s*\]?', 'HEVC'),
    (r'\[?\s*AVC\s*\]?', 'AVC'),
    (r'\[?\s*H264\s*\]?', 'H264'),
    (r'\[?\s*H265\s*\]?', 'H265'),
    (r'\[?\s*AAC\s*\]?', 'AAC'),
    (r'\[?\s*MP3\s*\]?', 'MP3'),
    (r'\[?\s*FLAC\s*\]?', 'FLAC'),
    (r'\[?\s*AC3\s*\]?', 'AC3'),
    (r'\[?\s*DTS\s*\]?', 'DTS'),
    (r'\[?\s*Blu-?Ray\s*\]?', 'BluRay'),
    (r'\[?\s*WEB-?DL\s*\]?', 'WEBDL'),
    (r'\[?\s*WEB-?DLMux\s*\]?', 'WEBDLMux'),
    (r'\[?\s*WEBRip\s*\]?', 'WEBRip'),
    (r'\[?\s*DVDRip\s*\]?', 'DVDRip'),
    (r'\[?\s*BDRip\s*\]?', 'BDRip'),
    (r'\[?\s*HDTV\s*\]?', 'HDTV'),
]


def detect_variations(name: str) -> List[Dict]:
    """Detect naming variations in a filename and return list of matches."""
    found = []
    for pattern, group_name in NAMING_VARIATIONS:
        for match in re.finditer(pattern, name, re.IGNORECASE):
            found.append({
                "group": group_name,
                "match": match.group(),
                "start": match.start(),
                "end": match.end()
            })
    return found


def strip_all_variations(name: str) -> str:
    """Strip all known naming variations from a filename."""
    clean = name
    for pattern, group_name in NAMING_VARIATIONS:
        clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
    # Clean up artifacts
    clean = re.sub(r'\[\]', '', clean)
    clean = re.sub(r'\(\)', '', clean)
    clean = re.sub(r'\{\}', '', clean)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip(' -_.')


def detect_custom_variations(name: str) -> List[Dict]:
    """Detect custom variations from config."""
    custom = config.get("naming.variations", [])
    found = []
    for var in custom:
        pattern = re.escape(var)
        for match in re.finditer(pattern, name, re.IGNORECASE):
            found.append({
                "group": var,
                "match": match.group(),
                "start": match.start(),
                "end": match.end()
            })
    return found


def full_strip(name: str) -> str:
    """Strip all built-in + custom variations."""
    clean = strip_all_variations(name)
    custom = detect_custom_variations(name)
    for c in custom:
        clean = clean.replace(c["match"], ' ')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip(' -_.')
