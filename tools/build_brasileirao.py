#!/usr/bin/env python3
"""Build publicly downloadable immutable Brasileirão packages from verified metadata.

Existing World Cup packages are preserved. Sources use approved cover URLs,
and 2024 explicitly exposes provisional identifiers in its album description.
"""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"sources"
OUT=ROOT/"albums"
OUT.mkdir(exist_ok=True)
covers=json.loads((SRC/"capas-aprovadas-brasileirao.json").read_text(encoding="utf-8"))["urls"]
old=json.loads((ROOT/"packages.json").read_text(encoding="utf-8"))
assert old["schemaVersion"]==1
preserved=[entry for entry in old["albums"] if not str(entry["officialId"]).startswith("panini.brasileirao")]
assert len(preserved)==9, f"Unexpected number of previous packages: {len(preserved)}"
assert all((ROOT/e["file"]).is_file() for e in preserved)
session=requests.Session()
session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; MeuAlbumFigurinhas/1.0; research)"})
updated=[]
for year in range(1996,2025):
    record=json.loads((SRC/f"brasileirao_{year}.json").read_text(encoding="utf-8"))
    stickers=record["stickers"]
    assert record["officialId"]==f"panini.brasileirao{year}.standard"
    assert record["plannedTotal"]==len(stickers)
    assert len({s["id"] for s in stickers})==len(stickers)
    assert len({s["number"].strip().casefold() for s in stickers})==len(stickers)
    secids={s["id"] for s in record["sections"]}
    assert all(s["sectionId"] in secids for s in stickers)
    assert record.get("releaseReady") is True,(year,"Not approved")
    if year==2024:
        assert len(stickers)==814 and sum(s["number"].startswith("U1-") for s in stickers)==60
        assert sum(s["number"].startswith("U2-") for s in stickers)==70
        assert "provisório" in record["description"].lower()
    url=covers[str(year)]
    try:
        response=session.get(url,timeout=35);response.raise_for_status()
    except requests.RequestException:
        if "online.anyflip.com" not in url:raise
        response=session.get("https://wsrv.nl/?url="+quote(url.removeprefix("https://"),safe=""),timeout=35)
        response.raise_for_status()
    assert len(response.content)<7*1024*1024
    with Image.open(io.BytesIO(response.content)) as im:
        assert im.width>=125 and im.height>=160
        im=ImageOps.exif_transpose(im)
        im.thumbnail((720,980))
        cover=io.BytesIO()
        im.convert("RGB").save(cover,"JPEG",quality=79,optimize=True,progressive=True)
    binary=cover.getvalue()
    name=f"panini-brasileirao-{year}-standard-v1.zip"
    path=OUT/name
    payload=(json.dumps(record,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        z.writestr("album.json",payload)
        z.writestr(f"imagens/brasileirao_{year}/capa.jpg",binary)
    raw=path.read_bytes()
    assert len(raw)<8*1024*1024
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist())==2
        assert json.loads(z.read("album.json"))["plannedTotal"]==len(stickers)
    updated.append({"officialId":record["officialId"],"version":record["version"],
                    "file":f"albums/{name}","bytes":len(raw),
                    "sha256":hashlib.sha256(raw).hexdigest()})
    print(year,len(stickers),len(binary),len(raw),flush=True)
assert len(updated)==29
merged=preserved+updated
assert len(merged)==38 and len({r["officialId"] for r in merged})==38
(ROOT/"packages.json").write_text(json.dumps({"schemaVersion":1,"albums":merged},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("SUCCESS: 9 historical packages retained + 29 Brasileirão packages, SHA-256 verified; 2024 provisional identifiers disclosed",flush=True)
