import json, subprocess, math, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

V = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video'
FD = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/web/fonts/'
W, H, FPS = 1920, 1080, 30
INK = (20, 20, 19); IVORY = (240, 238, 230); CORAL = (217, 119, 87)
LIVE = V + '/assets/footage4/live.mp4'; REL = V + '/assets/footage4/reliability.mp4'
CAP = json.load(open(V + '/assets/vo3/captions.json'))
DUR = json.load(open(V + '/assets/vo3/durations.json'))

def font(name, size, var=None):
    f = ImageFont.truetype(FD + name, size)
    if var:
        try: f.set_variation_by_name(var)
        except Exception: pass
    return f
SILK = lambda s: font('Silkscreen-Bold.ttf', s)
MONO = lambda s: font('JetBrainsMono-Variable.ttf', s, 'Bold')
VT = lambda s: font('VT323-Regular.ttf', s)

def ease(p):
    p = max(0.0, min(1.0, p)); return p * p * (3 - 2 * p)
def back(p):
    p = max(0.0, min(1.0, p)); c = 1.70158; return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2

def text_size(f, s):
    b = f.getbbox(s); return b[2] - b[0], b[3] - b[1], b[0], b[1]

def pill(text, f, fg, bg, pad=(26, 14), border=None, radius=14):
    tw, th, ox, oy = text_size(f, text)
    w, h = tw + pad[0] * 2, th + pad[1] * 2
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=bg, outline=border, width=4 if border else 0)
    d.text((pad[0] - ox, pad[1] - oy), text, font=f, fill=fg)
    return im

def check_chip(label):
    f = SILK(34); tw, th, ox, oy = text_size(f, label)
    w, h = tw + 110, 76
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 16, fill=INK + (235,), outline=CORAL, width=4)
    d.text((24 - ox, (h - th) // 2 - oy), label, font=f, fill=IVORY)
    cx = 24 + tw + 22
    d.rounded_rectangle([cx, 18, cx + 40, 58], 8, fill=CORAL)
    d.line([(cx + 9, 38), (cx + 17, 47), (cx + 32, 27)], fill=INK, width=6)
    return im

# ---------- truck sprite ----------
TRUCK = ["CCCCCCCCCCCC........",
         "CCCCCCCCCCCC.IIII...",
         "CCCCCCCCCCCC.IWWWI..",
         "CCCCCCCCCCCC.IWWWII.",
         "CCCCCCCCCCCCIIIIIIII",
         "CCCCCCCCCCCCIIIIIIII",
         "CCCCCCCCCCCCIIIIIIII",
         "..KKK.....KKK..KKK..",
         "..KKK.....KKK..KKK.."]
def truck(scale=10):
    cols = {'C': CORAL + (255,), 'I': IVORY + (255,), 'W': (90, 150, 190, 255), 'K': (120, 118, 110, 255)}
    im = Image.new('RGBA', (20 * scale, 9 * scale), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for r, row in enumerate(TRUCK):
        for c, ch in enumerate(row):
            if ch in cols: d.rectangle([c * scale, r * scale, (c + 1) * scale - 1, (r + 1) * scale - 1], fill=cols[ch])
    return im
TRK = truck(10)

# ---------- timeline ----------
segs = []   # dict(kind, dur, ...) ; start filled later
ovs = []    # dict(img, cx, cy, t0, t1) center coords
zooms = []  # (t_in0, t_in1, t_out0, t_out1, z, fx, fy)
vo_starts = {}

def add(kind, dur, trans=True, **kw):
    t0 = sum(s['dur'] for s in segs)
    segs.append(dict(kind=kind, dur=dur, start=t0, trans=trans, **kw)); return t0

def click(t, x, y, z=1.35):
    zooms.append((t - 0.45, t - 0.10, t + 0.60, t + 0.95, z, x, y))

def ov(img, cx, cy, t0, t1, anim='pop'):
    ovs.append(dict(img=img, cx=cx, cy=cy, t0=t0, t1=t1, anim=anim))

def tag(text, t0, t1):
    im = pill(text, SILK(34), INK, CORAL + (255,), pad=(24, 14), radius=10)
    ov(im, 30 + im.width // 2, 64 + im.height // 2, t0, t1)

# S1 problem
S1 = 0.0; vo_starts['S1'] = 0.25
add('vid', 4.2, trans=False, src=V + '/assets/fal3/1.mp4', ss=0.3, speed=1.0, kb=(1.0, 1.06, 960, 540))
add('img', 4.2, src=V + '/assets/fal3/2.png', kb=(1.04, 1.14, 900, 520))
add('img', 6.6, src=V + '/assets/fal3/3.png', kb=(1.0, 1.12, 1000, 560))
t_title = add('title', 3.0)
# problem card
card = Image.new('RGBA', (1180, 470), (0, 0, 0, 0)); d = ImageDraw.Draw(card)
d.rounded_rectangle([0, 0, 1179, 469], 22, fill=INK + (228,), outline=CORAL, width=6)
ov(card, 960, 470, 3.35, 11.5)
ov(pill('Marco is sick.', SILK(76), IVORY, (0, 0, 0, 0), pad=(10, 8)), 960, 335, 3.4, 11.5)
ov(pill('4 customers are waiting.', SILK(56), IVORY, (0, 0, 0, 0), pad=(10, 8)), 960, 460, 6.0, 11.5)
ov(pill('Who covers?', SILK(92), CORAL, (0, 0, 0, 0), pad=(10, 8)), 960, 590, 9.1, 11.5)

# S2 + S3 live continuous
s2 = add('clip', 10.2, src=LIVE, ss=0.0, speed=1.0); vo_starts['S2'] = s2 + 0.15
tag("1 · TELL IT WHO'S OUT", s2 + 0.3, s2 + 10.1)
click(s2 + 5.93, 246, 1040)
s3 = add('clip', 22.0, trans=False, src=LIVE, ss=10.2, speed=1.0); vo_starts['S3'] = s3 + 0.15
tag('2 · IT MAKES A NEW PLAN', s3 + 0.1, s3 + 21.9)
# punch-in on the crew board while vans drive (live 10.3 -> 22.3)
zooms.append((s3 + 0.1, s3 + 0.4, s3 + 11.8, s3 + 12.15, 1.2, 890, 560))
lab = lambda s: pill(s, MONO(28), INK, IVORY + (250,), pad=(20, 12), border=CORAL, radius=10)
ov(lab("Ana takes Wei's small job"), 1700, 300, vo_starts['S3'] + 9.67, s3 + 21.9)
ov(lab("Wei takes Marco's big job"), 1700, 380, vo_starts['S3'] + 12.72, s3 + 21.9)
ov(pill('1 customer picks a new time', MONO(26), IVORY, CORAL + (250,), pad=(18, 12), radius=10), 1700, 460, vo_starts['S3'] + 15.06, s3 + 21.9)

# S4 approve + writes (3.2x)
s4 = add('clip', 3.5, src=LIVE, ss=38.4, speed=1.0); vo_starts['S4'] = s4 + 0.15
tag('3 · YOU SAY YES', s4 + 0.3, s4 + 15.0)
click(s4 + (41.31 - 38.4), 1698, 995)
s4b = add('clip', (79.3 - 41.9) / 3.2, trans=False, src=LIVE, ss=41.9, speed=3.2)
ov(pill('3x SPEED', SILK(26), IVORY, INK + (220,), pad=(16, 10), radius=8), 1830, 150, s4b + 0.1, s4b + (79.3 - 41.9) / 3.2 - 0.1)
for i, name in enumerate(['Calendar', 'Sheets', 'Slack', 'Gmail']):
    ov(check_chip(name), 560 + i * 300, 185, s4b + 1.2 + i * 2.3, s4b + (79.3 - 41.9) / 3.2 - 0.05)

# S5 proof / crash / what-if
s5 = add('clip', 6.6, trans=False, src=LIVE, ss=79.3, speed=1.0); vo_starts['S5'] = s5 + 0.15
tag('4 · IT DOUBLE-CHECKS', s5 + 0.1, s5 + 6.5)
zooms.append((s5 + 0.2, s5 + 0.5, s5 + 6.0, s5 + 6.35, 1.3, 1700, 990))
cnt = [pill('%d/36' % n, SILK(120), CORAL, INK + (225,), pad=(34, 18), border=IVORY, radius=16) for n in range(37)]
ovs.append(dict(img=cnt[-1], frames=cnt, count=(s5 + 0.3, s5 + 1.3), cx=760, cy=430, t0=s5 + 0.3, t1=s5 + 6.4, anim='pop'))
ov(pill('CHECKS PASSED', SILK(40), IVORY, INK + (225,), pad=(20, 10), radius=10), 760, 560, s5 + 1.3, s5 + 6.4)
crash = CAP['S5'][2]['start']; ask = CAP['S5'][5]['start']
bdur = ask - crash
s5b = add('clip', bdur, src=REL, ss=15.7, speed=1.0)
ov(pill('Crash → resumes, nothing sent twice', MONO(34), IVORY, INK + (235,), pad=(24, 14), border=CORAL, radius=12), 900, 170, s5b + 0.3, s5b + bdur - 0.1)
click(s5b + (16.14 - 15.7), 1698, 995); click(s5b + (20.75 - 15.7), 1697, 994)
s5c = add('clip', 5.7, src=LIVE, ss=90.9, speed=1.0)
tag('5 · WHAT IF?', s5c + 0.2, s5c + 10.1)
click(s5c + (91.82 - 90.9), 1094, 85)
s5d = add('clip', 4.5, src=LIVE, ss=99.7, speed=1.0)
click(s5d + (100.18 - 99.7), 1200, 85)

# S6 conclusion
s6 = add('img', 11.45, src=V + '/assets/fal3/4.png', kb=(1.0, 1.15, 960, 520)); vo_starts['S6'] = s6 + 0.15
t_out = add('outro', 7.6)
TOTAL = sum(s['dur'] for s in segs)
NF = int(round(TOTAL * FPS))
print('TOTAL', TOTAL, 'frames', NF, flush=True)

# captions
caps = []
for k in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']:
    for c in CAP[k]:
        caps.append((vo_starts[k] + c['start'], vo_starts[k] + c['end'] + 0.05, c['text']))
CAPIMG = {}
def capimg(text):
    if text not in CAPIMG:
        CAPIMG[text] = pill(text, MONO(46), IVORY, INK + (200,), pad=(30, 14), radius=18)
    return CAPIMG[text]
def srt_t(t):
    ms = int(round(t * 1000)); return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
with open(V + '/second-shift-demo.srt', 'w') as f:
    for i, (a, b, tx) in enumerate(caps):
        nb = min(b, caps[i + 1][0] - 0.01) if i + 1 < len(caps) else b
        f.write('%d\n%s --> %s\n%s\n\n' % (i + 1, srt_t(a), srt_t(nb), tx))

# ---------- frame sources ----------
def reader(path, ss, dur, speed):
    vf = 'setpts=PTS/%s,fps=30,scale=1920:1080' % speed
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(ss), '-i', path, '-t', str(dur * speed + 0.5), '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 8)

def kenburns(img, p, kb):
    z0, z1, fx, fy = kb; z = z0 + (z1 - z0) * p
    box = (fx - fx / z, fy - fy / z, fx + (W - fx) / z, fy + (H - fy) / z)
    return img.resize((W, H), Image.BILINEAR, box=box)

BG = Image.new('RGB', (W, H), INK); dg = ImageDraw.Draw(BG)
for x in range(0, W, 48): dg.line([(x, 0), (x, H)], fill=(30, 30, 28))
for y in range(0, H, 48): dg.line([(0, y), (W, y)], fill=(30, 30, 28))
TITLE_BIG = pill('SECOND SHIFT', SILK(168), CORAL, (0, 0, 0, 0), pad=(10, 10))
TITLE_SUB = pill('Fixes the day in seconds', MONO(58), IVORY, (0, 0, 0, 0), pad=(10, 10))
O_BIG = pill('SECOND SHIFT', SILK(140), CORAL, (0, 0, 0, 0), pad=(10, 10))
O_L1 = pill("We can't predict the day.", MONO(54), IVORY, (0, 0, 0, 0), pad=(10, 8))
O_L2 = pill('We can be ready for it.', MONO(54), IVORY, (0, 0, 0, 0), pad=(10, 8))
O_URL = pill('github.com/anirxdh/second-shift', VT(76), INK, IVORY + (255,), pad=(28, 8), radius=10)

def paste_pop(fr, im, cx, cy, age, left, scale_in=True):
    if age < 0 or left < 0: return
    k = min(1.0, age / 0.15, left / 0.15 if left < 0.15 else 1.0)
    s = 0.8 + 0.2 * back(age / 0.24) if scale_in else 1.0
    if abs(s - 1) > 0.005:
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)
    if k < 0.999:
        a = np.array(im); a[..., 3] = (a[..., 3] * k).astype(np.uint8); im = Image.fromarray(a)
    fr.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)

def road_truck(fr, lt, dur, y):
    d = ImageDraw.Draw(fr)
    off = int(lt * 400) % 80
    for x in range(-80 + off, W, 80): d.rectangle([x, y + 100, x + 40, y + 106], fill=(70, 68, 62))
    x = -260 + (W + 520) * (lt / dur)
    bob = 3 if int(lt * 8) % 2 else 0
    for i in range(3): d.rectangle([x - 60 - i * 50, y + 30 + i * 18, x - 20 - i * 50, y + 34 + i * 18], fill=IVORY)
    fr.paste(TRK, (int(x), y + bob), TRK)

def card_frame(kind, lt, dur):
    fr = BG.copy()
    if kind == 'title':
        paste_pop(fr, TITLE_BIG, 960, 400, lt, dur - lt + 1)
        paste_pop(fr, TITLE_SUB, 960, 560, lt - 0.4, dur - lt + 1)
        road_truck(fr, lt, dur, 700)
    else:
        paste_pop(fr, O_BIG, 960, 260, lt - 0.1, 99)
        paste_pop(fr, O_L1, 960, 430, lt - 0.1, 99)
        paste_pop(fr, O_L2, 960, 510, lt - 2.4, 99)
        paste_pop(fr, O_URL, 960, 650, lt - 4.9, 99)
        road_truck(fr, lt, dur, 800)
    return fr

def zoom_at(t):
    best = (1.0, 960, 540)
    for (a0, a1, b0, b1, z, fx, fy) in zooms:
        if a0 <= t <= b1:
            if t < a1: k = ease((t - a0) / (a1 - a0))
            elif t > b0: k = 1 - ease((t - b0) / (b1 - b0))
            else: k = 1
            zz = 1 + (z - 1) * k
            if zz > best[0]: best = (zz, fx, fy)
    return best

# ---------- encoders ----------
def enc(out):
    return subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', '30', '-i', '-',
                             '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE, bufsize=10 ** 8)
E_SUB = enc(V + '/work/v_sub.mp4'); E_NOS = enc(V + '/work/v_nosub.mp4')

prev_last = None; fi = 0
FB = W * H * 3
for si, s in enumerate(segs):
    n = int(round((s['start'] + s['dur']) * FPS)) - int(round(s['start'] * FPS))
    proc = None; still = None; last = None
    if s['kind'] in ('clip', 'vid'):
        proc = reader(s['src'], s['ss'], s['dur'], s['speed'])
    elif s['kind'] == 'img':
        still = Image.open(s['src']).convert('RGB').resize((W, H))
    for j in range(n):
        t = fi / FPS; lt = j / FPS
        if proc:
            buf = proc.stdout.read(FB)
            if len(buf) == FB: last = Image.frombuffer('RGB', (W, H), buf, 'raw', 'RGB', 0, 1).copy()
            fr = last.copy()
            if s['kind'] == 'vid': fr = kenburns(fr, lt / s['dur'], s['kb'])
        elif still is not None:
            fr = kenburns(still, lt / s['dur'], s['kb'])
        else:
            fr = card_frame(s['kind'], lt, s['dur'])
        if s['kind'] == 'clip':
            z, fx, fy = zoom_at(t)
            if z > 1.002:
                fr = fr.resize((W, H), Image.BILINEAR, box=(fx - fx / z, fy - fy / z, fx + (W - fx) / z, fy + (H - fy) / z))
        # push transition
        if s['trans'] and prev_last is not None and j < 8:
            e = ease((j + 1) / 9.0); sft = int(W * e)
            a = np.array(fr); b = np.array(prev_last); o = np.empty_like(a)
            o[:, :W - sft] = b[:, sft:]; o[:, W - sft:] = a[:, :sft]
            fr = Image.fromarray(o)
        for o_ in ovs:
            if o_['t0'] <= t <= o_['t1']:
                im = o_['img']
                if 'frames' in o_:
                    c0, c1 = o_['count']; idx = int(round(36 * ease((t - c0) / (c1 - c0))))
                    im = o_['frames'][idx]
                paste_pop(fr, im, o_['cx'], o_['cy'], t - o_['t0'], o_['t1'] - t)
        # fades
        if t < 0.3 or t > TOTAL - 0.6:
            k = min(t / 0.3, (TOTAL - t) / 0.6); k = max(0.0, min(1.0, k))
            fr = Image.fromarray((np.array(fr) * k).astype(np.uint8))
        E_NOS.stdin.write(fr.tobytes())
        cur = [c for c in caps if c[0] <= t <= c[1]]
        if cur:
            fs = fr.copy(); ci = capimg(cur[-1][2])
            fs.paste(ci, (960 - ci.width // 2, 1034 - ci.height), ci)
            E_SUB.stdin.write(fs.tobytes())
        else:
            E_SUB.stdin.write(fr.tobytes())
        fi += 1
        if fi % 300 == 0: print('frame', fi, '/', NF, flush=True)
    if proc: proc.kill()
    prev_last = fr
E_SUB.stdin.close(); E_NOS.stdin.close(); E_SUB.wait(); E_NOS.wait()

# ---------- audio ----------
ins = []; fl = []
for i, k in enumerate(['S1', 'S2', 'S3', 'S4', 'S5', 'S6']):
    ins += ['-i', V + '/assets/vo3/%s.mp3' % k]
    ms = int(vo_starts[k] * 1000); fl.append('[%d:a]aresample=48000,adelay=%d|%d[a%d]' % (i, ms, ms, i))
fl.append(''.join('[a%d]' % i for i in range(6)) + 'amix=inputs=6:normalize=0:duration=longest,apad,atrim=0:%.3f,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]' % TOTAL)
subprocess.run(['ffmpeg', '-v', 'error', '-y'] + ins + ['-filter_complex', ';'.join(fl), '-map', '[out]', '-c:a', 'aac', '-b:a', '192k', V + '/work/audio.m4a'], check=True)
for vin, out in [('v_sub', 'second-shift-demo.mp4'), ('v_nosub', 'second-shift-demo-nosubs.mp4')]:
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', V + '/work/%s.mp4' % vin, '-i', V + '/work/audio.m4a', '-map', '0:v', '-map', '1:a', '-c', 'copy', '-shortest', '-movflags', '+faststart', V + '/' + out], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', V + '/second-shift-demo.mp4', '-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-c:a', 'copy', '-movflags', '+faststart', V + '/second-shift-demo-720p.mp4'], check=True)
print('DONE', TOTAL)
