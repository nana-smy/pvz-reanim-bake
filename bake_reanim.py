#!/usr/bin/env python3
# Bake original PvZ1 .reanim part animations into packed WebP sprite grids.
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
SCALE = float(os.environ.get('SCALE', '0.78'))
QUALITY = int(os.environ.get('QUALITY', '78'))
MAX_W = 16000
MAX_FRAMES = 40
PAD = 2
DIAG = MODE == 'samples'

SAMPLES = ['Chomper', 'PeaShooter', 'SunFlower', 'Wallnut', 'Cabbagepult',
           'Zombie', 'Zombie_cone', 'Zombie_bucket', 'Zombie_screendoor', 'Zombie_duckytube',
           'Zombie_gargantuar', 'Zombie_paper', 'Zombie_bungi']

PLANTS = {
    'SunFlower': 'sunflower', 'PeaShooter': 'peashooter', 'Wallnut': 'wallnut',
    'CherryBomb': 'cherry', 'SnowPea': 'snowpea', 'PotatoMine': 'potatomine',
    'Jalapeno': 'jalapeno', 'ThreePeater': 'threepeater', 'Squash': 'squash',
    'Cabbagepult': 'cabbage', 'Starfruit': 'starfruit', 'Garlic': 'garlic',
    'Caltrop': 'spikeweed', 'LilyPad': 'lilypad', 'Pot': 'flowerpot',
    'Chomper': 'chomper', 'PuffShroom': 'puffshroom', 'SunShroom': 'sunshroom',
    'FumeShroom': 'fumeshroom', 'Gravebuster': 'gravebuster', 'HypnoShroom': 'hypnoshroom',
    'ScaredyShroom': 'scaredyshroom', 'IceShroom': 'iceshroom', 'DoomShroom': 'doomshroom',
    'Tanglekelp': 'tanglekelp', 'Torchwood': 'torchwood', 'Tallnut': 'tallnut',
    'SeaShroom': 'seashroom', 'Plantern': 'plantern', 'Cactus': 'cactus',
    'Blover': 'blover', 'SplitPea': 'splitpea', 'Pumpkin': 'pumpkin',
    'Magnetshroom': 'magnetshroom', 'Cornpult': 'kernelpult', 'Coffeebean': 'coffeebean',
    'Umbrellaleaf': 'umbrelleaf', 'Marigold': 'marigold', 'Melonpult': 'melonpult',
    'GatlingPea': 'gatlingpea', 'TwinSunflower': 'twinsunflower', 'GloomShroom': 'gloomshroom',
    'Cattail': 'cattail', 'WinterMelon': 'wintermelon', 'GoldMagnet': 'goldmagnet',
    'SpikeRock': 'spikerock', 'CobCannon': 'cobcannon', 'Imitater': 'imitater',
}

ZOMBIES = {
    'Zombie': 'basic', 'Zombie_flagpole': 'flag', 'Zombie_paper': 'newspaper',
    'Zombie_football': 'football', 'Zombie_dancer': 'dancing', 'Zombie_backup': 'backup',
    'Zombie_snorkle': 'snorkel', 'Zombie_zamboni': 'zomboni', 'Zombie_bobsled': 'bobsled',
    'Zombie_dolphinrider': 'dolphinrider', 'Zombie_jackbox': 'jackbox', 'Zombie_balloon': 'balloon',
    'Zombie_digger': 'digger', 'Zombie_pogo': 'pogo', 'Zombie_yeti': 'yeti',
    'Zombie_bungi': 'bungee', 'Zombie_ladder': 'ladder', 'Zombie_catapult': 'catapult',
    'Zombie_gargantuar': 'gargantuar', 'Zombie_imp': 'imp', 'Zombie_boss': 'boss',
    'Zombie_polevaulter': 'polevault',
}

ZOMBIE_VARIANTS = ['cone', 'bucket', 'screendoor', 'duckytube']

PLANT_CLIPS = [
    ('idle', ['fullidle', 'idle', 'idle2', 'headidle']),
    ('shoot', ['shooting', 'shoot', 'fullshooting', 'spit']),
    ('special', ['bite', 'chew', 'swallow', 'squash', 'explode', 'rise', 'plant',
                 'grow', 'spin', 'shield', 'open', 'strike', 'throw', 'sleep']),
]
ZOMBIE_CLIPS = [
    ('walk', ['walk', 'walk2', 'walknopaper']),
    ('eat', ['eat', 'eatnopaper']),
    ('die', ['death', 'death2']),
    ('special', ['smash', 'throw', 'dance', 'swim', 'grab', 'raise', 'hold', 'gasp',
                 'grow', 'explode', 'plant', 'rising', 'jump', 'fly']),
]

FKEYS = ('x', 'y', 'a', 'sx', 'sy', 'kx', 'ky', 'f')
DEFAULTS = {'x': 0.0, 'y': 0.0, 'a': 0.0, 'sx': 1.0, 'sy': 1.0,
            'kx': 0.0, 'ky': 0.0, 'f': 0.0, 'i': None}

HIDE_ALWAYS = ['_ground', 'Zombie_whitewater', 'Zombie_mustache', 'anim_tongue',
               'Zombie_flaghand', 'Zombie_tie', 'anim_screendoor',
               'Zombie_innerarm_screendoor', 'Zombie_innerarm_screendoor_hand',
               'Zombie_outerarm_screendoor', 'anim_cone', 'anim_bucket', 'Zombie_duckytube']


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
    has_i = any('i' in fr for fr in frames)
    cur = dict(DEFAULTS)
    out = []
    for fr in frames:
        for k, v in fr.items():
            if k in FKEYS:
                cur[k] = float(v)
            elif k == 'i':
                cur['i'] = v
        if has_i and cur['i'] is None:
            cur['f'] = -1.0
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


class Xform(object):
    def __init__(self, fr, scale):
        self.sx = fr['sx'] * scale
        self.sy = fr['sy'] * scale
        th = math.radians(fr['a'])
        tkx = math.tan(math.radians(fr['kx'])) if abs(fr['kx']) < 89.0 else 0.0
        tky = math.tan(math.radians(fr['ky'])) if abs(fr['ky']) < 89.0 else 0.0
        c, s = math.cos(th), math.sin(th)
        self.m00 = c * self.sx - s * self.sy * tky
        self.m01 = c * self.sx * tkx - s * self.sy
        self.m10 = s * self.sx + c * self.sy * tky
        self.m11 = s * self.sx * tkx + c * self.sy
        self.x = fr['x'] * scale
        self.y = fr['y'] * scale

    def map_bbox(self, w, h, ox, oy):
        pts = []
        for u, v in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
            xc = ox + self.x + self.m00 * u - self.m01 * v + self.m01 * h
            yc = oy - self.y - self.m10 * u + self.m11 * v - self.m11 * h
            pts.append((xc, yc))
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts), max(p[1] for p in pts))

    def affine(self, w, h, ox, oy, offx, offy):
        cx = ox + self.x + self.m01 * h
        cy = oy - self.y - self.m11 * h
        det = self.m00 * self.m11 - self.m01 * self.m10
        if abs(det) < 1e-5:
            det = 1e-5
        i00 = self.m11 / det
        i01 = self.m01 / det
        i10 = self.m10 / det
        i11 = self.m00 / det
        a = i00
        b = i01
        c = i00 * (offx - cx) + i01 * (offy - cy)
        d = i10
        e = i11
        f = i10 * (offx - cx) + i11 * (offy - cy)
        return (a, b, c, d, e, f)


def paste_part(canvas, part, fr, scale, ox, oy):
    w, h = part.size
    xf = Xform(fr, scale)
    bb = xf.map_bbox(w, h, ox, oy)
    dw = int(math.ceil(bb[2] - bb[0])) + 1
    dh = int(math.ceil(bb[3] - bb[1])) + 1
    if dw <= 0 or dh <= 0 or dw > 6000 or dh > 6000:
        return False
    out = part.transform((dw, dh), Image.AFFINE, xf.affine(w, h, ox, oy, bb[0], bb[1]),
                         resample=Image.BICUBIC)
    if out.getchannel('A').getbbox() is None:
        return False
    canvas.alpha_composite(out, (int(round(bb[0])), int(round(bb[1]))))
    return True


def char_cell(resolved, order, clips, index, scale, missing):
    minx = miny = 1e9
    maxx = maxy = -1e9
    total = 0
    for tn in order:
        total = max(total, len(resolved[tn]))
    for _, s, e in clips:
        for i in range(s, min(e, total)):
            for tn in order:
                fr_all = resolved[tn]
                if i >= len(fr_all):
                    continue
                fr = fr_all[i]
                if fr['f'] < 0:
                    continue
                p = image_of(fr['i'], index)
                if not p:
                    if fr['i']:
                        missing.add(fr['i'])
                    continue
                w, h = load_img(p).size
                bb = Xform(fr, scale).map_bbox(w, h, 0.0, 0.0)
                minx, miny = min(minx, bb[0]), min(miny, bb[1])
                maxx, maxy = max(maxx, bb[2]), max(maxy, bb[3])
    if maxx < minx:
        return None
    ox = -minx + PAD
    oy = maxy + PAD
    W = int(math.ceil(maxx - minx)) + 2 * PAD + 1
    H = int(math.ceil(maxy - miny)) + 2 * PAD + 1
    return W, H, ox, oy


def render_frame(resolved, order, i, index, scale, cell):
    W, H, ox, oy = cell
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    drawn = 0
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
        if paste_part(canvas, load_img(p), fr, scale, ox, oy):
            drawn += 1
    return canvas, drawn


def pack_grid(frames, char, clip, cw, ch):
    n = len(frames)
    cols = max(1, min(n, MAX_W // max(1, cw)))
    rows = (n + cols - 1) // cols
    strip = Image.new('RGBA', (cols * cw, rows * ch), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.paste(f, ((i % cols) * cw, (i // cols) * ch))
    d = os.path.join(SHEETS, char)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, clip + '.webp')
    strip.save(path, 'WEBP', quality=QUALITY, method=6)
    return path, cols, rows, os.path.getsize(path), strip.size


def contact(rows, path):
    zoom = 3
    gap = 6
    rows = [(label, frames) for label, frames in rows if frames]
    if not rows:
        return
    picks = []
    for label, frames in rows:
        sel = frames if len(frames) <= 6 else [frames[int(i * (len(frames) - 1) / 5)] for i in range(6)]
        picks.append((label, sel))
    widths = [sum(max(1, f.size[0]) for f in sel) * zoom + gap * (len(sel) - 1) for _, sel in picks]
    W = max(widths) + 8
    H = sum(max(f.size[1] for f in sel) * zoom + 18 + gap for _, sel in picks) + 6
    sheet = Image.new('RGBA', (W, H), (32, 32, 36, 255))
    d = ImageDraw.Draw(sheet)
    y = 4
    for (label, sel), w in zip(picks, widths):
        row_h = max(f.size[1] for f in sel) * zoom
        d.text((4, y + 2), '%s (%d frames)' % (label, len(sel)), fill=(255, 232, 60, 255))
        x = 4
        for f in sel:
            big = f.resize((max(1, f.size[0]) * zoom, max(1, f.size[1]) * zoom), Image.NEAREST)
            sheet.alpha_composite(big, (x, y + 16 + (row_h - big.size[1])))
            x += big.size[0] + gap
        y += row_h + 18 + gap
    sheet.save(path)


def pick_clips(resolved, order, family):
    anims = {}
    firsts = []
    for tn in order:
        if not tn.startswith('anim_'):
            continue
        sp = anim_spans(resolved[tn])
        if sp:
            s, e = max(sp, key=lambda t: t[1] - t[0])
            anims[norm(tn[5:])] = (s, e)
            firsts.append(s)
    table = PLANT_CLIPS if family == 'plant' else ZOMBIE_CLIPS
    out, used = [], set()
    for label, keys in table:
        for k in keys:
            if k in anims and anims[k][1] - anims[k][0] >= 2 and k not in used:
                out.append((label, anims[k][0], anims[k][1]))
                used.add(k)
                break
    if family == 'plant' and not any(c[0] == 'idle' for c in out) and firsts:
        start = max(0, min(firsts) - 1)
        if start >= 2:
            out.insert(0, ('idle', 0, start))
    if DIAG:
        names = sorted(anims)
        print('  anims:', len(names), names[:24])
        print('  picked:', [(c[0], c[1], c[2]) for c in out])
    return out[:5]


def apply_forces(resolved, hides, shows):
    for tn in hides:
        if tn in resolved:
            for fr in resolved[tn]:
                fr['f'] = -1.0
    for tn in shows:
        if tn in resolved:
            for fr in resolved[tn]:
                if fr['i']:
                    fr['f'] = max(fr['f'], 0.0)


def variant_forces(variant):
    hides = list(HIDE_ALWAYS)
    shows = []
    if variant == 'cone':
        shows.append('anim_cone')
    elif variant == 'bucket':
        shows.append('anim_bucket')
    elif variant == 'screendoor':
        shows += ['anim_screendoor', 'Zombie_innerarm_screendoor', 'Zombie_outerarm_screendoor']
    elif variant == 'duckytube':
        shows.append('Zombie_duckytube')
    return hides, shows


def bake_char(key, path, family, index, manifest, report, sample_mode, scale):
    fps, tracks, order = read_reanim(path)
    if DIAG:
        print('  tracks:', len(order))
        for tn in order[:3] + order[-3:]:
            print('   raw', tn, ET.tostring_tostr) if False else None
    variant, base = '', key
    for v in ZOMBIE_VARIANTS:
        if key.endswith('_' + v):
            variant, base = v, key[:-(len(v) + 1)]
            break

    resolved = {tn: resolve(tracks[tn]) for tn in order}
    if base.startswith('Zombie') and 'imp' not in base.lower():
        for tn in list(resolved):
            if 'imp' in tn.lower() or 'whiterope' in tn.lower():
                resolved[tn] = [dict(fr, f=-1.0) for fr in resolved[tn]]
    hides, shows = variant_forces(variant)
    apply_forces(resolved, hides, shows)

    if DIAG:
        for tn in order:
            fr_all = resolved[tn]
            vis = sum(1 for fr in fr_all if fr['f'] >= 0)
            sym = next((fr['i'] for fr in fr_all if fr['i']), '')
            print('   T %-34s n=%3d vis=%3d sym=%-40s found=%s' %
                  (tn, len(fr_all), vis, sym[:40], bool(image_of(sym, index)) if sym else '-'))

    clips = pick_clips(resolved, order, family)
    if not clips:
        print('  no clips for', key)
        return 0
    missing = set()
    cell = char_cell(resolved, order, clips, index, scale, missing)
    if not cell:
        print('  empty cell for', key)
        return 0
    W, H, ox, oy = cell
    print('  cell %dx%d ox=%.1f oy=%.1f missing=%d %s' % (W, H, ox, oy, len(missing), sorted(missing)[:6]))

    entry = {'w': W, 'h': H, 'ax': round(ox, 1), 'ay': round(oy, 1), 'fps': int(fps), 'clips': {}}
    rows, total, empty = [], 0, 0
    for label, s, e in clips:
        n = e - s
        step = 1
        while n / step > MAX_FRAMES:
            step += 1
        pairs = [render_frame(resolved, order, i, index, scale, cell) for i in range(s, e)][::step]
        frames = [p[0] for p in pairs]
        drawn = [p[1] for p in pairs]
        if len(frames) < 2:
            continue
        filled = sum(1 for f in frames if f.getchannel('A').getbbox())
        if filled == 0:
            empty += 1
            print('  !! EMPTY clip', label, 'drawn/frame', drawn[:6])
            continue
        p, cols, rr, nbytes, size = pack_grid(frames, key, label, W, H)
        entry['clips'][label] = {'file': 'reanim/%s/%s.webp' % (key, label), 'frames': len(frames),
                                 'cols': cols, 'rows': rr, 'fps': round(fps / step, 2),
                                 'bytes': nbytes}
        total += nbytes
        print('  %-8s %3d fr %4dx%4d %7.1f KB parts/frame %s' %
              (label, len(frames), W, H, nbytes / 1024.0, drawn[:6]))
        rows.append((label, frames))
    if not entry['clips']:
        return 0
    if missing:
        entry['missing'] = sorted(missing)[:20]
    if sample_mode:
        contact(rows, 'contact_%s.png' % norm(key))
    manifest[key] = entry
    report[key] = {'src': os.path.basename(path), 'clips': entry['clips'],
                   'missing': len(missing), 'empty': empty}
    return total


def main():
    if not os.path.isdir(SRC):
        print('missing source dir', SRC)
        sys.exit(1)
    files = {norm(fn[:-7]): fn[:-7] for fn in os.listdir(SRC) if fn.lower().endswith('.reanim')}
    index = build_index(SRC)
    print('source %s: %d reanim, %d png, scale %.2f q%d' % (SRC, len(files), len(index), SCALE, QUALITY))
    os.makedirs(SHEETS, exist_ok=True)

    jobs = []
    for src in sorted(PLANTS):
        if norm(src) in files:
            jobs.append((src, 'plant', files[norm(src)]))
    for src in sorted(ZOMBIES):
        if norm(src) in files:
            jobs.append((src, 'zombie', files[norm(src)]))
    if norm('Zombie') in files:
        for v in ZOMBIE_VARIANTS:
            jobs.append(('Zombie_' + v, 'zombie', files[norm('Zombie')]))

    if MODE == 'samples':
        wanted = {norm(x) for x in SAMPLES}
        jobs = [j for j in jobs if norm(j[0]) in wanted]
    print('jobs:', len(jobs))

    manifest, report, total = {}, {}, 0
    for key, family, src in jobs:
        print('baking', key, '<-', src)
        try:
            total += bake_char(key, os.path.join(SRC, src + '.reanim'), family, index,
                               manifest, report, MODE == 'samples', SCALE)
        except Exception as exc:
            print('  FAILED', key, exc)
            report[key] = {'error': str(exc)}

    manifest = {'fps': 12, 'scale': SCALE, 'chars': manifest}
    json.dump(manifest, open('manifest.json', 'w'), indent=1)
    json.dump(report, open('report.json', 'w'), indent=1)
    print('total %.2f MB over %d chars' % (total / 1048576.0, len(manifest['chars'])))

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
