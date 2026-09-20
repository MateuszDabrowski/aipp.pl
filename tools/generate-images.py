#!/usr/bin/env python3
"""Generate the web image derivatives for aipp.pl from full-resolution originals.

Usage:
    python3 tools/generate-images.py [--src ~/Pictures/aipp] [--out obrazy/galeria] [--thumbs name,...] [name ...]

Reads <src>/<name>.jpg (all of them when no names are given) and writes:
    <out>/900/<name>.webp  <out>/1350/<name>.webp  <out>/1800/<name>.webp   (WebP, quality 80)
    <out>/900/<name>.jpg   <out>/1800/<name>.jpg                            (progressive JPEG fallback)
    <out>/450/<name>.webp  <out>/450/<name>.jpg   only for names listed in --thumbs (gallery thumbnails)

Colour: Adobe RGB originals are converted to sRGB, EXIF rotation is applied, metadata is dropped.
Requires Pillow (pip install Pillow) and cwebp (brew install webp).
"""
import argparse, io, os, subprocess, sys, tempfile
from multiprocessing import Pool
from PIL import Image, ImageCms, ImageOps

WEBP_WIDTHS = (900, 1350, 1800)
JPEG_WIDTHS = (900, 1800)
THUMB_WIDTH = 450
QUALITY = 80

def load(path):
    im = ImageOps.exif_transpose(Image.open(path))
    icc = im.info.get('icc_profile')
    if icc:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if 'sRGB' not in (ImageCms.getProfileDescription(src) or ''):
            im = ImageCms.profileToProfile(im, src, ImageCms.createProfile('sRGB'), outputMode='RGB')
    return im.convert('RGB')

def resized(im, width, previous_width):
    """Downscale to `width`. An original narrower than `width` is emitted once, at its native size,
    in the first tier above it (so the HTML can still offer the largest version available)."""
    if im.width >= width:
        return im if im.width == width else im.resize((width, round(im.height * width / im.width)), Image.LANCZOS, reducing_gap=3.0)
    return im if im.width > previous_width else None

def write_webp(im, dest):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        im.save(tmp.name, 'PNG', compress_level=1)
    try:
        subprocess.run(['cwebp', '-quiet', '-q', str(QUALITY), '-m', '6', '-sharp_yuv', '-metadata', 'none', tmp.name, '-o', dest], check=True)
    finally:
        os.unlink(tmp.name)

def process(job):
    name, src, out, is_thumb = job
    im = load(os.path.join(src, name + '.jpg'))
    written = []
    widths = set(WEBP_WIDTHS) | set(JPEG_WIDTHS) | ({THUMB_WIDTH} if is_thumb else set())
    previous = 0
    for w in sorted(widths):
        small = resized(im, w, previous)
        previous = w
        if small is None:
            continue
        os.makedirs(os.path.join(out, str(w)), exist_ok=True)
        if w in WEBP_WIDTHS or (is_thumb and w == THUMB_WIDTH):
            p = os.path.join(out, str(w), name + '.webp'); write_webp(small, p); written.append(p)
        if w in JPEG_WIDTHS or (is_thumb and w == THUMB_WIDTH):
            p = os.path.join(out, str(w), name + '.jpg'); small.save(p, 'JPEG', quality=QUALITY, progressive=True, optimize=True); written.append(p)
    return name, im.size, [(os.path.relpath(p, out), os.path.getsize(p)) for p in written]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=os.path.expanduser('~/Pictures/aipp'))
    ap.add_argument('--out', default='obrazy/galeria')
    ap.add_argument('--thumbs', default='', help='comma-separated names that also need a 450px thumbnail')
    ap.add_argument('names', nargs='*')
    a = ap.parse_args()
    names = a.names or sorted(f[:-4] for f in os.listdir(a.src) if f.lower().endswith('.jpg'))
    thumbs = set(filter(None, a.thumbs.split(',')))
    missing = [n for n in names if not os.path.exists(os.path.join(a.src, n + '.jpg'))]
    if missing:
        sys.exit('missing originals: ' + ', '.join(missing))
    jobs = [(n, a.src, a.out, n in thumbs) for n in names]
    total = 0
    with Pool() as pool:
        for name, size, files in pool.imap_unordered(process, jobs):
            total += sum(s for _, s in files)
            print(f'{name:24} {size[0]}x{size[1]:<5} ' + '  '.join(f'{os.path.dirname(p)}/{p.split(".")[-1]}={s//1024}K' for p, s in files))
    print(f'\n{len(names)} photos, {total/1048576:.1f} MB written to {a.out}')

if __name__ == '__main__':
    main()
