import asyncio
import json
import re
import random
from playwright.async_api import async_playwright

# Configuration
CATEGORIES = [
    {"name": "FLOWER", "url": "https://gsngdispensary.com/shop/categories/flower"},
    {"name": "PRE-ROLLS", "url": "https://gsngdispensary.com/shop/categories/pre-rolls"},
    {"name": "VAPORIZERS", "url": "https://gsngdispensary.com/shop/categories/vaporizers"},
    {"name": "EDIBLES", "url": "https://gsngdispensary.com/shop/categories/edibles"},
    {"name": "CONCENTRATES", "url": "https://gsngdispensary.com/shop/categories/concentrates"}
]
OUTPUT_FILE = "products.json"
BASE_URL = "https://gsngdispensary.com"

async def handle_age_gate(page):
    try:
        yes_button = page.locator('button.age-gate__submit--yes[data-submit="yes"]')
        if await yes_button.is_visible(timeout=5000):
            await yes_button.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

async def scroll_to_load_all(page):
    last_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2500)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

async def scrape_page_products(page, category_label):
    products = []
    cards = await page.query_selector_all('[data-testid="product-card-div"]')
    if not cards:
        cards = await page.query_selector_all('[data-testid="card-outer"]')
        
    for card in cards:
        try:
            # 1. Get Product Link (Crucial for QR codes)
            link_el = await card.query_selector('a')
            relative_url = await link_el.get_attribute('href') if link_el else ""
            full_url = f"{BASE_URL}{relative_url}" if relative_url.startswith('/') else relative_url

            # 2. Get Brand & Name
            brand_el = await card.query_selector('[data-testid*="product-card-brand-name"]')
            brand = (await brand_el.inner_text()).strip() if brand_el else ""
            name_el = await card.query_selector('[data-testid*="product-name"]')
            name = (await name_el.inner_text()).strip() if name_el else "Unknown"
            full_name = f"{brand} - {name}" if brand and not name.lower().startswith(brand.lower()) else name

            # 3. Get Price
            found_prices = []
            price_elements = await card.query_selector_all('[data-testid*="price"], [data-testid*="discount"]')
            for el in price_elements:
                text = (await el.inner_text()).strip()
                matches = re.findall(r"\$(\d+\.?\d*)", text)
                for val in matches:
                    found_prices.append(float(val))

            price = f"${min(found_prices):,.2f}" if found_prices else "$0.00"

            # 4. Get Metadata
            card_text = await card.inner_text()
            meta_match = re.search(r"((?:THCa?|CBD|Total THC)\s*\d+\.?\d*%|\d+\s*mg)", card_text, re.IGNORECASE)
            meta_val = meta_match.group(0) if meta_match else "N/A"

            # 5. Get Image
            img_el = await card.query_selector('img')
            img_url = await img_el.get_attribute('src') if img_el else ""

            if name != "Unknown":
                products.append({
                    "name": full_name,
                    "price": price,
                    "meta": meta_val,
                    "category": category_label,
                    "image": img_url,
                    "url": full_url # Saved for the QR code
                })
        except Exception:
            continue
    return products

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        all_products = []

        for category in CATEGORIES:
            try:
                await page.goto(category['url'], wait_until="domcontentloaded", timeout=60000)
                await handle_age_gate(page)
                await page.wait_for_timeout(3000)
                await scroll_to_load_all(page)
                category_products = await scrape_page_products(page, category['name'])
                all_products.extend(category_products)
            except Exception as e:
                print(f"Error scraping {category['name']}: {e}")

        unique_products = list({p['name']: p for p in all_products}.values())
        random.shuffle(unique_products)
        
        with open(OUTPUT_FILE, "w") as f:
            json.dump(unique_products, f, indent=4)
        
        print(f"Successfully scraped {len(unique_products)} products with URLs.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())