#!/usr/bin/env python3
# Bake original PvZ1 .reanim part animations into packed WebP sprite strips.
#
# Reanim model (PvZ 2009 .reanim XML):
#   fps          12 for every stock animation
#   track/name   one channel; each <t> carries only the fields that CHANGED
#                (carry-forward into the next <t>)
#   x,y          position, y axis points UP, origin = character feet
#   sx,sy        scale, kx,ky skew, a rotation in degrees (CCW)
#   f            >=0 sprite visible, -1 sprite hidden
#   i            image symbol, e.g. IMAGE_REANIM_ZOMBIE_BODY
#   anim_*       track that only holds visibility markers: a run of f>=0 frames
#                between two f<0 frames is one loop of that animation
import json
import math
import os
import sys
import tarfile
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw

SRC = os.environ.get('REANIM_SRC', 'src_assets/reanim')
MODE = os.environ.get('MODE', 'samples')
SHEETS = os.environ.get('SHEETS', 'sheets')
MAX_W = 16000
TARGET_BYTES = 15 * 1024 * 1024
PAD = 2

SAMPLES = ['Chomper', 'PeaShooter', 'Zombie', 'Zombie_gargantuar', 'Zombie_paper', 'Zombie_bungi']
KEYCHARS = ['Zombie', 'Zombie_gargantuar', 'Zombie_boss', 'Zombie_paper', 'Zombie_bungi',
            'Zombie_balloon', 'Zombie_digger', 'Zombie_polevaulter', 'Zombie_jackbox',
            'Zombie_dancer', 'Chomper', 'PeaShooter', 'SunFlower', 'Wallnut', 'Cabbagepult']

FKEYS = ('x', 'y', 'a', 'sx', 'sy', 'kx', 'ky', 'f')
DEFAULTS = {'x': 0.0, 'y': 0.0, 'a': 0.0, 'sx': 1.0, 'sy': 1.0,
            'kx': 0.0, 'ky': 0.0, 'f': -1.0, 'i': None}


def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())


def read_reanim(path):
    raw = open(path, encoding='utf-8', errors='ignore').read()
    start = raw.find('<fps')
    if start < 0:
        start = raw.find('<track')
    body = raw[start:] if start > 0 else raw
    root = ET.fromstring('<reanim>' + body + '</reanim>')
    try:
        fps = float(root.findtext('fps') or 12)
    except ValueError:
        fps = 12.0
    tracks, order = {}, []
    for tr in root.findall('track'):
        name = (tr.findtext('name') or '').strip()
        frames = []
        for t in tr.findall('t'):
            fr = {}
            for ch in t:
                txt = (ch.text or '').strip()
                if ch.tag in FKEYS:
                    try:
                        fr[ch.tag] = float(txt)
                    except ValueError:
                        pass
                elif ch.tag == 'i' and txt:
                    fr['i'] = txt
            frames.append(fr)
        tracks[name] = frames
        order.append(name)
    return fps, tracks, order


def resolve(frames):
    cur = dict(DEFAULTS)
    out = []
    for fr in frames:
        for k, v in fr.items():
            if k in FKEYS:
                cur[k] = float(v)
            elif k == 'i':
                cur['i'] = v
        out.append(dict(cur))
    return out


def anim_spans(frames):
    spans, start = [], None
    for i, fr in enumerate(frames):
        if fr['f'] >= 0 and start is None:
            start = i
        elif fr['f'] < 0 and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(frames)))
    return spans


def build_index(src):
    index = {}
    for fn in sorted(os.listdir(src)):
        if fn.lower().endswith('.png'):
            index[norm(fn[:-4])] = os.path.join(src, fn)
    return index


_img_cache = {}


def load_img(path):
    if path not in _img_cache:
        _img_cache[path] = Image.open(path).convert('RGBA')
    return _img_cache[path]


def image_of(symbol, index):
    if not symbol:
        return None
    key = symbol[len('IMAGE_REANIM_'):] if symbol.startswith('IMAGE_REANIM_') else symbol
    return index.get(norm(key))


def corners(x, y, sx, sy, a, w, h):
    ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
    pts = []
    for px, py in ((0.0, 0.0), (w * sx, 0.0), (0.0, h * sy), (w * sx, h * sy)):
        pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
    return pts


def paste_part(canvas, part, x, y, sx, sy, a, ox, oy):
    w, h = part.size
    sw, sh = max(1, int(round(w * sx))), max(1, int(round(h * sy)))
    im = part if (sw, sh) == (w, h) else part.resize((sw, sh), Image.LANCZOS)
    if abs(a) > 0.01:
        im = im.rotate(-a, expand=True, resample=Image.BICUBIC)
        W, H = im.size
        dx, dy = -sw / 2.0, sh - sh / 2.0
        t = math.radians(-a)
        c, s = math.cos(t), math.sin(t)
        ax = W / 2.0 + dx * c - dy * s
        ay = H / 2.0 + dx * s + dy * c
    else:
        ax, ay = 0.0, float(sh)
    p = (int(round(ox + x - ax)), int(round(oy - y - ay)))
    if p[0] > canvas.size[0] or p[1] > canvas.size[1] or p[0] + im.size[0] < 0 or p[1] + im.size[1] < 0:
        return
    canvas.alpha_composite(im, p)


def visible(fr, forced):
    if fr['f'] < 0 and fr['i'] is None:
        return False
    return True


def render_clip(resolved, order, s, e, index, missing):
    minx = miny = 1e9
    maxx = maxy = -1e9
    used = 0
    total = 0
    for tn in order:
        fr_all = resolved[tn]
        total = max(total, len(fr_all))
        for i in range(s, min(e, len(fr_all))):
            fr = fr_all[i]
            if fr['f'] < 0:
                continue
            p = image_of(fr['i'], index)
            if not p:
                if fr['i']:
                    missing.add(fr['i'])
                continue
            w, h = load_img(p).size
            used += 1
            for cx, cy in corners(fr['x'], fr['y'], fr['sx'], fr['sy'], fr['a'], w, h):
                minx, maxx = min(minx, cx), max(maxx, cx)
                miny, maxy = min(miny, cy), max(maxy, cy)
    if used == 0:
        return None

    ox = -minx + PAD
    oy = maxy + PAD
    W = int(math.ceil(maxx - minx)) + PAD * 2 + 1
    H = int(math.ceil(maxy - miny)) + PAD * 2 + 1

    frames = []
    for i in range(s, min(e, total)):
        canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for tn in order:
            fr_all = resolved[tn]
            if i >= len(fr_all):
                continue
            fr = fr_all[i]
            if fr['f'] < 0:
                continue
            p = image_of(fr['i'], index)
            if not p:
                continue
            paste_part(canvas, load_img(p), fr['x'], fr['y'], fr['sx'], fr['sy'], fr['a'], ox, oy)
        frames.append(canvas)

    union = None
    for f in frames:
        bb = f.getchannel('A').getbbox()
        if not bb:
            continue
        union = bb if union is None else (min(union[0], bb[0]), min(union[1], bb[1]),
                                          max(union[2], bb[2]), max(union[3], bb[3]))
    if union is None:
        return None

    cw, ch = union[2] - union[0], union[3] - union[1]
    ax, ay = ox - union[0], oy - union[1]
    return {'frames': [f.crop(union) for f in frames], 'w': cw, 'h': ch,
            'ax': round(ax, 1), 'ay': round(ay, 1)}


def pack(cropped, char, clip, quality=88):
    n, cw, ch = len(cropped), cropped[0].size[0], cropped[0].size[1]
    cols = max(1, min(n, MAX_W // max(1, cw)))
    rows = (n + cols - 1) // cols
    strip = Image.new('RGBA', (cols * cw, rows * ch), (0, 0, 0, 0))
    for i, f in enumerate(cropped):
        strip.paste(f, ((i % cols) * cw, (i // cols) * ch))
    d = os.path.join(SHEETS, char)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, clip + '.webp')
    strip.save(path, 'WEBP', quality=quality, method=6)
    return path, strip.size, os.path.getsize(path), cols, rows


def contact(frames, path, label):
    picks = frames if len(frames) <= 8 else [frames[int(i * (len(frames) - 1) / 7)] for i in range(8)]
    gap = 4
    w = sum(p.size[0] for p in picks) + gap * (len(picks) - 1)
    h = max(p.size[1] for p in picks) + 16
    sheet = Image.new('RGBA', (max(w, 200), h), (30, 30, 30, 255))
    x = 0
    for p in picks:
        sheet.alpha_composite(p, (x, h - 16 - p.size[1]))
        x += p.size[0] + gap
    ImageDraw.Draw(sheet).text((2, 2), '%s (%d/%d)' % (label, len(picks), len(frames)), fill=(255, 255, 0, 255))
    sheet.save(path)


def bake_char(name, path, index, report, manifest, sample_mode):
    fps, tracks, order = read_reanim(path)
    resolved = {tn: resolve(tracks[tn]) for tn in order}
    clips = []
    for tn in order:
        if not tn.startswith('anim_'):
            continue
        spans = anim_spans(resolved[tn])
        if not spans:
            continue
        s, e = max(spans, key=lambda t: t[1] - t[0])
        if e - s < 2:
            continue
        clips.append((tn[len('anim_'):], s, e))

    missing = set()
    entry = {'fps': int(fps), 'clips': {}}
    for clip, s, e in clips:
        step = 1
        n = e - s
        if n > 40:
            step = int(math.ceil(n / 40.0))
        r = render_clip(resolved, order, s, e, index, missing)
        if not r:
            continue
        frames = r['frames'][::step]
        if len(frames) < 2:
            continue
        p, size, nbytes, cols, rows = pack(frames, name, clip)
        entry['clips'][clip] = {'file': 'reanim/%s/%s.webp' % (name, clip), 'frames': len(frames),
                                'fps': round(fps / step, 2), 'w': r['w'], 'h': r['h'],
                                'ax': r['ax'], 'ay': r['ay'], 'cols': cols, 'rows': rows,
                                'bytes': nbytes}
        print('  %-14s %3d frames %4dx%4d %7.1f KB' % (clip, len(frames), r['w'], r['h'], nbytes / 1024.0))
        if sample_mode:
            contact(frames, 'contact_%s.png' % norm(name), name + ' / ' + clip)
    if missing:
        entry['missing_images'] = sorted(missing)[:40]
        print('  !! missing images:', len(missing))
    if entry['clips']:
        manifest[name] = entry
        report[name] = {'file': os.path.basename(path), 'clips': entry['clips'], 'missing': len(missing)}
    return entry


def dump_tracks(chars, src, tracks_dir='tracks'):
    os.makedirs(tracks_dir, exist_ok=True)
    found = {norm(fn[:-7]): fn[:-7] for fn in os.listdir(src) if fn.lower().endswith('.reanim')}
    for nm in chars:
        real = found.get(norm(nm))
        if not real:
            print('no reanim for', nm)
            continue
        fps, tracks, order = read_reanim(os.path.join(src, real + '.reanim'))
        lines = ['%s  fps=%s  frames=%d' % (real, fps, max((len(v) for v in tracks.values()), default=0))]
        for tn in order:
            frames = resolve(tracks[tn])
            vis = [i for i, f in enumerate(frames) if f['f'] >= 0]
            imgs = sorted({f['i'] for f in frames if f['i']})
            lines.append('  %-28s n=%-3d visible=%-12s %s' % (tn, len(frames),
                                                             ('%d..%d' % (vis[0], vis[-1])) if vis else '-',
                                                             ' '.join(i.replace('IMAGE_REANIM_', '') for i in imgs[:6]))
        open(os.path.join(tracks_dir, real + '.txt'), 'w').write('\n'.join(lines))
        print('tracks ->', real)


def main():
    if not os.path.isdir(SRC):
        print('missing source dir', SRC)
        sys.exit(1)
    files = sorted(fn for fn in os.listdir(SRC) if fn.lower().endswith('.reanim'))
    index = build_index(SRC)
    print('source %s: %d reanim, %d png' % (SRC, len(files), len(index)))

    inventory = {}
    for fn in files:
        try:
            fps, tracks, order = read_reanim(os.path.join(SRC, fn))
            inventory[fn[:-7]] = {'fps': fps, 'ntracks': len(tracks),
                                  'frames': max((len(v) for v in tracks.values()), default=0),
                                  'anims': [t for t in order if t.startswith('anim_')]}
        except Exception as exc:
            inventory[fn[:-7]] = {'error': str(exc)}
    json.dump(inventory, open('inventory.json', 'w'), indent=1)
    err = sum(1 for v in inventory.values() if 'error' in v)
    print('inventory: %d reanim, %d parse errors' % (len(inventory), err))

    dump_tracks(KEYCHARS, SRC)

    found = {norm(fn[:-7]): fn[:-7] for fn in files}
    if MODE == 'samples':
        targets = [found[norm(n)] for n in SAMPLES if norm(n) in found]
        print('sample targets:', targets)
    else:
        targets = [k for k in inventory if 'error' not in inventory[k]]

    os.makedirs(SHEETS, exist_ok=True)
    manifest, report, total = {}, {}, 0
    for nm in targets:
        print('baking', nm)
        try:
            e = bake_char(nm, os.path.join(SRC, nm + '.reanim'), index, report, manifest, MODE == 'samples')
            total += sum(c['bytes'] for c in e['clips'].values())
        except Exception as exc:
            print('  FAILED', nm, exc)
            report[nm] = {'error': str(exc)}

    json.dump(report, open('report.json', 'w'), indent=1)
    json.dump({'fps': 12, 'generated_by': 'pvz-reanim-bake', 'chars': manifest},
              open('manifest.json', 'w'), indent=1)
    print('total baked bytes: %.2f MB' % (total / 1048576.0))

    if MODE != 'samples':
        with tarfile.open('reanim-assets.tar', 'w') as tar:
            for root, _, fs in os.walk(SHEETS):
                for f in fs:
                    p = os.path.join(root, f)
                    arc = 'assets/reanim/' + os.path.relpath(p, SHEETS).replace(os.sep, '/')
                    ti = tar.gettarinfo(p, arcname=arc)
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ''
                    with open(p, 'rb') as fh:
                        tar.addfile(ti, fh)
        print('reanim-assets.tar %.2f MB' % (os.path.getsize('reanim-assets.tar') / 1048576.0))


if __name__ == '__main__':
    main()
