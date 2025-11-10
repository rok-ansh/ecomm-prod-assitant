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
        pass

    def _load_env_variables(self):
        """Load environment variables from a .env file."""
        pass

    def _get_csv_path(self):
        """Get the CSV file path from configuration."""
        pass

    def transform_data(self):
        """Transform raw CSV data into a list of Document objects."""
        pass

    def store_in_vetcor_db(self):
        """Store transformed documents in AstraDB Vector Store."""
        pass

    def run_pipeline(self):
        """Run the complete data ingestion pipeline."""
        pass