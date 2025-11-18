import os 
from langchain_astradb import AstraDBVectorStore
from typing import List
from langchain_core.documents import Document
from utils.config_loader import load_config 
from utils.model_loader import ModelLoader
from dotenv import load_dotenv


class Retriever :
    def __init__(self):
        """_summary_
        """
        pass

    def _load_env_varibales(self):
        """load the environment variables
        """
        pass    

    def load_retriever(self):
        """load the retriever
        """
        pass

    def call_retriever(self):
        """call the retriever"""
        pass


if __name__ == "__main__":
    retriever = Retriever()
    user_query = "can you sugggest good budget laptops"
    results = retriever.call_retriever(user_query)

    for idx, doc in enumerate(results):
        print(f"Result {idx}: {doc.page_content}\nMetadata: {doc.metadata}\n")
