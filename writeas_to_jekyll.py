#!/usr/bin/env python3
"""
Convert one blog (collection) from a write.as JSON export into a
GitHub Pages-ready Jekyll site.

Usage:
    python3 writeas_to_jekyll.py EXPORT.json --alias 575-life --out 575-life-site

What it does
- Writes each post to _posts/YYYY-MM-DD-<slug>.md with front matter
- Keeps write.as URLs exactly (https://575.life/<slug>, /page/2, ...)
- Uses the first line of an untitled post as its <title> (not shown on the page,
  same as write.as)
- Moves #hashtags into front-matter tags
- Downloads i.snap.as images into assets/img/ and rewrites the links
  (use --no-images to skip; downloading needs normal internet access)
- Writes _config.yml, layouts, CSS, the home page with pagination, CNAME and Gemfile
"""
import argparse
import json
import os
import re
import sys
import textwrap
import urllib.request
from datetime import datetime

HASHTAG = re.compile(r"(?<![\w/#&])#([A-Za-z][\w-]*)")
SNAP_IMG = re.compile(r"https?://i\.snap\.as/[A-Za-z0-9]+\.(?:jpe?g|png|gif|webp)", re.I)


def yaml_str(s):
    # JSON strings are valid YAML scalars and handle quotes/colons safely
    return json.dumps(s, ensure_ascii=False)


def clean_body(body):
    lines = [ln.strip() for ln in body.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def title_from(post, body):
    if post.get("title"):
        return post["title"].strip()
    first = body.split("\n", 1)[0]
    return re.sub(r"\s*/\s*$", "", first).strip() or post["slug"]


def fetch_images(body, out_dir, enabled):
    if not enabled:
        return body
    img_dir = os.path.join(out_dir, "assets", "img")
    for url in sorted(set(SNAP_IMG.findall(body))):
        name = url.rsplit("/", 1)[1]
        dest = os.path.join(img_dir, name)
        if not os.path.exists(dest):
            os.makedirs(img_dir, exist_ok=True)
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception as e:  # keep the remote link if download fails
                print(f"  ! could not download {url}: {e}", file=sys.stderr)
                continue
        body = body.replace(url, "{{ '/assets/img/" + name + "' | relative_url }}")
    return body


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build(export, alias, out, per_page, images):
    cols = {c["alias"]: c for c in export.get("collections", [])}
    if alias not in cols:
        sys.exit(f"Blog '{alias}' not found. Available: {', '.join(cols)}")
    col = cols[alias]
    posts = col.get("posts") or []
    domain = col.get("domain") or ""
    site_title = (col.get("title") or alias).strip()
    description = (col.get("description") or "").replace("</br>", "\n").replace("<br>", "\n").strip()

    for p in posts:
        body = clean_body(p["body"])
        tags = sorted(set(p.get("tags") or []) | set(HASHTAG.findall(body)))
        body = HASHTAG.sub(r"\1", body) if tags else body
        body = fetch_images(body, out, images)
        created = datetime.strptime(p["created"], "%Y-%m-%dT%H:%M:%SZ")
        fm = [
            "---",
            f"title: {yaml_str(title_from(p, body))}",
            f"date: {created:%Y-%m-%d %H:%M:%S} +0000",
            f"permalink: /{p['slug']}",
        ]
        if p.get("updated") and p["updated"] != p["created"]:
            u = datetime.strptime(p["updated"], "%Y-%m-%dT%H:%M:%SZ")
            fm.append(f"last_modified_at: {u:%Y-%m-%d %H:%M:%S} +0000")
        if tags:
            fm.append("tags: [" + ", ".join(yaml_str(t) for t in tags) + "]")
        fm.append(f"writeas_id: {p['id']}")
        fm.append("---")
        write(os.path.join(out, "_posts", f"{created:%Y-%m-%d}-{p['slug']}.md"),
              "\n".join(fm) + "\n\n" + body + "\n")

    url = f"https://{domain}" if domain else ""
    write(os.path.join(out, "_config.yml"), textwrap.dedent(f"""\
        title: {yaml_str(site_title)}
        description: {yaml_str(description)}
        url: {yaml_str(url)}
        baseurl: ""
        markdown: kramdown
        permalink: /:title
        paginate: {per_page}
        paginate_path: "/page/:num/"
        plugins:
          - jekyll-paginate
          - jekyll-feed
          - jekyll-sitemap
          - jekyll-seo-tag
        exclude: [README.md, Gemfile, Gemfile.lock, writeas_to_jekyll.py]
        """))

    if domain:
        write(os.path.join(out, "CNAME"), domain + "\n")

    write(os.path.join(out, "Gemfile"), textwrap.dedent("""\
        source "https://rubygems.org"
        gem "github-pages", group: :jekyll_plugins
        gem "webrick"
        """))

    write(os.path.join(out, "_layouts", "default.html"), textwrap.dedent("""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          {% seo %}
          {% feed_meta %}
          <link rel="stylesheet" href="{{ '/assets/css/site.css' | relative_url }}">
        </head>
        <body id="{% if page.layout == 'post' %}post{% else %}collection{% endif %}">
          <header>
            <h1 id="blog-title"><a href="{{ '/' | relative_url }}">{{ site.title }}</a></h1>
            {% if page.layout != 'post' and site.description != '' %}
            <div class="description">{{ site.description | markdownify }}</div>
            {% endif %}
          </header>
          <main>
          {{ content }}
          </main>
        </body>
        </html>
        """))

    write(os.path.join(out, "_layouts", "post.html"), textwrap.dedent("""\
        ---
        layout: default
        ---
        <article class="h-entry">
          <div class="e-content">{{ content }}</div>
        </article>
        """))

    write(os.path.join(out, "index.html"), textwrap.dedent("""\
        ---
        layout: default
        ---
        {% for post in paginator.posts %}
        <article class="h-entry">
          <div class="e-content">{{ post.content }}</div>
          <a class="permalink" href="{{ post.url | relative_url }}">{{ post.date | date: "%B %-d, %Y" }}</a>
        </article>
        {% endfor %}
        {% if paginator.total_pages > 1 %}
        <nav id="paging">
          {% if paginator.previous_page %}<a href="{{ paginator.previous_page_path | relative_url }}" title="Newer">&#8672;</a>{% endif %}
          {% if paginator.next_page %}<a href="{{ paginator.next_page_path | relative_url }}" title="Older">&#8674;</a>{% endif %}
        </nav>
        {% endif %}
        """))

    write(os.path.join(out, "404.html"), textwrap.dedent("""\
        ---
        layout: default
        permalink: /404.html
        sitemap: false
        ---
        <article><div class="e-content"><p>this page drifted<br>like a leaf on the water<br><a href="{{ '/' | relative_url }}">return home</a></p></div></article>
        """))

    # Styling carried over from the write.as custom CSS for this blog
    write(os.path.join(out, "assets", "css", "site.css"), textwrap.dedent("""\
        @import url('https://api.fontshare.com/v2/css?f[]=montserrat@100,300&f[]=sentient@300&display=swap');

        * { font-family: 'Sentient', serif; box-sizing: border-box; }
        html { font-size: 16px; }
        body { max-width: 550px; margin: 0 auto; padding: 3em 1.25em 6em; color: #111; background: #fff; }

        header { text-align: center; margin-bottom: 5em; }
        #blog-title { margin: 0; font-weight: 300; }
        #blog-title a { font-family: 'Montserrat', sans-serif; font-weight: 300; font-size: 1.7em; color: #444; text-decoration: none; padding: 4px 8px; }
        #post #blog-title a { font-size: 1.2em; }
        .description, .description * { font-family: 'Montserrat', sans-serif; font-weight: 300; color: #888; line-height: 1.1em; }
        .description p { margin: .35em 0; white-space: pre-line; }

        a { font-family: 'Montserrat', sans-serif; color: #444; }
        a:hover { color: #888; }

        /* write.as keeps single line breaks; keep them here too */
        article .e-content p { white-space: pre-line; line-height: 1.9em; font-size: 1.3em; margin: 0 0 .6em; }
        #collection article { margin-bottom: 180px; }
        .permalink { font-size: .85em; color: #aaa; text-decoration: none; }
        img { display: block; margin: 0 auto; max-width: 100%; }

        #paging { display: flex; justify-content: space-between; font-size: 2em; }
        #paging a { text-decoration: none; }
        #paging a[title="Older"]:only-child { margin-left: auto; }

        @media (prefers-color-scheme: dark) {
          body { color: #eee; background: #111; }
          a, #blog-title a { color: #ccc; }
          a:hover { color: #888; }
        }
        """))

    write(os.path.join(out, "README.md"), textwrap.dedent(f"""\
        # {site_title}

        Jekyll site for GitHub Pages, converted from the write.as blog `{alias}`
        ({len(posts)} posts). Add a post by dropping a file into `_posts/` named
        `YYYY-MM-DD-slug.md` with this at the top:

        ```
        ---
        title: "first line of the haiku"
        date: 2026-11-21 12:00:00 -0500
        permalink: /first-line-of-the-haiku
        ---
        ```
        """))
    return len(posts), domain


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="write.as JSON export file")
    ap.add_argument("--alias", required=True, help="blog alias, e.g. 575-life")
    ap.add_argument("--out", help="output folder (default: <alias>-site)")
    ap.add_argument("--per-page", type=int, default=10, help="posts per home page (default 10)")
    ap.add_argument("--no-images", action="store_true", help="leave snap.as image links as they are")
    a = ap.parse_args()
    with open(a.export, encoding="utf-8") as f:
        export = json.load(f)
    out = a.out or f"{a.alias}-site"
    n, domain = build(export, a.alias, out, a.per_page, not a.no_images)
    print(f"Wrote {n} posts to {out}/" + (f" (CNAME: {domain})" if domain else ""))


if __name__ == "__main__":
    main()
