import csv 
import time
import re
import os
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


class FlipkartScrapper:
    
    def __init__(self, output_dir="data"):
        """Initialize the FlipkartScrapper with output directory."""
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # Get the product review using product url and and how many review we want as default 
    def get_top_reviews(self, product_url, count=2):
        """Fetch top reviews for a given product URL."""
        pass

    # Scrap the flipkart product data
    def scrape_flipkart_products(self, query, max_products=1, review_count=2):
        """Scrape Flipkart for products based on a search query."""
        pass

    # Next we will save in csv file 
    def save_to_csv(self, data, filename="product_reviews.csv"):
        """Save scraped data to a CSV file."""
        pass