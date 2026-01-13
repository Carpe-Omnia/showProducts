import asyncio
import json
import re
from playwright.async_api import async_playwright

# Configuration
CATEGORIES = [
    {"name": "FLOWER", "url": "https://gsngdispensary.com/shop/categories/flower"},
    {"name": "PRE-ROLLS", "url": "https://gsngdispensary.com/shop/categories/pre-rolls"},
    {"name": "VAPORIZERS", "url": "https://gsngdispensary.com/shop/categories/vaporizers"}
]
OUTPUT_FILE = "products.json"

async def handle_age_gate(page):
    """Detects and clicks the specific 'Yes' button on the age gate."""
    print("[*] Checking for age verification gate...")
    try:
        yes_button = page.locator('button.age-gate__submit--yes[data-submit="yes"]')
        if await yes_button.is_visible(timeout=5000):
            print("[!] Age gate detected. Clicking 'Yes'...")
            await yes_button.click()
            await page.wait_for_timeout(2000)
            return True
    except Exception:
        pass
    return False

async def scroll_to_load_all(page):
    """Simulates scrolling to trigger infinite loading until no more content appears."""
    print("[*] Scrolling to load all items...")
    last_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2500)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

async def scrape_page_products(page, category_label):
    """Extracts product details from the current page state."""
    products = []
    cards = await page.query_selector_all('[data-testid="card-outer"]')
    print(f"[*] Found {len(cards)} cards in {category_label}. Parsing...")

    for card in cards:
        try:
            # 1. Get Brand Name
            brand_el = await card.query_selector('[data-testid*="product-card-brand-name"]')
            brand = (await brand_el.inner_text()).strip() if brand_el else ""

            # 2. Get Product Name
            name_el = await card.query_selector('[data-testid*="product-name"]')
            name = (await name_el.inner_text()).strip() if name_el else "Unknown"

            # 3. Clean Duplicate Brand Names
            # If the name already starts with the brand (e.g., Brand is "Black Buddha" and name is "Black Buddha - Energy..."),
            # just use the name as is. Otherwise, join them nicely.
            if brand and not name.lower().startswith(brand.lower()):
                full_name = f"{brand} - {name}"
            else:
                full_name = name

            # 4. Get Price
            price_el = await card.query_selector('[data-testid*="variant-discount"]') or \
                       await card.query_selector('[data-testid*="variant-price-original"]')
            
            price_text = await price_el.inner_text() if price_el else "$0.00"
            price_match = re.search(r"\$\d+\.\d{2}", price_text)
            price = price_match.group(0) if price_match else price_text

            # 5. Get Metadata (THC)
            card_text = await card.inner_text()
            thc_match = re.search(r"THCa?\s*(\d+\.?\d*%)", card_text)
            thc = thc_match.group(1) if thc_match else "N/A"

            # 6. Get Image
            img_el = await card.query_selector('img')
            img_url = await img_el.get_attribute('src') if img_el else ""

            if name != "Unknown":
                products.append({
                    "name": full_name,
                    "price": price,
                    "meta": f"THC: {thc}",
                    "category": category_label,
                    "image": img_url
                })
        except Exception:
            continue
    return products

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        all_products = []

        for category in CATEGORIES:
            print(f"\n--- Starting: {category['name']} ---")
            try:
                await page.goto(category['url'], wait_until="domcontentloaded", timeout=60000)
                
                # Handle age gate
                await handle_age_gate(page)
                
                # Wait for content and scroll
                await page.wait_for_selector('[data-testid="card-outer"]', timeout=20000)
                await scroll_to_load_all(page)
                
                # Scrape
                category_products = await scrape_page_products(page, category['name'])
                all_products.extend(category_products)
                print(f"[+] Added {len(category_products)} items from {category['name']}")
                
            except Exception as e:
                print(f"[!] Error scraping {category['name']}: {e}")

        # Final cleanup and save (Remove duplicates by name)
        unique_products = list({p['name']: p for p in all_products}.values())
        with open(OUTPUT_FILE, "w") as f:
            json.dump(unique_products, f, indent=4)
        
        print(f"\n[!!!] Final Success: {len(unique_products)} total unique products saved to {OUTPUT_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())