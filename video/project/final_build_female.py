import json, subprocess, math, sys, re, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Female-narration cut. Timeline is built AROUND the vo3f narration: every scene
# length = its narration + <=0.3s, visuals anchored to word times in words.json.
V = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video'
FD = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/web/fonts/'
VO = V + '/assets/vo3f'
WK = V + '/work_f'
REL_DIR = V + '/release'
os.makedirs(WK, exist_ok=True); os.makedirs(REL_DIR, exist_ok=True)
W, H, FPS = 1920, 1080, 30
INK = (20, 20, 19); IVORY = (240, 238, 230); CORAL = (217, 119, 87); RED = (205, 60, 70)
LIVE = V + '/assets/footage4/live.mp4'; REL = V + '/assets/footage4/reliability.mp4'
CAP = json.load(open(VO + '/captions.json'))
WORDS = json.load(open(VO + '/words.json'))

def mp3_len(p):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-f', 's16le', '-ac', '1', '-ar', '48000', '-'], capture_output=True).stdout
    return len(raw) / 96000.0
DUR = {k: mp3_len(VO + '/%s.mp3' % k) for k in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']}
print('decoded VO durations', {k: round(v, 3) for k, v in DUR.items()}, flush=True)

def wt(k, word, occ=0):
    """relative start time of the occ-th occurrence of word in scene k"""
    n = 0
    for x in WORDS[k]:
        if re.sub(r"[^a-z0-9'\-]", '', x['word'].lower()) == word.lower():
            if n == occ: return x['start']
            n += 1
    raise KeyError((k, word, occ))

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
segs = []; ovs = []; zooms = []; vo_starts = {}; anchors = []

def add(kind, dur, trans=True, **kw):
    t0 = sum(s['dur'] for s in segs)
    segs.append(dict(kind=kind, dur=dur, start=t0, trans=trans, **kw)); return t0
def now(): return sum(s['dur'] for s in segs)

def click(t, x, y, z=1.35):
    zooms.append((t - 0.45, t - 0.10, t + 0.60, t + 0.95, z, x, y))

def ov(img, cx, cy, t0, t1, anim='pop'):
    ovs.append(dict(img=img, cx=cx, cy=cy, t0=t0, t1=t1, anim=anim))

# section tags: small, in the empty middle of the app header bar (never over "02 CREW BOARD")
def tag(text, t0, t1):
    im = pill(text, SILK(24), INK, CORAL + (255,), pad=(16, 8), radius=8)
    ov(im, 1085, 27, t0, t1)

def A(k, word, occ=0): return vo_starts[k] + wt(k, word, occ)
def anchor(label, t, visual): anchors.append((label, t, visual))

TAIL = 0.2   # visual runs this much past each scene's narration (<= 0.3)

# ===== S1 problem =====
vo_starts['S1'] = 0.25
t_title = A('S1', 'second') - 0.04
add('vid', 3.40, trans=False, src=V + '/assets/fal3/1.mp4', ss=0.3, speed=1.0, kb=(1.0, 1.06, 960, 540))
add('img', 2.90, src=V + '/assets/fal3/2.png', kb=(1.04, 1.14, 900, 520))
add('img', t_title - now(), src=V + '/assets/fal3/3.png', kb=(1.0, 1.12, 1000, 560))
s1_end_audio = vo_starts['S1'] + DUR['S1']
# title sting: narration "Second Shift does it in seconds" + <=1.0s non-narrated
add('title', (s1_end_audio + 0.94) - t_title)
T_SUB = A('S1', 'seconds') - 0.10 - t_title
card = Image.new('RGBA', (1180, 470), (0, 0, 0, 0)); d = ImageDraw.Draw(card)
d.rounded_rectangle([0, 0, 1179, 469], 22, fill=INK + (228,), outline=CORAL, width=6)
t645 = A('S1', 'six'); tm = A('S1', 'marco'); t4 = A('S1', 'four'); tw_ = A('S1', 'who')
ov(pill('6:45 AM', MONO(150), CORAL, (0, 0, 0, 0), pad=(10, 8)), 960, 460, t645, tm - 0.08)
ov(card, 960, 470, tm - 0.05, t_title)
ov(pill('Marco is sick.', MONO(80), IVORY, (0, 0, 0, 0), pad=(10, 8)), 960, 335, tm, t_title)
ov(pill('4 customers are waiting.', MONO(62), IVORY, (0, 0, 0, 0), pad=(10, 8)), 960, 460, t4, t_title)
ov(pill('Who covers?', MONO(96), CORAL, (0, 0, 0, 0), pad=(10, 8)), 960, 590, tw_, t_title)
anchor('S1 "six forty-five"', t645, '"6:45 AM" card pops')
anchor('S1 "Marco just called in sick"', tm, '"Marco is sick." card')
anchor('S1 "Four customers"', t4, '"4 customers are waiting." (JetBrains Mono)')
anchor('S1 "Who covers"', tw_, '"Who covers?"')
anchor('S1 "Second Shift"', t_title + 0.04, 'SECOND SHIFT title card (push-in, sub on "seconds")')

# ===== S2 (dashboard -> Plan click), continuous into S3 =====
s2 = add('clip', 0, src=LIVE, ss=0.0, speed=1.0)   # dur/speed patched below
vo_starts['S2'] = s2 + 0.06
S2_DUR = 0.06 + DUR['S2'] + 0.18
# S3 timing: "Watch" must land exactly on vans-drive (footage 8.69)
s3 = s2 + S2_DUR
vo_starts['S3'] = s3 + 0.05
t_watch = A('S3', 'watch')
t_marcos_end = vo_starts['S3'] + [x for x in WORDS['S3'] if x['word'].lower().startswith("marco's.")][0]['end']
segA_end = t_marcos_end + 0.55             # hold board till after "...Wei takes Marco's."
spA = (15.15 - 8.69) / (segA_end - t_watch)  # gentle slow-mo so board holds through the swap
F0 = 8.69 - (t_watch - s3) * spA
spS2 = F0 / S2_DUR
segs[-1]['dur'] = S2_DUR; segs[-1]['speed'] = spS2
tag("1 · TELL IT WHO'S OUT", s2 + 0.3, s3 - 0.05)
t_plan = s2 + 6.12 / spS2
click(t_plan, 246, 1040)
anchor('S2 (footage 0-%.2f @%.2fx)' % (F0, spS2), t_plan, 'Plan click at footage 6.12 (zoom-on-click)')

# ===== S3 new plan =====
add('clip', segA_end - s3, trans=False, src=LIVE, ss=F0, speed=spA)
tag('2 · IT MAKES A NEW PLAN', s3 + 0.1, None)
zooms.append((t_watch - 0.12, t_watch + 0.25, segA_end - 0.35, segA_end - 0.02, 1.2, 890, 560))
anchor('S3 "Watch the trucks move"', t_watch, 'vans start driving (footage 8.69) + 1.2x punch-in')
lab = lambda s: pill(s, MONO(28), INK, IVORY + (250,), pad=(20, 12), border=CORAL, radius=10)
t_ana = A('S3', 'ana'); t_wei2 = A('S3', 'wei', 1)
ov(lab("Ana takes Wei's small job"), 1700, 300, t_ana, segA_end)
ov(lab("Wei takes Marco's big job"), 1700, 380, t_wei2, segA_end)
anchor('S3 "Ana takes Wei\'s small job"', t_ana, 'label pops')
anchor('S3 "Wei takes Marco\'s"', t_wei2, 'label pops')
# short zone-map slice on "One job can't be saved today"
t_one = A('S3', 'one')
mapB_end = A('S3', 'so', 1) + 0.05
add('clip', mapB_end - segA_end, trans=False, src=LIVE, ss=23.55, speed=1.0)
anchor('S3 "One job can\'t be saved"', segA_end, 'zone map slice (footage 23.55)')
# back to the After board with the red NEEDS RESCHEDULE tray
s3_end = vo_starts['S3'] + DUR['S3'] + TAIL
add('clip', s3_end - mapB_end, trans=False, src=LIVE, ss=20.45, speed=1.0)
zooms.append((mapB_end + 0.05, mapB_end + 0.4, s3_end - 0.3, s3_end - 0.02, 1.22, 620, 990))
t_pick = A('S3', 'pick')
ov(pill('Needs reschedule: customer picks a new time', MONO(30), IVORY, RED + (250,), pad=(22, 12), radius=10), 760, 858, t_pick, s3_end)
anchor('S3 "pick a new time"', t_pick, 'red "needs reschedule" label over the red tray (zoomed)')
for o in ovs:
    if o['t1'] is None: o['t1'] = s3_end - 0.05

# ===== S4 approve + writes =====
s4 = add('clip', 0, src=LIVE, ss=0, speed=1.0)
vo_starts['S4'] = s4 + 0.10
t_click = A('S4', 'click') - 0.05
lt_click = t_click - s4
segs[-1]['ss'] = 41.31 - lt_click
s4a_end = s4 + (41.9 - segs[-1]['ss'])
segs[-1]['dur'] = s4a_end - s4
click(t_click, 1698, 995)
anchor('S4 "a person says yes" / "One click"', t_click, 'Approve click (footage 41.31) + zoom-on-click')
s4_end = vo_starts['S4'] + DUR['S4'] + TAIL
# S5 continuity: 36/36 burst (79.5) must land on "Thirty-six"
vo_starts['S5'] = s4_end + 0.05
t36 = A('S5', 'thirty-six')
F5 = 79.5 - (t36 - s4_end)
spW = (F5 - 41.9) / (s4_end - s4a_end)
add('clip', s4_end - s4a_end, trans=False, src=LIVE, ss=41.9, speed=spW)
tag('3 · YOU SAY YES', s4 + 0.3, s4_end - 0.05)
ov(pill('%dx SPEED' % round(spW), SILK(26), IVORY, INK + (220,), pad=(16, 10), radius=8), 1830, 150, s4a_end + 0.1, s4_end - 0.1)
for i, (name, (k, w_, oc)) in enumerate(zip(['Calendar', 'Sheets', 'Slack', 'Gmail'],
                                           [('S4', 'calendars', 0), ('S4', 'sheet', 0), ('S4', 'slack', 0), ('S4', 'customers', 0)])):
    tt = A(k, w_, oc)
    ov(check_chip(name), 560 + i * 300, 185, tt, s4_end - 0.05)
    anchor('S4 "%s"' % w_, tt, '%s check chip' % name)

# ===== S5 proof / crash / what-if =====
s5 = s4_end
s5a_end = A('S5', 'if') - 0.15 + 0.02   # cut to crash footage just before "If it crashes"
add('clip', s5a_end - s5, trans=False, src=LIVE, ss=F5, speed=1.0)
tag('4 · IT DOUBLE-CHECKS', s5 + 0.1, None)
zooms.append((t36 - 0.25, t36 + 0.1, s5a_end - 0.3, s5a_end - 0.02, 1.3, 1700, 990))
cnt = [pill('%d/36' % n, SILK(120), CORAL, INK + (225,), pad=(34, 18), border=IVORY, radius=16) for n in range(37)]
t36b = A('S5', 'thirty-six', 1)
ovs.append(dict(img=cnt[-1], frames=cnt, count=(t36, t36b + 0.1), cx=760, cy=430, t0=t36, t1=s5a_end, anim='pop'))
ov(pill('CHECKS PASSED', SILK(40), IVORY, INK + (225,), pad=(20, 10), radius=10), 760, 560, t36b, s5a_end)
anchor('S5 "Thirty-six out of thirty-six"', t36, '36/36 burst (footage 79.5) + counter + zoom')
# reliability: crash (16.84) on "crashes", resume (20.75) on "finishes"
t_crash = A('S5', 'crashes'); t_fin = A('S5', 'finishes')
spC = 3.0
lt_c = t_crash - s5a_end
ssC = 16.84 - lt_c * spC
t_resume = s5a_end + (20.75 - ssC) / spC
b1_end = s5a_end + (21.6 - ssC) / spC
add('clip', b1_end - s5a_end, src=REL, ss=ssC, speed=spC)
t_ask = A('S5', 'and', 0) - 0.03
add('clip', t_ask - b1_end, trans=False, src=REL, ss=21.6, speed=1.0)
ov(pill('Crash → resumes, nothing sent twice', MONO(34), IVORY, INK + (235,), pad=(24, 14), border=CORAL, radius=12), 900, 170, t_crash, t_ask - 0.05)
click(t_resume, 1697, 994)
for o in ovs:
    if o['t1'] is None: o['t1'] = t_ask - 0.05
anchor('S5 "crashes halfway"', t_crash, 'reliability crash (footage 16.84)')
anchor('S5 "it finishes"', t_resume, 'resume click (footage 20.75); 36/36 at %.2f' % (s5a_end + (21.47 - ssC) / spC))
# what-if: click 91.96 on "ask", result 94.18 on "show up"
spWI = 2.0
t_wiclick = A('S5', 'ask') + 0.1
ssWI = 91.96 - (t_wiclick - t_ask) * spWI
t_wires = t_ask + (94.18 - ssWI) / spWI
t_before_seg = A('S5', 'shows') - 0.20
add('clip', t_before_seg - t_ask, src=LIVE, ss=ssWI, speed=spWI)
click(t_wiclick, 1094, 85)
s5_end = vo_starts['S5'] + DUR['S5'] + TAIL
tag('5 · WHAT IF?', t_ask + 0.2, s5_end - 0.05)
anchor('S5 "what if Wei doesn\'t show up"', t_wiclick, 'What-if click (footage 91.96); result (94.18) at %.2f' % t_wires)
# risk scan dialog (102.66) on "before"
t_bef = A('S5', 'before')
ssR = 102.66 - (t_bef - t_before_seg)
add('clip', s5_end - t_before_seg, src=LIVE, ss=ssR, speed=1.0)
anchor('S5 "before it happens"', t_bef, 'risk scan dialog (footage 102.66)')

# ===== S6 conclusion =====
s6 = s5_end
vo_starts['S6'] = s6 + 0.10
t_we = A('S6', 'we') - 0.12
add('img', t_we - s6, src=V + '/assets/fal3/4.png', kb=(1.0, 1.15, 960, 520))
pl = lambda s, c=IVORY: pill(s, MONO(64), c, INK + (225,), pad=(30, 14), radius=14)
t_sick = A('S6', 'sick'); t_flat = A('S6', 'flat'); t_no = A('S6', 'no-shows'); t_sec = A('S6', 'seconds')
ov(pl('Sick days.'), 960, 360, t_sick, t_sec - 0.1)
ov(pl('Flat tires.'), 960, 480, t_flat, t_sec - 0.1)
ov(pl('No-shows.'), 960, 600, t_no, t_sec - 0.1)
ov(pl('Seconds, not an hour.', CORAL), 960, 480, t_sec, t_we)
s6_audio_end = vo_starts['S6'] + DUR['S6']
TOTAL_TARGET = s6_audio_end + 1.30
add('outro', TOTAL_TARGET - t_we)
O_D = dict(l1=A('S6', 'we') - t_we, l2=A('S6', 'but') - t_we, big=A('S6', 'second') - t_we, url=A('S6', 'second') + 0.45 - t_we)
anchor('S6 "We can\'t predict the day"', A('S6', 'we'), 'outro line 1')
anchor('S6 "But we can be ready for it"', A('S6', 'but'), 'outro line 2')
anchor('S6 "Second Shift"', A('S6', 'second'), 'SECOND SHIFT + github.com/anirxdh/second-shift')

TOTAL = sum(s['dur'] for s in segs)
NF = int(round(TOTAL * FPS))
print('TOTAL', TOTAL, 'frames', NF, flush=True)
print('vo_starts', {k: round(v, 3) for k, v in vo_starts.items()}, flush=True)
for k in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']:
    print('  %s %.3f -> %.3f' % (k, vo_starts[k], vo_starts[k] + DUR[k]))
print('speeds S2 %.3f S3A %.3f writes %.3f' % (spS2, spA, spW))
for s in segs: print('  seg %-6s %.3f +%.3f ss=%s sp=%s' % (s['kind'], s['start'], s['dur'], s.get('ss'), s.get('speed')))

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
with open(REL_DIR + '/second-shift-demo-v3-female.srt', 'w') as f:
    for i, (a, b, tx) in enumerate(caps):
        nb = min(b, caps[i + 1][0] - 0.01) if i + 1 < len(caps) else b
        f.write('%d\n%s --> %s\n%s\n\n' % (i + 1, srt_t(a), srt_t(nb), tx))
json.dump(dict(vo_starts=vo_starts, anchors=anchors, total=TOTAL), open(WK + '/timeline.json', 'w'), indent=1)
if '--plan' in sys.argv: sys.exit(0)

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
        paste_pop(fr, TITLE_BIG, 960, 400, lt - 0.04, dur - lt + 1)
        paste_pop(fr, TITLE_SUB, 960, 560, lt - T_SUB, dur - lt + 1)
        road_truck(fr, lt, dur, 700)
    else:
        paste_pop(fr, O_BIG, 960, 260, lt - O_D['big'], 99)
        paste_pop(fr, O_L1, 960, 430, lt - O_D['l1'], 99)
        paste_pop(fr, O_L2, 960, 510, lt - O_D['l2'], 99)
        paste_pop(fr, O_URL, 960, 650, lt - O_D['url'], 99)
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
E_SUB = enc(WK + '/v_sub.mp4'); E_NOS = enc(WK + '/v_nosub.mp4')

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
    ins += ['-i', VO + '/%s.mp3' % k]
    ms = int(round(vo_starts[k] * 1000)); fl.append('[%d:a]aresample=48000,adelay=%d|%d[a%d]' % (i, ms, ms, i))
fl.append(''.join('[a%d]' % i for i in range(6)) + 'amix=inputs=6:normalize=0:duration=longest,apad,atrim=0:%.3f,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]' % (fi / FPS))
subprocess.run(['ffmpeg', '-v', 'error', '-y'] + ins + ['-filter_complex', ';'.join(fl), '-map', '[out]', '-c:a', 'aac', '-b:a', '192k', WK + '/audio.m4a'], check=True)
for vin, out in [('v_sub', 'second-shift-demo-v3-female.mp4'), ('v_nosub', 'second-shift-demo-v3-female-nosubs.mp4')]:
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', WK + '/%s.mp4' % vin, '-i', WK + '/audio.m4a', '-map', '0:v', '-map', '1:a', '-c', 'copy', '-shortest', '-movflags', '+faststart', REL_DIR + '/' + out], check=True)
print('DONE', TOTAL, 'frames', fi)
