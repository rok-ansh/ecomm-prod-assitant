# This file is without the Langgraph (Generation Workflow) not going to use it just for understanding the classic RAG flow
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from prompt_library.prompts import PROMPT_REGISTRY, PromptType
from retriever.retrieval import Retriever
from utils.model_loader import ModelLoader

retriever_obj = Retriever()
model_loader = ModelLoader()

#
def format_docs(docs)-> str:
    """Format retrieved documents into a structured text block fro the prompt."""
    if not docs:
        return "No relevant documents found."
    
    formatted_chunks = []
    for doc in docs:
        # Extract metadata
        meta = doc.metadata or {}
        # Extract relevant information from the metadata
        formatted = (
            f"Title : {meta.get('product_title', 'N/A')}\n"
            f"Price : {meta.get('price', 'N/A')}\n"
            f"Rating : {meta.get('rating', 'N/A')}\n"
            f"Reviews :\n{doc.page_content.strip()}"
        )
        # Append the formatted chunk
        formatted_chunks.append(formatted)
    # Join the formatted chunks with a separator
    return "\n\n--\n\n".join(formatted_chunks)


def build_chain(query):
    """Build the RAG pipeline chain with retriever, prompt, LLM and parser"""
    retriever = retriever_obj.load_retriever() # load the retriever get the config of models and environment variables
    retrieved_docs = retriever.invoke(query) # retrieve docs
    retrieved_context = [format_docs(retrieved_docs)]

    llm = model_loader.load_llm() # load the LLM model
    prompt = ChatPromptTemplate.from_template(
        PROMPT_REGISTRY[PromptType.PRODUCT_BOT].template 
    )

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        |prompt
        |llm
        |StrOutputParser
    )
    return chain, retrieved_context


def invoke_chain(query:str, debug:bool=False)->str:
    """Run the chain with a user query"""
    chain, retrieved_context = build_chain()

    if debug:
        # For debugging : show docs retrieved before passing to LLM
        docs = retriever_obj.load_retriever().invoke(query) # retrieve docs
        print("\nRetrieved Documents:\n")
        print(format_docs(docs))
        print("\n---\n")

    response = chain.invoke(query)

    return retrieved_context,response

if __name__=="__main__":
    try:
        answer = invoke_chain("can you tell me the price of iphone 15")
        print("\n Assistant Answer:\n", answer)
    except Exception as e:
        import traceback
        print("Exeception occurred:", str(e))
        traceback.print_exc()
        
