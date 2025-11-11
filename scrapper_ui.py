
import streamlit as st
from prod_assistant.etl.data_scrapper import FlipkartScraper
from prod_assistant.etl.data_ingestion import DataIngestion
import os

# Initialize scraper
flipkart_scraper = FlipkartScraper()
# Define output CSV path
output_path = "data/product_reviews.csv"
# Streamlit UI
st.title("📦 Product Review Scraper")

# Initialize session state for product inputs
if "product_inputs" not in st.session_state:
    # Start with one empty input field
    st.session_state.product_inputs = [""]

# Function to add a new product input field
def add_product_input():
    # Append an empty string to the list of product inputs
    st.session_state.product_inputs.append("")

# UI Elements
st.subheader("📝 Optional Product Description")
# Text area for additional product description
product_description = st.text_area("Enter product description (used as an extra search keyword):")

# Text inputs for product names
st.subheader("🛒 Product Names")
# Dynamically create text input fields for each product
updated_inputs = []
# Iterate over existing product inputs
for i, val in enumerate(st.session_state.product_inputs):   
    # Create a text input for each product
    input_val = st.text_input(f"Product {i+1}", value=val, key=f"product_{i}")
    # Collect updated inputs
    updated_inputs.append(input_val)
# Update session state with new inputs
st.session_state.product_inputs = updated_inputs

# Button to add another product input field
st.button("➕ Add Another Product", on_click=add_product_input)

# Input for number of products and reviews
max_products = st.number_input("How many products per search?", min_value=1, max_value=10, value=1)
review_count = st.number_input("How many reviews per product?", min_value=1, max_value=10, value=2)

# Button to start scraping
if st.button("🚀 Start Scraping"):
    # Gather all product inputs, including the optional description
    product_inputs = [p.strip() for p in st.session_state.product_inputs if p.strip()]
    # Add product description as an additional search keyword if provided
    if product_description.strip():
        # Append description to each product input
        product_inputs.append(product_description.strip())
    # Validate at least one product input
    if not product_inputs:
        st.warning("⚠️ Please enter at least one product name or a product description.")
    # Start scraping process
    else:
        final_data = []
        # Iterate over each product input and scrape data
        for query in product_inputs:
            # Display current search query
            st.write(f"🔍 Searching for: {query}")
            # Scrape products and reviews
            results = flipkart_scraper.scrape_flipkart_products(query, max_products=max_products, review_count=review_count)
            final_data.extend(results)

        unique_products = {}
        # Remove duplicates based on product name (index 1)
        for row in final_data:
            # Keep the first occurrence of each unique product
            if row[1] not in unique_products:
                # Store the product using its name as the key
                unique_products[row[1]] = row

        # Convert back to list
        final_data = list(unique_products.values())
        # Store the final data in session state
        st.session_state["scraped_data"] = final_data  # store in session
        # Save data to CSV
        flipkart_scraper.save_to_csv(final_data, output_path)
        st.success("✅ Data saved to `data/product_reviews.csv`")
        # Provide download link for the CSV
        st.download_button("📥 Download CSV", data=open(output_path, "rb"), file_name="product_reviews.csv")

# This stays OUTSIDE "if st.button('Start Scraping')"
# Button to start ingestion to Vector DB
if "scraped_data" in st.session_state and st.button("🧠 Store in Vector DB (AstraDB)"):
    # Initialize and run ingestion pipeline
    with st.spinner("📡 Initializing ingestion pipeline..."):
        try:
            # Initialize ingestion
            ingestion = DataIngestion()
            # Run the ingestion pipeline
            st.info("🚀 Running ingestion pipeline...")
            # Execute the pipeline
            ingestion.run_pipeline()
            st.success("✅ Data successfully ingested to AstraDB!")
        # Handle exceptions during ingestion
        except Exception as e:
            st.error("❌ Ingestion failed!")
            st.exception(e)


# ------------------------------------------------------------------
# Developer summary — end-to-end flow and files/functions used
# ------------------------------------------------------------------
# Flow (user -> scraping -> CSV -> ingestion -> vector DB):
# 1) UI: `scrapper_ui.py` (this file)
#    - Collects product names and optional description from the user.
#    - Buttons:
#       * "Start Scraping" -> triggers scraping via FlipkartScraper.
#       * "Store in Vector DB (AstraDB)" -> runs the ingestion pipeline.
#    - Saves scraped rows to `data/product_reviews.csv` and stores them in
#      `st.session_state['scraped_data']` for the ingestion step.
#
# 2) Scraper: `prod_assistant/etl/data_scrapper.py`
#    - Class: `FlipkartScraper`
#      * `scrape_flipkart_products(query, max_products, review_count)`
#          - Uses undetected_chromedriver to open Flipkart search results.
#          - Extracts product tiles (product_id, product_title, rating, total_reviews, price).
#          - Calls `get_top_reviews(product_url, count)` to visit product pages and
#            collect top reviews (scroll + BeautifulSoup parsing).
#      * `save_to_csv(data, filename)` writes CSV with header: 
#          ["product_id","product_title","rating","total_reviews","price","top_reviews"].
#
# 3) Ingestion: `prod_assistant/etl/data_ingestion.py`
#    - Class: `DataIngestion`
#      * On initialization: loads `.env` vars and YAML config via
#        `prod_assistant/utils/config_loader.py` -> `load_config()`.
#      * `_get_csv_path()` / `_load_csv()` read `data/product_reviews.csv`.
#      * `transform_data()` converts CSV rows into `langchain_core.documents.Document`
#        objects (content = reviews, metadata = product fields).
#      * `store_in_vetcor_db(documents)` uses `langchain_astradb.AstraDBVectorStore`
#        and the embeddings loader to add documents to AstraDB.
#
# 4) Models & Embeddings: `prod_assistant/utils/model_loader.py`
#    - `ModelLoader.load_embeddings()` reads `config/config.yaml` embedding settings
#      and returns an embeddings object (OpenAI or Google) based on `provider`.
#    - `ModelLoader.load_llm()` returns an LLM client (OpenAI, Google, or Groq)
#      based on the `llm` block in the config.
#
# Key files to inspect when debugging:
#  - `scrapper_ui.py`             <- Streamlit UI and controls
#  - `prod_assistant/etl/data_scrapper.py` <- scraping & CSV writer
#  - `prod_assistant/etl/data_ingestion.py` <- transform & vector store
#  - `prod_assistant/utils/model_loader.py` <- embeddings & LLM loader
#  - `prod_assistant/config/config.yaml`    <- embedding/LLM/Astra settings
#  - `.env` (or environment) -> must contain keys like OPENAI_API_KEY, ASTRA_DB_*
#
# Tips:
#  - Run Streamlit from the project root so `data/product_reviews.csv` path resolves.
#  - Ensure required env vars are set before clicking "Store in Vector DB".
#  - If scraping fails to find elements, save `driver.page_source` or a screenshot
#    to inspect DOM and adjust selectors.
# ------------------------------------------------------------------