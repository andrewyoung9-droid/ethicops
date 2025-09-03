from pathlib import Path
import re, json

root = Path(".")
html_files = sorted(root.glob("*.html"))

# ===== Config (EthicOps only) =====
DOMAIN = "ethicops.org"
NAME = "EthicOps"

# Role mapping -> canonical local-part
local_map = {
    "hello":"hello","contact":"hello","info":"hello",
    "support":"support","help":"support",
    "security":"security",
    "press":"press","media":"press",
    "billing":"billing","sales":"billing",
    "abuse":"abuse","postmaster":"postmaster"
}

# Footer block (inserted once per page)
footer_block = """
<div id="contacts-ethicops" style="margin-top:1.25rem;font-size:.95rem;line-height:1.5">
  <strong>Contact {NAME}:</strong>
  <a href="mailto:hello@{DOMAIN}?subject=General%20Inquiry%20-%20EthicOps">hello@{DOMAIN}</a> &middot;
  <a href="mailto:support@{DOMAIN}?subject=Support%20Request%20-%20Kame-Ha">support@{DOMAIN}</a> &middot;
  <a href="mailto:security@{DOMAIN}?subject=Vulnerability%20Disclosure%20-%20EthicOps">security@{DOMAIN}</a> &middot;
  <a href="mailto:press@{DOMAIN}?subject=Media%20Inquiry%20-%20EthicOps">press@{DOMAIN}</a> &middot;
  <a href="mailto:billing@{DOMAIN}?subject=Billing%20Question%20-%20EthicOps">billing@{DOMAIN}</a>
</div>
""".strip().format(NAME=NAME, DOMAIN=DOMAIN)

# Minimal Organization JSON-LD (inserted in <head> if missing)
json_ld = {
  "@context":"https://schema.org",
  "@type":"Organization",
  "name": NAME,
  "url": f"https://{DOMAIN}/",
  "contactPoint": [
    {"@type":"ContactPoint","contactType":"customer support","email":f"support@{DOMAIN}"},
    {"@type":"ContactPoint","contactType":"security","email":f"security@{DOMAIN}"}
  ]
}
json_ld_tag = '<script type="application/ld+json">'+json.dumps(json_ld, ensure_ascii=False)+'</script>'

mailto_re = re.compile(r'(?i)mailto:([A-Z0-9._%+\-]+)@([A-Z0-9.\-]+\.[A-Z]{2,})(\?[^"\'\s>]*)?')

def rewrite_mailto(match):
    local, dom, query = match.group(1), match.group(2), match.group(3) or ""
    new_local = local_map.get(local.lower())
    if not new_local:
        # leave unknown aliases alone, but if domain isn't ethicops, keep original
        return match.group(0)
    return f"mailto:{new_local}@{DOMAIN}{query}"

def insert_footer(html):
    # Remove our old auto block or previous contacts block if present
    html = re.sub(r'<div id="auto-contacts".*?</div>\s*', '', html, flags=re.I|re.S)
    html = re.sub(r'<div id="contacts-ethicops".*?</div>\s*', '', html, flags=re.I|re.S)
    # Insert before </footer> or </body>, else append
    if re.search(r"</footer>", html, flags=re.I):
        return re.sub(r"</footer>", footer_block + "\n</footer>", html, count=1, flags=re.I)
    if re.search(r"</body>", html, flags=re.I):
        return re.sub(r"</body>", footer_block + "\n</body>", html, count=1, flags=re.I)
    return html + "\n" + footer_block + "\n"

def insert_json_ld(html):
    if re.search(r'Application/ld\+json|application/ld\+json', html) and NAME in html:
        return html  # already present for EthicOps
    # Insert before </head> if possible
    if re.search(r"</head>", html, flags=re.I):
        return re.sub(r"</head>", json_ld_tag + "\n</head>", html, count=1, flags=re.I)
    return html  # no head tag; skip quietly

updated = []
for p in html_files:
    t = p.read_text(encoding="utf-8", errors="ignore")
    # 1) Normalize any mailto: links for known roles to @ethicops.org
    t2 = mailto_re.sub(rewrite_mailto, t)
    # 2) Insert footer block (EthicOps only)
    t3 = insert_footer(t2)
    # 3) JSON-LD in <head>
    t4 = insert_json_ld(t3)
    if t4 != t:
        p.write_text(t4, encoding="utf-8")
        updated.append(p.name)

print("Updated files:")
for n in updated: print(" -", n)
