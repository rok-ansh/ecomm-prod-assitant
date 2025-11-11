import csv
import time
import re
import os
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

class FlipkartScraper:
    def __init__(self, output_dir="data"):
        """Create a scraper instance.

        Args:
            output_dir: directory where CSV files will be written. Created if missing.
        """
        self.output_dir = output_dir
        # ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def get_top_reviews(self,product_url,count=2):
        """Get the top reviews for a product.

        This opens the product URL in a headful Chrome instance and scrolls
        the page to allow reviews to load. It then parses the rendered HTML
        with BeautifulSoup and extracts textual review blocks.

        Args:
            product_url: full URL of the product page on Flipkart
            count: maximum number of top reviews to return

        Returns:
            A string with reviews joined by ' || ', or 'No reviews found'.
        """
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = uc.Chrome(options=options,use_subprocess=True)

        # Validate URL early
        if not product_url.startswith("http"):
            driver.quit()
            return "No reviews found"

        try:
            # Open product page and wait for initial content
            driver.get(product_url)
            time.sleep(4)

            # Try to close any initial popup (the selector may not always match)
            try:
                driver.find_element(By.XPATH, "//button[contains(text(), '✕')]").click()
                time.sleep(1)
            except Exception as e:
                # Popup not present or different selector
                print(f"Error occurred while closing popup: {e}")

            # Scroll down to load lazy content (reviews often load after scrolling)
            for _ in range(4):
                ActionChains(driver).send_keys(Keys.END).perform()
                time.sleep(1.5)

            # Parse rendered HTML and select common review container classes
            soup = BeautifulSoup(driver.page_source, "html.parser")
            review_blocks = soup.select("div._27M-vq, div.col.EPCmJX, div._6K-7Co")
            seen = set()
            reviews = []

            # Deduplicate and collect up to `count` reviews
            for block in review_blocks:
                text = block.get_text(separator=" ", strip=True)
                if text and text not in seen:
                    reviews.append(text)
                    seen.add(text)
                if len(reviews) >= count:
                    break
        except Exception:
            reviews = []

        driver.quit()
        return " || ".join(reviews) if reviews else "No reviews found"
    
    def scrape_flipkart_products(self, query, max_products=1, review_count=2):
        """Scrape Flipkart products based on a search query.

        This performs a search on Flipkart and extracts metadata from the
        search results page. For each product link it optionally visits the
        product page to collect top reviews (via `get_top_reviews`).

        Args:
            query: search string
            max_products: maximum number of products to return
            review_count: number of top reviews to fetch per product

        Returns:
            A list of lists: [product_id, title, rating, total_reviews, price, top_reviews]
        """
        options = uc.ChromeOptions()
        driver = uc.Chrome(options=options,use_subprocess=True)
        search_url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        driver.get(search_url)
        time.sleep(4)

        # Try to dismiss initial popup on the search page
        try:
            driver.find_element(By.XPATH, "//button[contains(text(), '✕')]").click()
        except Exception as e:
            # It's fine if the popup is not present
            print(f"Error occurred while closing popup: {e}")

        time.sleep(2)
        products = []

        # Select result items; Flipkart uses `data-id` on product tiles
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-id]")[:max_products]
        for item in items:
            try:
                # Extract visible fields from the search result tile
                title = item.find_element(By.CSS_SELECTOR, "div.KzDlHZ").text.strip()
                price = item.find_element(By.CSS_SELECTOR, "div.Nx9bqj").text.strip()
                rating = item.find_element(By.CSS_SELECTOR, "div.XQDdHH").text.strip()
                reviews_text = item.find_element(By.CSS_SELECTOR, "span.Wphh3N").text.strip()
                match = re.search(r"\d+(,\d+)?(?=\s+Reviews)", reviews_text)
                total_reviews = match.group(0) if match else "N/A"

                link_el = item.find_element(By.CSS_SELECTOR, "a[href*='/p/']")
                href = link_el.get_attribute("href")
                product_link = href if href.startswith("http") else "https://www.flipkart.com" + href
                match = re.findall(r"/p/(itm[0-9A-Za-z]+)", href)
                product_id = match[0] if match else "N/A"
            except Exception as e:
                # If a single tile fails to parse, skip it and proceed
                print(f"Error occurred while processing item: {e}")
                continue

            # Optionally visit the product page to grab top reviews
            top_reviews = self.get_top_reviews(product_link, count=review_count) if "flipkart.com" in product_link else "Invalid product URL"
            products.append([product_id, title, rating, total_reviews, price, top_reviews])

        # Close the browser and return collected products
        driver.quit()
        return products
    
    def save_to_csv(self, data, filename="product_reviews.csv"):
        """Save the scraped product reviews to a CSV file."""
        # Determine destination path. Support absolute paths and subfolders.
        if os.path.isabs(filename):
            path = filename
        elif os.path.dirname(filename):  # filename includes subfolder like 'data/product_reviews.csv'
            path = filename
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            # plain filename like 'output.csv'
            path = os.path.join(self.output_dir, filename)

        # Write CSV with a header row matching the scraper's data structure
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["product_id", "product_title", "rating", "total_reviews", "price", "top_reviews"])
            writer.writerows(data)
        