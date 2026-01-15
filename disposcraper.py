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
    # Using the outer card selector identified from your HTML
    cards = await page.query_selector_all('[data-testid="product-card-div"]')
    if not cards:
        # Fallback to the generic outer card if the specific div isn't found
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
            if brand and not name.lower().startswith(brand.lower()):
                full_name = f"{brand} - {name}"
            else:
                full_name = name

            # 4. Get Price (Robust Logic)
            price = "$0.00"
            price_found = False
            
            # Step A: Check elements with price-related test-ids
            price_elements = await card.query_selector_all('[data-testid*="price"], [data-testid*="discount"]')
            
            for el in price_elements:
                # Check 1: Content of the element
                text = (await el.inner_text()).strip()
                # Check 2: The test-id attribute itself (handles variant-price-45)
                testid = await el.get_attribute('data-testid') or ""
                
                # Combine both to look for a price match
                combined_source = f"{text} {testid}"
                
                # Look for patterns like $45.00 or $45
                match = re.search(r"\$(\d+\.?\d*)", combined_source)
                if not match:
                    # Look for the specific numeric suffix in the test-id if no $ is present
                    # e.g., variant-price-45 -> matches 45
                    match = re.search(r"price-(\d+\.?\d*)", testid)
                
                if match:
                    val = match.group(1)
                    # Standardize to $XX.XX
                    if "." in val:
                        parts = val.split(".")
                        price = f"${parts[0]}.{parts[1][:2].ljust(2, '0')}"
                    else:
                        price = f"${val}.00"
                    
                    if price != "$0.00":
                        price_found = True
                        break
            
            # Step B: Broad Fallback - check entire card text for first $ sign
            if not price_found:
                full_card_text = await card.inner_text()
                price_match = re.search(r"\$\d+\.?\d*", full_card_text)
                if price_match:
                    price = price_match.group(0)
                    if "." not in price: price += ".00"

            # 5. Get Metadata (THC)
            card_text = await card.inner_text()
            # Match THC, THCa, or CBD percentages
            thc_match = re.search(r"(THCa?|CBD)\s*(\d+\.?\d*%)", card_text, re.IGNORECASE)
            thc = thc_match.group(2) if thc_match else "N/A"

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
        except Exception as e:
            # print(f"Error parsing card: {e}")
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
                await handle_age_gate(page)
                
                # Check for any of the card identifiers
                await page.wait_for_function(
                    "document.querySelector('[data-testid=\"product-card-div\"]') || document.querySelector('[data-testid=\"card-outer\"]')",
                    timeout=20000
                )
                
                await scroll_to_load_all(page)
                category_products = await scrape_page_products(page, category['name'])
                all_products.extend(category_products)
                print(f"[+] Added {len(category_products)} items from {category['name']}")
                
            except Exception as e:
                print(f"[!] Error scraping {category['name']}: {e}")

        # Final cleanup and save
        unique_products = list({p['name']: p for p in all_products}.values())
        with open(OUTPUT_FILE, "w") as f:
            json.dump(unique_products, f, indent=4)
        
        print(f"\n[!!!] Final Success: {len(unique_products)} total unique products saved to {OUTPUT_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())