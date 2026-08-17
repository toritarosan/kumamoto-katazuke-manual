# -*- coding: utf-8 -*-
"""index.html の機械検証（更新のたびに実行する）

    python tools/verify.py            # タグ・アンカー・tel の検証のみ（速い）
    python tools/verify.py --urls     # 外部URLのHTTPステータスも確認（数十秒）

チェック内容:
  1) HTMLタグの開閉整合
  2) ページ内アンカー(#...)のリンク切れ
  3) tel: リンクと表示されている番号の数字一致
  4) 外部URLのHTTPステータス（--urls 指定時）

既知の誤検知:
  - gov-online.go.jp は 403 を返すことがあるがボット弾き。実ブラウザでは正常表示。
  - 報道記事のURLは消えやすい。404 が出たら記事の差し替えを検討する。
"""
import re
import ssl
import sys
import urllib.error
import urllib.request
import concurrent.futures
from html.parser import HTMLParser
from pathlib import Path

HTML_PATH = Path(__file__).resolve().parent.parent / "index.html"
VOID = {"meta", "link", "br", "img", "hr", "input", "source", "wbr"}


class Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []
        self.ids = set()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            self.ids.add(d["id"])
        if tag == "a" and "href" in d:
            self.hrefs.append(d["href"])
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"閉じタグ過多: </{tag}> at {self.getpos()}")
            return
        open_tag, pos = self.stack.pop()
        if open_tag != tag:
            self.errors.append(
                f"タグ不整合: <{open_tag}>(open {pos}) と </{tag}>(close {self.getpos()})"
            )


def check_url(url):
    ctx = ssl.create_default_context()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) link-check"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            return url, r.status
    except urllib.error.HTTPError as e:
        return url, e.code
    except Exception as e:
        return url, f"ERR {type(e).__name__}"


def main():
    html = HTML_PATH.read_text(encoding="utf-8")
    c = Checker()
    c.feed(html)
    for tag, pos in c.stack:
        c.errors.append(f"未閉鎖タグ: <{tag}> at {pos}")

    failed = False

    print("=== 1) タグ整合 ===")
    if c.errors:
        failed = True
        print("\n".join(c.errors))
    else:
        print("OK")

    print("\n=== 2) ページ内アンカー ===")
    anchors = [h[1:] for h in c.hrefs if h.startswith("#")]
    missing = sorted({a for a in anchors if a not in c.ids})
    print(f"アンカーリンク {len(anchors)}件 / id {len(c.ids)}件")
    if missing:
        failed = True
        print(f"リンク切れ: {missing}")
    else:
        print("OK (リンク切れなし)")

    print("\n=== 3) tel:リンクの突合 ===")
    problems = []
    for m in re.finditer(r'href="tel:([^"]+)">([^<]+)</a>', html):
        href_digits = re.sub(r"\D", "", m.group(1).replace("%23", "#"))
        disp_digits = re.sub(r"\D", "", m.group(2))
        if href_digits != disp_digits:
            problems.append(f"  不一致: tel:{m.group(1)} vs 表示 {m.group(2)}")
    tels = re.findall(r'href="tel:([^"]+)"', html)
    if problems:
        failed = True
        print("\n".join(problems))
    else:
        print(f"OK (tel:リンク {len(tels)}件すべて一致)")

    if "--urls" in sys.argv:
        print("\n=== 4) 外部URLのHTTPステータス ===")
        urls = sorted({m.group(1) for m in re.finditer(r'href="(https?://[^"]+)"', html)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(check_url, urls))
        ng = [r for r in results if r[1] != 200]
        print(f"200 OK: {len(results) - len(ng)}/{len(results)}")
        for url, status in ng:
            failed = True
            print(f"  [{status}] {url}")

    print("\n" + ("NG: 上記を修正してください" if failed else "すべてOK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
