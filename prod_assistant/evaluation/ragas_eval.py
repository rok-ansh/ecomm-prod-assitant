from utils.model_loader import ModelLoader
from ragas import SingleTurnSample 
from ragas import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import LLMContextPrecisionWithoutReference, ResponseRelevancy
import grpc.experimental.aio as grpc_aio # this is used for async calls
import asyncio

grpc_aio.init_grpc_aio() # initialize grpc aio
model_loader = ModelLoader()

# Now create 2 function for evalution we can make as many metrics as reqiured from document 
def evaluate_context_precision():
    """_summary_
    """
    pass

def evaluate_context_relevancy():
    """_summary_
    """
    pass