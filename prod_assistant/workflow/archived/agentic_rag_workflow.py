from typing import Annotated, Sequence, TypedDict, Literal
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from prompt_library.prompts import PROMPT_REGISTRY, PromptType
from retriever.retrieval import Retriever
from utils.model_loader import ModelLoader
from langgraph.checkpoint.memory import MemorySaver
import asyncio
# from evaluation.ragas_eval import evaluate_context_precision, evaluate_response_relevancy

class AgenticRAG:
    """Agentic RAG pipeline using langGraph"""

    class AgentState(TypedDict):
        # The current state of the agent
        messages:Annotated[Sequence[BaseMessage], add_messages]
        rewrite_count: int  # Counter to track how many times we've rewritten the query

    def __init__(self):
        self.retriever_obj = Retriever()
        self.model_loader = ModelLoader()
        self.llm = self.model_loader.load_llm()
        # Counter to track rewrites across a single run; easier and more reliable
        # than relying on framework state merging semantics
        self.rewrite_count = 0
        self.checkpointer = MemorySaver()
        self.workflow = self._build_workflow()
        # compile workflow into runnable app
        self.app = self.workflow.compile(checkpointer=self.checkpointer)
        # Debug: expose compiled app and workflow summary for troubleshooting
        try:
            print("[DEBUG] Workflow compiled. Introspecting workflow and app...")
            print("[DEBUG] workflow repr:", repr(self.workflow))
            # print non-private attributes to avoid verbose internals
            public_attrs = [a for a in dir(self.workflow) if not a.startswith("_")]
            print("[DEBUG] workflow public attrs:", public_attrs)
            print("[DEBUG] compiled app repr:", repr(self.app))
        except Exception as _e:
            print("[DEBUG] Error introspecting workflow/app:", _e)

    # -----------Helpers----------
    def _format_docs(self, docs)-> str:
        if not docs:
            return "No relevant documents found."
        
        formatted_chunks = []
        for d in docs:
            meta = d.metadata or {}
            formatted = (
                f"Title : {meta.get('product_title', 'N/A')}\n"
                f"Price : {meta.get('price', 'N/A')}\n"
                f"Rating : {meta.get('rating', 'N/A')}\n"
                f"Reviews :\n{d.page_content.strip()}"
            )
            formatted_chunks.append(formatted)
        return "\n\n--\n\n".join(formatted_chunks)
    
    # ------------Nodes -----------
    def _ai_assistant(self, state:AgentState):
        print("---CALL ASSISTANT---")
        messages = state['messages']
        last_message = messages[-1].content

        if any(word in last_message.lower() for word in ['price', 'review', 'product']):
            # if we find this word in the last message, use the retriever
            return {"messages": [HumanMessage(content='TOOL: retriever')]}
        # if not found then directly use the llm capability to answer the question
        else:
            prompt = ChatPromptTemplate.from_template(
                "You are a helpful assistant. Answer the user query directly. \n\nQuestion:{question}\n\nAnswer:"
            )
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({'question': last_message})
            return {'messages': [HumanMessage(content = response)]}
        
    # ----Under Node if we find those word then route to the retriever and search in vector DB -----
    def _vector_retriever(self, state:AgentState):
        print("---RETRIEVER---")
        # get the last message
        query = state['messages'][-1].content
        # call the retriever
        retriever = self.retriever_obj.load_retriever()
        # invoke or call the retriever as done in retrieval.py ( call_retriever function )
        docs = retriever.invoke(query)
        # format the docs
        context =self._format_docs(docs)
        return {'messages':[HumanMessage(content =context)]}

    # ---- Check whether document is valid or not below we have retuen both the method (geenerator and rewriter)--------
    def _grade_document(self, state:AgentState)->Literal['generator', 'rewriter']:
        print("---GRADE DOCUMENT---")
        question = state['messages'][0].content # get the first message ( Question user asked)
        docs = state['messages'][-1].content # get the last message 

        prompt = PromptTemplate(
            template="""You are a grader. Question : {question}\nDocs : {docs}\n
            Are docs relevant to the question? Answer yes or no.
            """,
            input_variables = ['question', 'docs'], 
        )
        chain = prompt | self.llm |StrOutputParser() 
        score = chain.invoke({'question': question, 'docs': docs})
        return "generator" if "yes" in score.lower() else "rewriter"
    
    # --------This is generator method what we have called above as grade document -----------
    def _generate(self, state:AgentState):
        print("---GENERATE---")
        # we will reach in generator method when the grader document method is confident that the docs are relevant to the question
        question = state['messages'][0].content # get the first message ( Question user asked)
        docs = state['messages'][-1].content # get the last message
        prompt = ChatPromptTemplate.from_template(
         # this are the prompts that we have written in prompt_library/prompts.py
         PROMPT_REGISTRY[PromptType.PRODUCT_BOT].template   
        )  
        chain = prompt | self.llm | StrOutputParser() 
        response = chain.invoke({'context': docs, "question": question})   
        return {'messages': [HumanMessage(content=response)]}  
    
    # rewriter it will be called when the grader document method is not confident that the docs are relevant to the question
    def _rewrite(self, state:AgentState):
        print("---REWRITE---")
        # Use instance attribute to reliably persist rewrite attempts across nodes
        # Reset at run start (see run_workflow)
        if self.rewrite_count >= 3:
            print("Max rewrite attempts reached. Generating answer with available context.")
            question = state['messages'][0].content
            docs = state['messages'][-1].content
            prompt = ChatPromptTemplate.from_template(
                PROMPT_REGISTRY[PromptType.PRODUCT_BOT].template
            )
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({'context': docs, "question": question})
            return {'messages': [HumanMessage(content=response)]}

        question = state['messages'][0].content
        # Re-write the question using the llm
        new_question = self.llm.invoke(
            [HumanMessage(content=f"Rewrite the query to be clearer : {question}")]
        )
        # increment counter and return rewritten message so Assistant sees it next
        self.rewrite_count += 1
        return {'messages': [HumanMessage(content=new_question.content)]}
    
    #----------Node creation is completed above now Build the Workflow -----------
    def _build_workflow(self):
        # we have used self because we have created AgentState class in nested AgenticRAG class 
        # We cant call it like AgentState() as it will throw an error we can even do it like AgenticRag.AgentState
        # We havent defined in __init__ beacuse its a class(blueprint) not the data 
        workflow = StateGraph(self.AgentState) 
        # Node 1: We will start with 1st node as ai_assistant( if we found the word like price, review, product then it should route to vector retriever )
        # if not found then directly use the llm capability to answer the question
        workflow.add_node("Assistant", self._ai_assistant)
        # Node 2: if we found the word like price, review, product then it should route to vector retriever and fetch the document 
        workflow.add_node("Retriever", self._vector_retriever) 
        # Node 3: Generator method will be called when the grader document method is confident that the docs are relevant to the question
        workflow.add_node("Generator", self._generate)
        # Node 4: rewriter method will be called when the grader document method is not confident that the docs are relevant to the question
        # it will take help of llm to write the question more clearly
        workflow.add_node("Rewriter", self._rewrite)

        #---------------- Now lets start ading the edges-------------------------
        # Start the workflow from assistant node(its a normal edge)
        workflow.add_edge(START, 'Assistant')
        workflow.add_conditional_edges(
            "Assistant",
            # This means if the last message is "TOOL: retriever" then go to Retriever node otherwise directly answer the question and end it 
            lambda state : "Retriever" if "TOOL" in state['messages'][-1].content else END,
            # This is routing map 
            {
            "Retriever": "Retriever",  # If lambda returns "Retriever", go to "Retriever" node
            END: END,                   # If lambda returns END, end the workflow
            },
        )
        # After working with retriever node we will go to grader document method
        # where we will try to figure out either we have to go to generator method or rewriter method
        workflow.add_conditional_edges(
            "Retriever",
            self._grade_document, # if 'yes' thhen we are returing generator from _grade_document method else we are returning rewriter
            {
                "generator": "Generator",
                "rewriter": "Rewriter",
            }
        )
        # If we go the generator node that means we have found the docs that are relevant to the question and we aere good to go
        workflow.add_edge("Generator", END)

        # If we go the rewriter node that means we have not found the docs that are relevant to the question
        # we will take help of llm to write the question more clearly and repeat the loop from Assistant node
        workflow.add_edge("Rewriter", 'Assistant')
        # Debug: print a simple summary of the graph structure so you can verify nodes/edges
        try:
            print("[DEBUG] Built StateGraph - attempting to display nodes/edges summary")
            # try common attributes; fall back to dir() introspection
            nodes = getattr(workflow, "nodes", None)
            edges = getattr(workflow, "edges", None)
            if nodes is not None:
                print("[DEBUG] nodes:", nodes)
            if edges is not None:
                print("[DEBUG] edges:", edges)
            # a safer generic listing
            public = [a for a in dir(workflow) if not a.startswith("_")]
            print("[DEBUG] workflow public attributes:", public)
        except Exception as _e:
            print("[DEBUG] Error while summarizing StateGraph:", _e)
        return workflow
    
    # --------Public Run -----------
    def run_workflow(self, query: str)-> str:
        """Run the workflow for a given query and return the final answer"""
        # We are calling self.app which we have already initialize in __init__ where are compiling the workflow 
        # Set recursion_limit to prevent infinite loops and initialize rewrite_count
        result = self.app.invoke(
            {'messages': [HumanMessage(content=query)], 'rewrite_count': 0},
            config={'configurable': {'recursion_limit': 50, 'thread_id': thread_id}}  # Increased from default 25 to 50
        )
        return result['messages'][-1].content


# -----------Test the Workflow -----------
if __name__ == "__main__":
    rag_agent = AgenticRAG()
    answer = rag_agent.run_workflow("What is the top review of iPhone 15?")
    print("\n Final Answer:\n", answer)











