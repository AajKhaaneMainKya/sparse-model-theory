import json
from playwright.sync_api import sync_playwright

URL = "https://aksharthewriter.vercel.app/offline"
OUT = "/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/scratch_akshar_shots"
import os
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1000)

    page.screenshot(path=f"{OUT}/akshar-live-full.png", full_page=True)
    page.screenshot(path=f"{OUT}/akshar-live-viewport.png", full_page=False)

    # Body / page-level background + font
    body_style = page.evaluate("""
        () => {
            const b = getComputedStyle(document.body);
            const html = getComputedStyle(document.documentElement);
            return {
                bodyBg: b.backgroundColor,
                bodyColor: b.color,
                bodyFont: b.fontFamily,
                htmlBg: html.backgroundColor,
            };
        }
    """)
    print("BODY/HTML STYLE:", json.dumps(body_style, indent=2))

    # Find any element containing the Devanagari wordmark "अक्षर"
    wordmark_info = page.evaluate("""
        () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const results = [];
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.includes('अक्षर')) {
                    const el = node.parentElement;
                    const style = getComputedStyle(el);
                    results.push({
                        tag: el.tagName,
                        className: el.className,
                        text: node.textContent.trim(),
                        color: style.color,
                        backgroundColor: style.backgroundColor,
                        fontFamily: style.fontFamily,
                        fontSize: style.fontSize,
                        fontWeight: style.fontWeight,
                        outerHTML: el.outerHTML.slice(0, 300),
                    });
                }
            }
            return results;
        }
    """)
    print("DEVANAGARI WORDMARK MATCHES:", json.dumps(wordmark_info, indent=2, ensure_ascii=False))

    # Find "Akshar" (Latin) text elements too, e.g. logo/brand text
    latin_info = page.evaluate("""
        () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const results = [];
            let node;
            while (node = walker.nextNode()) {
                if (/Akshar/i.test(node.textContent) && node.textContent.trim().length < 60) {
                    const el = node.parentElement;
                    const style = getComputedStyle(el);
                    results.push({
                        tag: el.tagName,
                        className: el.className,
                        text: node.textContent.trim(),
                        color: style.color,
                        backgroundColor: style.backgroundColor,
                        fontFamily: style.fontFamily,
                        fontSize: style.fontSize,
                        fontWeight: style.fontWeight,
                    });
                }
            }
            return results;
        }
    """)
    print("LATIN 'AKSHAR' TEXT MATCHES:", json.dumps(latin_info, indent=2, ensure_ascii=False))

    # Grab prominent accent-colored elements (buttons, links, headers) for a color palette sample
    palette_sample = page.evaluate("""
        () => {
            const selectors = ['h1', 'h2', 'a', 'button', '[class*="accent"]', '[class*="primary"]', '[class*="brand"]'];
            const seen = new Set();
            const results = [];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const style = getComputedStyle(el);
                    const key = style.color + '|' + style.backgroundColor;
                    if (!seen.has(key) && results.length < 25) {
                        seen.add(key);
                        results.push({
                            selector: sel,
                            tag: el.tagName,
                            className: (el.className || '').toString().slice(0, 80),
                            text: (el.textContent || '').trim().slice(0, 40),
                            color: style.color,
                            backgroundColor: style.backgroundColor,
                            borderColor: style.borderColor,
                        });
                    }
                });
            }
            return results;
        }
    """)
    print("PALETTE SAMPLE:", json.dumps(palette_sample, indent=2, ensure_ascii=False))

    # Page title / meta for confirmation this is really Akshar
    print("PAGE TITLE:", page.title())

    browser.close()
