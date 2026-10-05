#!/usr/bin/env python3
"""Track the progress of a set of JIRA tickets as a stacked burn-up chart.

One bar per *iteration* (the user decides when a new iteration starts). Each
ticket is put in exactly one category, bottom to top:

  applied      status Applied in JIRA (dark green)
  done         applied in the specification (PR merged, or applied earlier),
               but not yet marked Applied in JIRA (light green)
  pr           in an open PR (yellow-green)
  voted        resolved in JIRA (or voted but not entered), not applied (orange)
  disposition  has a proposed resolution, not voted yet (red)
  none         no disposition yet (grey)

Inputs
  --config  JSON file (default .jira-cache/progress-config.json):
    {
      "title": "Pharmacy WG – ticket burn-up",
      "export": ".jira-cache/Jira *.csv",        # glob; the newest file is used
      "delimiter": "|",                          # optional, auto-detected
      "github": "HL7/fhir",                      # optional: read PR states with gh
      "pr_author": "@me",                        # optional, default @me
      "pr_since": "2026-10-01",                  # optional: only PRs created on/after this date
      "pr_ignore": ["FHIR-53306"],               # optional: tickets not to take from PR titles
      "applied_statuses": ["Applied", "Published"],
      "resolved_statuses": ["Resolved - change required"],
      "extra": ["FHIR-59522"],                   # tickets not in the export
      "exclude": [],                             # tickets to leave out
      "pr_open": {"FHIR-57813": 4339},           # manual overrides (merged with gh)
      "pr_merged": {"FHIR-54341": 4327},
      "done_not_marked": ["FHIR-51540"],         # applied earlier, not marked
      "voted_not_entered": ["FHIR-55332"],       # voted, not yet entered in JIRA
      "dispositions_local": ["FHIR-58593"],      # disposition drafted, not yet in JIRA
      "out_dir": ".jira-cache"
    }
  The export is a JIRA CSV export with at least the columns Issue key, Status and
  Resolution (Summary is used when present).

Usage
  progress_chart.py new  [--date YYYY-MM-DD]   add a bar (new iteration)
  progress_chart.py same [--date YYYY-MM-DD]   replace the last bar (same iteration)
  progress_chart.py show                       print the counts without saving

Outputs (in out_dir): progress-data.json, progress.md (tickets per category),
progress.html (single file, reloads every 30 s), and progress-history/
iteration-N.{html,md}. Ask the user whether an update is a new iteration or the
same one before running "new" or "same".
"""
import argparse, csv, datetime, glob, html as H, json, os, re, subprocess, sys

ORDER = [('applied', 'Applied (marked in Jira)', '#1b5e20'), ('done', 'Done, to mark Applied in Jira', '#66bb6a'),
         ('pr', 'In PR', '#c0ca33'), ('voted', 'Voted, not applied', '#fb8c00'),
         ('disposition', 'Disposition, not voted', '#e53935'), ('none', 'No disposition', '#9e9e9e')]
KEY = re.compile(r'\b[A-Z][A-Z0-9]+-\d+\b')


def read_export(pattern, delim=None):
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    files = [f for f in files if os.path.getsize(f) > 0]
    if not files:
        sys.exit(f'no export found for {pattern}')
    f = files[-1]
    first = open(f, encoding='utf-8-sig').readline()
    d = delim or ('|' if first.count('|') > first.count(',') else ',')
    rows = list(csv.reader(open(f, encoding='utf-8-sig'), delimiter=d))
    hdr = rows[0]
    def col(name):
        for i, h in enumerate(hdr):
            if h == name or h.endswith('(' + name + ')'):
                return i
        return None
    ik, ist, ires, isu = col('Issue key'), col('Status'), col('Resolution'), col('Summary')
    out = {}
    for r in rows[1:]:
        if len(r) != len(hdr):
            continue
        out[r[ik]] = {'status': r[ist], 'resolution': r[ires] if ires is not None else '',
                      'summary': r[isu] if isu is not None else ''}
    return f, out


def github_prs(repo, author, since=None, ignore=()):
    """{ticket: (number, state)} from the author's PRs whose title names a ticket."""
    try:
        res = subprocess.run(['gh', 'pr', 'list', '--repo', repo, '--author', author, '--state', 'all',
                              '--limit', '300', '--json', 'number,title,state,createdAt'],
                             capture_output=True, text=True, timeout=120)
        prs = json.loads(res.stdout or '[]')
    except Exception as e:  # noqa: BLE001
        print(f'warning: could not read PRs from {repo}: {e}', file=sys.stderr)
        return {}
    out = {}
    for p in sorted(prs, key=lambda p: p['number']):
        if since and p.get('createdAt', '')[:10] < since:
            continue
        for k in KEY.findall(p['title']):
            if k in ignore:
                continue
            out[k] = (p['number'], p['state'])        # later PRs win
    return out


def classify(cfg, export):
    excl = set(cfg.get('exclude', []))
    keys = [k for k in list(export) + cfg.get('extra', []) if k not in excl]
    keys = list(dict.fromkeys(keys))
    applied = set(cfg.get('applied_statuses', ['Applied', 'Published']))
    resolved = set(cfg.get('resolved_statuses', ['Resolved - change required']))
    pr_open = dict(cfg.get('pr_open', {}))
    pr_merged = dict(cfg.get('pr_merged', {}))
    if cfg.get('github'):
        for k, (n, st) in github_prs(cfg['github'], cfg.get('pr_author', '@me'), cfg.get('pr_since'), set(cfg.get('pr_ignore', []))).items():
            if st == 'MERGED':
                pr_merged.setdefault(k, n)
            elif st == 'OPEN' and k not in pr_merged:
                pr_open.setdefault(k, n)
    done = set(cfg.get('done_not_marked', [])) | set(pr_merged)
    voted = set(cfg.get('voted_not_entered', []))
    local = set(cfg.get('dispositions_local', []))
    cat = {}
    for k in keys:
        e = export.get(k, {'status': '', 'resolution': ''})
        if e['status'] in applied:
            cat[k] = 'applied'
        elif k in done:
            cat[k] = 'done'
        elif k in pr_open:
            cat[k] = 'pr'
        elif e['status'] in resolved or k in voted:
            cat[k] = 'voted'
        elif e['resolution'] or k in local:
            cat[k] = 'disposition'
        else:
            cat[k] = 'none'
    return cat, pr_open, pr_merged


def page(title, data):
    series = json.dumps([{'key': c, 'label': l, 'color': col} for c, l, col in ORDER])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{H.escape(title)}</title>
<style>
 :root {{ --fg:#1f2328; --muted:#59636e; --bg:#ffffff; --grid:#d8dee4; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --fg:#e6edf3; --muted:#9198a1; --bg:#0d1117; --grid:#30363d; }} }}
 body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; color: var(--fg); background: var(--bg); margin: 24px; }}
 h1 {{ font-size: 1.3rem; margin: 0 0 4px; }} .sub {{ color: var(--muted); font-size: .9rem; margin-bottom: 16px; }}
 .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin: 8px 0 16px; font-size:.9rem; }}
 .legend span::before {{ content:""; display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:6px; vertical-align:-1px; background: var(--c); }}
 svg text {{ fill: var(--fg); font-size: 12px; }} .axis {{ stroke: var(--grid); }}
 table {{ border-collapse: collapse; margin-top: 18px; font-size: .9rem; }} th, td {{ border-bottom: 1px solid var(--grid); padding: 4px 10px; text-align: right; }} th:first-child, td:first-child {{ text-align:left; }}
</style></head><body>
<h1>{H.escape(title)}</h1>
<div class="sub">Steps: resolution → vote → applied. Dark green = marked Applied in Jira (bottom); light green = done, still to mark in Jira. Reloads every 30 seconds. * = reconstructed. Last iteration: <b id="last"></b>.</div>
<div class="legend" id="legend"></div>
<svg id="chart" width="100%" height="420" role="img" aria-label="Stacked bar chart of ticket status per iteration"></svg>
<table id="tbl"></table>
<script>
const SERIES = {series};
const DATA = {json.dumps(data)};
document.getElementById('last').textContent = DATA.length ? ('#' + DATA[DATA.length-1].iteration + ' · ' + DATA[DATA.length-1].date) : '–';
document.getElementById('legend').innerHTML = SERIES.map(s => `<span style="--c:${{s.color}}">${{s.label}}</span>`).join('');
const svg = document.getElementById('chart'); const W = svg.clientWidth || 900, Hh = 420, m = {{l:46,r:16,t:16,b:40}};
const maxT = Math.max(1, ...DATA.map(d => SERIES.reduce((a,s)=>a+(d[s.key]||0),0)));
const yTop = Math.ceil(maxT/20)*20, ih = Hh-m.t-m.b, iw = W-m.l-m.r;
const bw = Math.min(70, (iw-12)/Math.max(DATA.length,1)-8), step = bw + 8;
let g = '';
for (let v=0; v<=yTop; v+=20) {{ const y = m.t+ih-ih*v/yTop; g += `<line class="axis" x1="${{m.l}}" x2="${{W-m.r}}" y1="${{y}}" y2="${{y}}"/><text x="${{m.l-6}}" y="${{y+4}}" text-anchor="end">${{v}}</text>`; }}
DATA.forEach((d,i) => {{ let y = m.t+ih; const x = m.l+12+step*i;
  SERIES.forEach(s => {{ const n = d[s.key]||0; if(!n) return; const h = ih*n/yTop; y -= h;
    g += `<rect x="${{x}}" y="${{y}}" width="${{bw}}" height="${{h}}" fill="${{s.color}}"><title>${{s.label}}: ${{n}}</title></rect>`;
    if (h > 14) g += `<text x="${{x+bw/2}}" y="${{y+h/2+4}}" text-anchor="middle" style="fill:#fff;font-weight:600">${{n}}</text>`; }});
  g += `<text x="${{x+bw/2}}" y="${{Hh-m.b+15}}" text-anchor="middle">#${{d.iteration}}${{d.note ? '*' : ''}}</text><text x="${{x+bw/2}}" y="${{Hh-m.b+29}}" text-anchor="middle" style="font-size:10px">${{d.date.slice(5)}}</text>`; }});
svg.innerHTML = g;
const tot = d => SERIES.reduce((a,s)=>a+(d[s.key]||0),0);
document.getElementById('tbl').innerHTML = '<tr><th>Iteration</th>' + SERIES.map(s=>`<th>${{s.label}}</th>`).join('') + '<th>Total</th></tr>' +
  DATA.map(d => `<tr><td>#${{d.iteration}}${{d.note ? '*' : ''}} · ${{d.date}}</td>` + SERIES.map(s=>`<td>${{d[s.key]||0}}</td>`).join('') + `<td>${{tot(d)}}</td></tr>`).join('');
</script></body></html>
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['new', 'same', 'show'])
    ap.add_argument('--config', default='.jira-cache/progress-config.json')
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))
    out = cfg.get('out_dir', os.path.dirname(a.config) or '.')
    exp_file, export = read_export(cfg['export'], cfg.get('delimiter'))
    cat, pr_open, pr_merged = classify(cfg, export)
    counts = {c: sum(1 for v in cat.values() if v == c) for c, _, _ in ORDER}
    total = sum(counts.values())
    print(f'export: {exp_file}')
    print('counts:', counts, 'total', total)
    if a.mode == 'show':
        return 0
    dp = os.path.join(out, 'progress-data.json')
    data = json.load(open(dp, encoding='utf-8')) if os.path.exists(dp) else []
    if a.mode == 'same' and data:
        data[-1] = {'iteration': data[-1]['iteration'], 'date': a.date, **counts}
    else:
        data.append({'iteration': max([d['iteration'] for d in data] or [0]) + 1, 'date': a.date, **counts})
    it = data[-1]['iteration']
    json.dump(data, open(dp, 'w', encoding='utf-8'), indent=1)
    title = cfg.get('title', 'Ticket burn-up')
    summ = {k: v.get('summary', '') for k, v in export.items()}
    md = [f'# {title} – status', '', f'Iteration {it} ({a.date}), {total} tickets. Source: `{os.path.basename(exp_file)}`.', '',
          '| Status | Count |', '|---|---|'] + [f'| {l} | {counts[c]} |' for c, l, _ in ORDER] + [f'| **Total** | **{total}** |', '']
    for c, l, _ in ORDER:
        ks = sorted([k for k, v in cat.items() if v == c], key=lambda x: (x.split('-')[0], int(x.split('-')[1])))
        md += [f'## {l} ({len(ks)})', '']
        for k in ks:
            pr = pr_open.get(k) or pr_merged.get(k)
            md.append(f'- {k}' + (f' – {summ[k]}' if summ.get(k) else '') + (f' (PR #{pr})' if pr else ''))
        md.append('')
    html_text = page(title, data)
    open(os.path.join(out, 'progress.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(md))
    open(os.path.join(out, 'progress.html'), 'w', encoding='utf-8', newline='\n').write(html_text)
    hist = os.path.join(out, 'progress-history'); os.makedirs(hist, exist_ok=True)
    open(os.path.join(hist, f'iteration-{it}.html'), 'w', encoding='utf-8', newline='\n').write(html_text)
    open(os.path.join(hist, f'iteration-{it}.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(md))
    print(f'iteration {it} written to {out}/progress.html')
    return 0


if __name__ == '__main__':
    sys.exit(main())
