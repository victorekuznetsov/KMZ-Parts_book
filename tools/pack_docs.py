#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_docs.py — собрать самодостаточный «читатель руководств» в один html-файл.

Встраивает docs.js (текст+оглавление) и docs_img/*.jpg (страницы) как data:-URI
в шаблон tools/docs_viewer.html. Результат открывается офлайн двойным кликом,
без соседних папок и без Python.

Использование:
    python3 tools/pack_docs.py                       # -> catalog_book/Руководства.html
    python3 tools/pack_docs.py --dir catalog_book -o "Руководства БС-215.html"
"""
import argparse, base64, json, os, re, sys

def pack(build_dir='catalog_book', out=None, template=None):
    data_path = os.path.join(build_dir, 'docs.js')
    img_dir = os.path.join(build_dir, 'docs_img')
    if template is None:
        template = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs_viewer.html')
    for p in (data_path, img_dir, template):
        if not os.path.exists(p):
            raise FileNotFoundError(f'не найдено: {p}')
    html = open(template, encoding='utf-8').read()
    data_js = open(data_path, encoding='utf-8').read()
    m = re.search(r'window\.DOCS=(.*);\s*$', data_js.strip(), re.S)
    if not m:
        raise ValueError('docs.js: формат не совпадает')
    docs = json.loads(m.group(1))
    names = set()
    for d in docs['docs']:
        for pg in d['pages']:
            names.add(pg['img'])
    assets, missing = {}, []
    for name in sorted(names):
        fp = os.path.join(img_dir, name)
        if not os.path.exists(fp): missing.append(name); continue
        assets[name] = 'data:image/jpeg;base64,' + base64.b64encode(open(fp, 'rb').read()).decode('ascii')
    assets_js = json.dumps(assets, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = html.replace('<script src="docs.js"></script>', '')
    inline = f'<script>window.DOCS={m.group(1)};\nwindow.DOCS_ASSETS={assets_js};</script>\n'
    html = html.replace('<noscript>', inline + '<noscript>', 1)
    out = out or os.path.join(build_dir, 'Руководства.html')
    open(out, 'w', encoding='utf-8').write(html)
    return out, os.path.getsize(out) / 1024 / 1024, len(assets), missing

def main():
    ap = argparse.ArgumentParser(description='Собрать читатель руководств в один html')
    ap.add_argument('--dir', default='catalog_book')
    ap.add_argument('-o', '--out', default=None)
    a = ap.parse_args()
    try:
        out, mb, n, missing = pack(a.dir, a.out)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f'{e} — сначала выполните tools/build_docs.py')
    if missing:
        print(f'! {len(missing)} изображений не найдено (пропущены)')
    print(f'Готово: {out}  ({mb:.1f} МБ, страниц встроено: {n})')
    print('Самодостаточный файл — открывается офлайн, без Python.')

if __name__ == '__main__':
    main()
