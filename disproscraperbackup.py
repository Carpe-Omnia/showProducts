import asyncio
import json
import re
from playwright.async_api import async_playwright

# Configuration
TARGET_URL = "https://gsngdispensary.com/shop/categories/flower"
OUTPUT_FILE = "products.json"

async def handle_age_gate(page):
    """Detects and clicks the specific 'Yes' button on the age gate."""
    print("[*] Checking for age verification gate...")
    
    try:
        # Targeting the exact HTML button structure you provided
        yes_button = page.locator('button.age-gate__submit--yes[data-submit="yes"]')
        
        # Wait up to 5 seconds for it to appear
        if await yes_button.is_visible(timeout=5000):
            print("[!] Age gate detected. Clicking 'Yes'...")
            await yes_button.click()
            # Wait for the overlay to vanish and content to start loading
            await page.wait_for_timeout(2000)
            return True
        else:
            # Fallback for different site versions
            fallback = page.get_by_role("button", name=re.compile("Yes", re.IGNORECASE))
            if await fallback.is_visible(timeout=1000):
                print("[!] Using fallback 'Yes' button click.")
                await fallback.click()
                await page.wait_for_timeout(2000)
                return True

    except Exception as e:
        print(f"[*] Note: Age gate check finished (None found or error: {e})")
            
    print("[*] No obvious age gate detected (or already cleared).")
    return False

async def scroll_to_load_all(page):
    """Simulates scrolling to trigger infinite loading until no more content appears."""
    print("[*] Starting infinite scroll to load all products...")
    last_height = await page.evaluate("document.body.scrollHeight")
    
    while True:
        # Scroll to the bottom of the page
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # Wait for potential lazy loading / network requests
        await page.wait_for_timeout(2000)
        
        # Check new height
        new_height = await page.evaluate("document.body.scrollHeight")
        
        # Count current cards to log progress
        current_count = await page.locator('[data-testid="card-outer"]').count()
        print(f"[*] Current scroll height: {new_height}px | Products visible: {current_count}")
        
        if new_height == last_height:
            # Try one more small scroll/wait just in case of slow network
            await page.mouse.wheel(0, -200) # Scroll up slightly
            await page.wait_for_timeout(500)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            
            final_height = await page.evaluate("document.body.scrollHeight")
            if final_height == new_height:
                print("[+] Reached the bottom of the list.")
                break
        
        last_height = new_height

async def scrape_dispensary():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"[*] Navigating to {TARGET_URL}...")
        try:
            # Go to site
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Handle the age gate
            await handle_age_gate(page)

            # 2. Wait for initial cards to appear
            await page.wait_for_selector('[data-testid="card-outer"]', timeout=30000)
            
            # 3. Scroll until all products are loaded
            await scroll_to_load_all(page)

            # 4. Extract details
            products = []
            cards = await page.query_selector_all('[data-testid="card-outer"]')
            print(f"[*] Total cards found after scrolling: {len(cards)}. Parsing...")

            for card in cards:
                try:
                    # Brand Name
                    brand_el = await card.query_selector('[data-testid*="product-card-brand-name"]')
                    brand = await brand_el.inner_text() if brand_el else ""

                    # Product Name
                    name_el = await card.query_selector('[data-testid*="product-name"]')
                    name = await name_el.inner_text() if name_el else "Unknown Strain"

                    # Price
                    price_el = await card.query_selector('[data-testid*="variant-discount"]')
                    if not price_el:
                        price_el = await card.query_selector('[data-testid*="variant-price-original"]')
                    
                    price_text = await price_el.inner_text() if price_el else "$0.00"
                    price_match = re.search(r"\$\d+\.\d{2}", price_text)
                    price = price_match.group(0) if price_match else price_text

                    # THC and Meta data
                    card_text = await card.inner_text()
                    thc_match = re.search(r"THCa?\s*(\d+\.?\d*%)", card_text)
                    thc = thc_match.group(1) if thc_match else "N/A"

                    # Category
                    category = "FLOWER"
                    if "indica" in card_text.lower(): category = "INDICA"
                    elif "sativa" in card_text.lower(): category = "SATIVA"
                    elif "hybrid" in card_text.lower(): category = "HYBRID"

                    # Image
                    img_el = await card.query_selector('img')
                    img_url = await img_el.get_attribute('src') if img_el else ""

                    if name != "Unknown Strain":
                        full_name = f"{brand} - {name}" if brand else name
                        products.append({
                            "name": full_name.strip(),
                            "price": price,
                            "meta": f"THC: {thc}",
                            "category": category,
                            "image": img_url
                        })
                except Exception:
                    continue

            # Final cleanup and save
            unique_products = list({p['name']: p for p in products}.values())
            with open(OUTPUT_FILE, "w") as f:
                json.dump(unique_products, f, indent=4)
            
            print(f"[+] Success! Scraped {len(unique_products)} total products.")

        except Exception as e:
            print(f"[!] Error during scrape: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_dispensary())