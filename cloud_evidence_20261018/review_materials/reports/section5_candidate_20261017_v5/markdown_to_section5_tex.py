from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'section5_cn_full_body_20261017_v5.md'
OUTPUT = ROOT / 'section5_cn_full_body_20261017_v5.tex'


def inline(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)

    def code(match):
        value = match.group(1).replace('_', r'\_').replace('%', r'\%')
        return r'\texttt{' + value + '}'

    tick = chr(96)
    text = re.sub(tick + r'([^' + tick + r']+)' + tick, code, text)
    parts = re.split(r'(\$[^$]*\$)', text)
    for i, part in enumerate(parts):
        if not (part.startswith('$') and part.endswith('$')):
            part = re.sub(r'(?<!\\)%', r'\%', part)
            part = part.replace('&', r'\&')
            parts[i] = part
    return ''.join(parts)


def parse_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def make_table(caption: str, rows: list[list[str]], note: str, index: int) -> str:
    ncols = len(rows[0])
    if ncols == 7:
        spec = 'c' + 'Y' * 6
    elif ncols == 6:
        spec = 'cc' + 'Y' * 4
    elif ncols == 5:
        spec = 'l' + 'Y' * 4
    elif ncols == 4:
        spec = 'lYYY'
    else:
        spec = 'l' + 'Y' * (ncols - 1)
    out = [r'\begin{table}[htbp]', r'\centering', r'\small',
           r'\caption{' + inline(caption) + '}',
           r'\label{tab:section5_' + str(index) + '}',
           r'\begin{tabularx}{\textwidth}{' + spec + '}', r'\toprule']
    row_end = ' ' + chr(92) * 4
    out.append(' & '.join(r'\textbf{' + inline(cell) + '}' for cell in rows[0]) + row_end)
    out.append(r'\midrule')
    for row in rows[1:]:
        out.append(' & '.join(inline(cell) for cell in row) + row_end)
    out.extend([r'\bottomrule', r'\end{tabularx}', r'\par\vspace{3pt}',
                r'\begin{minipage}{0.99\linewidth}', r'\footnotesize', inline(note),
                r'\end{minipage}', r'\end{table}'])
    return '\n'.join(out)


def main() -> None:
    lines = SOURCE.read_text(encoding='utf-8').splitlines()
    out = [r'\documentclass[UTF8,a4paper,11pt]{ctexart}',
           r'\usepackage[margin=2.2cm]{geometry}',
           r'\usepackage{amsmath,amssymb,booktabs,tabularx,array,graphicx,float,caption}',
           r'\graphicspath{{figures/}}',
           r'\newcolumntype{Y}{>{\centering\arraybackslash}X}',
           r'\captionsetup{font=small,labelfont=bf}',
           r'\setlength{\emergencystretch}{3em}',
           r'\numberwithin{table}{section}', r'\numberwithin{figure}{section}',
           r'\setcounter{section}{4}', r'\begin{document}', '']
    i = 0
    table_i = 0
    figure_i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('# '):
            title = re.sub(r'^5\.\s*', '', line[2:])
            out.append(r'\section{' + inline(title) + '}')
            i += 1
            continue
        if line.startswith('### 表 '):
            caption = re.sub(r'^### 表\s*5\.\d+\s*[　 ]*', '', line)
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_line = lines[i].strip()
                if not set(table_line) <= set('|:- '):
                    table_lines.append(parse_row(table_line))
                i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            note = lines[i].strip() if i < len(lines) and lines[i].strip().startswith('注：') else ''
            if note:
                note = note[2:]
                i += 1
            table_i += 1
            out.append(make_table(caption, table_lines, note, table_i))
            out.append('')
            continue
        if line.startswith('### '):
            title = re.sub(r'^5\.\d+\s*', '', line[4:])
            out.append(r'\subsection{' + inline(title) + '}')
            i += 1
            continue
        if line.startswith('!['):
            m = re.match(r'!\[(.*?)\]\((.*?)\)', line)
            if not m:
                raise ValueError(f'Bad image line: {line}')
            caption = re.sub(r'^图\s*5\.\d+\s*[　 ]*', '', m.group(1))
            filename = Path(m.group(2)).stem + '.pdf'
            figure_i += 1
            out.extend([r'\begin{figure}[htbp]', r'\centering',
                        r'\includegraphics[width=0.99\linewidth]{' + filename + '}',
                        r'\caption{' + inline(caption) + '}',
                        r'\label{fig:section5_' + str(figure_i) + '}',
                        r'\end{figure}'])
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith('**图 '):
                note = re.sub(r'^\*\*图\s*5\.\d+\s*注：\*\*\s*', '', lines[i].strip())
                out.append(r'\noindent\textbf{图注：} ' + inline(note))
                i += 1
            out.append('')
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].startswith('!['):
            paragraph.append(lines[i].strip())
            i += 1
        out.append(inline(' '.join(paragraph)))
        out.append('')
    out.append(r'\end{document}')
    tex = '\n'.join(out) + '\n'
    slash = chr(92)
    tex = tex.replace(slash + slash, slash)
    OUTPUT.write_text(tex, encoding='utf-8')
    print(OUTPUT)


if __name__ == '__main__':
    main()
