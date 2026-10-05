"""Convert the Jira/Confluence wiki markup used in the agenda/disposition files to plain HTML,
for copy-paste into the Confluence editor (which keeps tables, links and lists from rendered HTML).
Usage: python wiki2html.py input.md output.html"""
import html, re, sys

def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'\[([^\]|]+)\|([^\]]+)\]', r'<a href="\2">\1</a>', t)          # [text|url]
    t = re.sub(r'\[(https?://[^\]]+)\]', r'<a href="\1">\1</a>', t)             # [url]
    t = re.sub(r'\{\{(.+?)\}\}', r'<code>\1</code>', t)                         # {{code}}
    t = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<b>\1</b>', t)   # *bold*
    t = re.sub(r'(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])', r'<i>\1</i>', t)      # _italic_
    return t

def cells(line, sep):
    # split on the separator but not inside [link|url]
    out, cur, depth, i = [], '', 0, 0
    while i < len(line):
        if line[i] == '[': depth += 1
        if line[i] == ']': depth = max(0, depth - 1)
        if depth == 0 and line.startswith(sep, i):
            out.append(cur); cur = ''; i += len(sep); continue
        cur += line[i]; i += 1
    out.append(cur)
    return [c.strip() for c in out[1:-1]]

def convert(src):
    out, lines, i = [], src.replace('\r\n', '\n').split('\n'), 0
    in_ul = in_ol = in_table = in_code = False
    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: out.append('</ul>'); in_ul = False
        if in_ol: out.append('</ol>'); in_ol = False
    for line in lines:
        if in_code:
            if line.startswith('{code}') or line.startswith('{noformat}'):
                out.append('</pre>'); in_code = False
            else:
                out.append(html.escape(line))
            continue
        if line.startswith('{code') or line.startswith('{noformat}'):
            close_lists(); out.append('<pre>'); in_code = True; continue
        if line.startswith('{quote}'):
            close_lists(); out.append('<blockquote>' if '<blockquote>' not in out[-3:] or out[-1] == '</blockquote>' else '</blockquote>'); continue
        if line.startswith('||') or (line.startswith('|') and line.rstrip().endswith('|')):
            close_lists()
            if not in_table: out.append('<table border="1" cellpadding="4" cellspacing="0">'); in_table = True
            if line.startswith('||'):
                out.append('<tr>' + ''.join(f'<th>{inline(c)}</th>' for c in cells(line.rstrip(), '||')) + '</tr>')
            else:
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in cells(line.rstrip(), '|')) + '</tr>')
            continue
        if in_table: out.append('</table>'); in_table = False
        m = re.match(r'h([1-6])\.\s+(.*)', line)
        if m:
            close_lists(); out.append(f'<h{m.group(1)}>{inline(m.group(2))}</h{m.group(1)}>'); continue
        m = re.match(r'\*(\d+)\.\*\s+(.*)', line)          # agenda item "*4.* Title"
        if m:
            close_lists(); out.append(f'<h3>{m.group(1)}. {inline(m.group(2))}</h3>'); continue
        m = re.match(r'(\*+|#+)\s+(.*)', line)
        if m:
            tag = 'ul' if m.group(1)[0] == '*' else 'ol'
            if tag == 'ul' and not in_ul: close_lists(); out.append('<ul>'); in_ul = True
            if tag == 'ol' and not in_ol: close_lists(); out.append('<ol>'); in_ol = True
            out.append(f'<li>{inline(m.group(2))}</li>'); continue
        close_lists()
        if line.strip() == '----': out.append('<hr/>'); continue
        if line.strip(): out.append(f'<p>{inline(line)}</p>')
    close_lists()
    if in_table: out.append('</table>')
    title = re.search(r'h1\.\s+(.*)', src)
    return ('<!doctype html><html><head><meta charset="utf-8"><title>' + html.escape(title.group(1) if title else 'Agenda') +
            '</title><style>body{font-family:sans-serif;max-width:1100px;margin:16px} table{border-collapse:collapse} '
            'th{background:#eee} pre{background:#f6f6f6;padding:8px}</style></head><body>\n' + '\n'.join(out) + '\n</body></html>\n')

if __name__ == '__main__':
    src = open(sys.argv[1], encoding='utf-8').read()
    open(sys.argv[2], 'w', encoding='utf-8').write(convert(src))
    print('written', sys.argv[2])
