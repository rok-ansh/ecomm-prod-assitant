import os
import pandas as pd
from dotenv import load_dotenv
from typing import List
from langchain_core.documents import Document
from langchain_astradb import AstraDBVectorStore
from prod_assistant.utils.model_loader import ModelLoader
from prod_assistant.utils.config_loader import load_config


class DataIngestion:
    """Class to handle data ingestion, processing, and storage in AstraDB Vector Store."""
    def __init__(self):
        """Initialize DataIngestion with configuration and environment variables."""
        # Initialize model loader and load environment variables
        self.model_loader = ModelLoader()
        # Load environment variables from .env file
        self._load_env_variables()
        # csv path from config
        self.csv_path = self._get_csv_path()
        # Load product data from CSV
        self.product_data = self._load_csv()
        # Load configuration
        self.config = load_config()


    def _load_env_variables(self):
        """Load environment variables from a .env file."""
        # Load environment variables from .env file
        load_dotenv()

        # Define required environment variables
        required_vars = [
            "OPENAI_API_KEY",
            "ASTRA_DB_API_ENDPOINT",
            "ASTRA_DB_APPLICATION_TOKEN",
            "ASTRA_DB_KEYSPACE",
        ]

        # Check for any missing required environment variables
        missing_vars = [var for var in required_vars if os.getenv(var) is None]
        # Raise an error if any required environment variables are missing
        if missing_vars:
            raise EnvironmentError(f"Missing required environmnet variables : {missing_vars}")
        
        # Store environment variables as instance attributes
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        # AstraDB related env variables
        self.db_api_endpoint = os.getenv("ASTRA_DB_API_ENDPOINT") # e.g., "https://your-instance.db.astra.datastax.com"
        self.db_application_token = os.getenv("ASTRA_DB_APPLICATION_TOKEN") # e.g., "your-application-token"
        self.db_keyspace = os.getenv("ASTRA_DB_KEYSPACE") # e.g., "your_keyspace"
        


    def _get_csv_path(self):
        """Get the CSV file path from configuration."""

        # Default path
        current_dir = os.getcwd()
        # Construct CSV path
        csv_path = os.path.join(current_dir, 'data', 'product_reviews.csv')

        # Checking if csv file is not available at path raise file not found error
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found at the path: {csv_path}")
        
        return csv_path
    
    def _load_csv(self):
        """Load product data from CSV file."""
        df = pd.read_csv(self.csv_path)
        # Validate required columns
        expected_columns = {'product_name', 'product_title', 'rating', 'total_reviews', 'price', 'top_reviews'}

        # Check if all expected columns are present
        if not expected_columns.issubset(set(df.columns)):
            raise ValueError(f"CSV file is missing required columns. Expected columns: {expected_columns}")
        
        return df

    def transform_data(self):
        """Transform product data into list of Langchain Document objects."""
        product_list = []

        # Iterating and checking all the row values and appending it to product_list 
        for _, row in self.product_data.iterrows():
            product_entry = {
                "product_id" : row["product_id"], 
                "product_title" : row["product_title"],
                "rating" : row["rating"],
                "total_reviews" : row["total_reviews"],
                "price" : row["price"],
                "top_reviews" : row["top_reviews"]
            }
            product_list.append(product_entry)

        documents = []
        for entry in product_list:
            metadata = {
                "product_id" : entry["product_id"], 
                "product_title" : entry["product_title"],
                "rating" : entry["rating"],
                "total_reviews" : entry["total_reviews"],
                "price" : entry["price"],
            }
            doc = Document(page_content=entry['top_reviews'], metadata=metadata)
            documents.append(doc)

        print(f"Transformed {len(documents)} documents. ")
        return documents

        
    def store_in_vetcor_db(self, documents : List[Document]):
        """Store transformed documents in AstraDB Vector Store."""
        collection_name = self.config["astra-db"]["collection_name"]
        vstore = AstraDBVectorStore(
            embedding = self.model_loader.load_embeddings(),
            collection_name = collection_name,
            api_endpoint = self.db_api_endpoint,
            token = self.db_application_token,
            namespace = self.db_keyspace
        )

        inserted_ids = vstore.add_documents(documents)
        print(f"Successfully inserted {len(inserted_ids)} documents into Astra DB. ")
        return vstore, inserted_ids


    def run_pipeline(self):
        """Run the complete data ingestion pipeline. tranform data and store into vector DB. """
        documents = self.transform_data()
        vstore, _ = self.store_in_vetcor_db()

        # Optionally do a quick check 
        query = "can you tell me the low budget iphone"
        results = vstore.similarity_search(query)

        print("f\nSample search result for the query : {query}")
        for res in results:
            print(f"Content : {res.page_content}\nMetadata : {res.metadata}\n")

    
# Run if this file is executed directy
if __name__ == "__main__":
    ingestion = DataIngestion()
    ingestion.run_pipeline()

        