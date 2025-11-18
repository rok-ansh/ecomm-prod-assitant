import sys
from pathlib import Path
import os 
from langchain_astradb import AstraDBVectorStore
from typing import List
from langchain_core.documents import Document
from utils.config_loader import load_config 
from utils.model_loader import ModelLoader
from dotenv import load_dotenv


# Add the project root to the Python path for direct script execution
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

class Retriever :
    def __init__(self):
        """_summary_
        """
        self.model_loader = ModelLoader()
        self.config = load_config()
        self._load_env_varibales()
        self.vstore = None
        self.retriever = None

    def _load_env_varibales(self):
        """load the environment variables
        """
        load_dotenv()
        required_vars = ["OPENAI_API_KEY", "ASTRA_DB_API_ENDPOINT", "ASTRA_DB_APPLICATION_TOKEN", "ASTRA_DB_KEYSPACE"] 
        missing_vars = [var for var in required_vars if os.getenv(var) is None]

        if missing_vars:
            raise EnvironmentError(f"Missing required environmnet variables : {missing_vars}")
        
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.db_api_endpoint = os.getenv("ASTRA_DB_API_ENDPOINT") # e.g., "https://your-instance.db.astra.datastax.com"
        self.db_application_token = os.getenv("ASTRA_DB_APPLICATION_TOKEN") # e.g., "your-application-token"
        self.db_keyspace = os.getenv("ASTRA_DB_KEYSPACE") # e.g., "your_keyspace"

    def load_retriever(self):
        """load the retriever
        """
        # Similar to store_in_vetcor_db function only difference is we are retrieving not storing
        # vstore is intilized as None in __init__ function so it's not none then create it otherwise load the vector store
        if not self.vstore:
            self.vstore = AstraDBVectorStore(
                embedding = self.model_loader.load_embeddings(),
                collection_name = self.config["astra_db"]["collection_name"],
                api_endpoint = self.db_api_endpoint,
                token = self.db_application_token,
                namespace = self.db_keyspace
            )
        
        # retriever is intilized as None in __init__ function so it's not none then create it otherwise load the retriever
        if not self.retriever:
            top_k = self.config["retriever"]["top_k"] if self.config["retriever"]["top_k"] else 3 # default to 3 if not specified in config
            retriever = self.vstore.as_retriever(search_kwargs={"k": top_k}) # top_k is the number of results to return
            print("Retriever is Loaded successfully")
            return retriever



    def call_retriever(self, query):
        """call the retriever"""
        retriever = self.load_retriever()
        output = retriever.invoke(query)
        return output


if __name__ == "__main__":
    retriever = Retriever()
    query = "can you sugggest good budget laptops"
    results = retriever.call_retriever(query)

    for idx, doc in enumerate(results):
        print(f"Result {idx}: {doc.page_content}\nMetadata: {doc.metadata}\n")
