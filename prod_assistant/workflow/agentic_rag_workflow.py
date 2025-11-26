from typing import Annotated, Sequence, TypedDict, Literal
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from prompt_library.prompts import PROMPT_REGISTRY, PromptType
from retriever.archieved.retrieval import Retriever
from utils.model_loader import ModelLoader
from langgraph.checkpoint.memory import MemorySaver
import asyncio
import uuid

# DuckDuckGo search helper (optional package)
try:
    import duckduckgo_search
    ddg = True  # Just a flag to indicate it's installed
except ImportError as e:
    print(f"[DEBUG] duckduckgo_search not available: {e}")
    ddg = None


class AgenticRAG:
    """Agentic RAG pipeline using langGraph"""

    class AgentState(TypedDict):
        # The current state of the agent
        messages: Annotated[Sequence[BaseMessage], add_messages]
        # rewrite_count kept here for typing; runtime counter is stored on self
        rewrite_count: int

    def __init__(self):
        self.retriever_obj = Retriever()
        self.model_loader = ModelLoader()
        self.llm = self.model_loader.load_llm()
        # Counter to track rewrites across a single run (reset in run_workflow)
        self.rewrite_count = 0
        # Flag to indicate retriever has been exhausted and should fallback to web search
        self.skip_retriever = False
        self.checkpointer = MemorySaver()
        self.thread_id = str(uuid.uuid4())
        self.workflow = self._build_workflow()
        # compile workflow into runnable app
        self.app = self.workflow.compile(checkpointer=self.checkpointer)
        # Debug introspection
        try:
            print("[DEBUG] Workflow compiled. workflow repr:", repr(self.workflow))
            print("[DEBUG] Compiled app repr:", repr(self.app))
        except Exception as _e:
            print("[DEBUG] Error introspecting workflow/app:", _e)

    # -----------Helpers----------
    def _format_docs(self, docs) -> str:
        if not docs:
            return "No relevant documents found."

        formatted_chunks = []
        for d in docs:
            meta = getattr(d, "metadata", {}) or {}
            page = getattr(d, "page_content", str(d)) or ""
            formatted = (
                f"Title : {meta.get('product_title', 'N/A')}\n"
                f"Price : {meta.get('price', 'N/A')}\n"
                f"Rating : {meta.get('rating', 'N/A')}\n"
                f"Reviews :\n{page.strip()}"
            )
            formatted_chunks.append(formatted)
        return "\n\n--\n\n".join(formatted_chunks)

    # ------------Nodes -----------
    def _ai_assistant(self, state: AgentState):
        """Decides whether to call retriever or web search. Does NOT answer directly."""
        print("---CALL ASSISTANT---")
        messages = state["messages"]
        last_message = messages[-1].content
        last_lower = last_message.lower()

        trigger = any(
            word in last_lower
            for word in ["price", "review", "product", "cost", "how much", "msrp"]
        )
        print(f"[DEBUG] assistant last_message={last_message!r}, trigger_retriever={trigger}, skip_retriever={self.skip_retriever}")

        # If retriever has been exhausted, force web search
        if self.skip_retriever:
            print("[DEBUG] Retriever exhausted, forcing web search")
            return {"messages": [HumanMessage(content="TOOL: web")]}
        elif trigger:
            # Signal the workflow to call the vector retriever
            return {"messages": [HumanMessage(content="TOOL: retriever")]}
        else:
            # Signal the workflow to call the web search (DuckDuckGo)
            return {"messages": [HumanMessage(content="TOOL: web")]}

    # ----Under Node if we find those word then route to the retriever and search in vector DB -----
    def _vector_retriever(self, state: AgentState):
        print("---RETRIEVER---")
        query = state["messages"][-1].content
        retriever = self.retriever_obj.load_retriever()
        docs = retriever.invoke(query)
        context = self._format_docs(docs)

        # debug: show how many docs were returned and snippet
        try:
            print(f"[DEBUG] Retriever returned {len(docs)} docs")
            for i, d in enumerate(docs[:2]):
                snippet = getattr(d, "page_content", "")[:200]
                print(f"[DEBUG] doc[{i}] snippet: {repr(snippet)}")
        except Exception:
            pass

        return {"messages": [HumanMessage(content=context)]}

    # ---- Check whether document is valid or not -----------
    def _grade_document(self, state: AgentState) -> Literal["generator", "rewriter"]:
        print("---GRADE DOCUMENT---")
        question = state["messages"][0].content
        docs = state["messages"][-1].content

        prompt = PromptTemplate(
            template="""You are a grader. Question : {question}\nDocs : {docs}\n
            Are docs relevant to the question? Answer yes or no.
            """,
            input_variables=["question", "docs"],
        )
        chain = prompt | self.llm | StrOutputParser()
        score = chain.invoke({"question": question, "docs": docs})
        print(f"[DEBUG] grade score_raw: {score!r}")
        return "generator" if "yes" in score.lower() else "rewriter"

    # Generator (uses docs when grader says yes)
    def _generate(self, state: AgentState):
        print("---GENERATE---")
        question = state["messages"][0].content
        docs = state["messages"][-1].content
        prompt = ChatPromptTemplate.from_template(PROMPT_REGISTRY[PromptType.PRODUCT_BOT].template)
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke({"context": docs, "question": question})
        return {"messages": [HumanMessage(content=response)]}

    # Rewriter: rewrite the question; after N rewrites, give up and generate answer
    def _rewrite(self, state: AgentState):
        print("---REWRITE---")
        print(f"[DEBUG] rewrite_count before = {self.rewrite_count}")
        
        # Check if we've already rewritten 3 times
        if self.rewrite_count >= 1:
            print("[DEBUG] Max rewrite attempts (3) reached. Setting skip_retriever=True and routing to web search.")
            # Set flag to skip retriever next time and route back to Assistant which will use web search
            self.skip_retriever = True
            question = state["messages"][0].content
            return {"messages": [HumanMessage(content=f"Rewritten query for web search: {question}")]}
        
        # Otherwise, rewrite and increment counter
        question = state["messages"][0].content
        new_question = self.llm.invoke([HumanMessage(content=f"Rewrite the question to be clearer: {question}")])
        self.rewrite_count += 1
        print(f"[DEBUG] rewrite_count after = {self.rewrite_count}")

        return {"messages": [HumanMessage(content=new_question.content)]}

    # ----------Web search node (DuckDuckGo) ----------
    def _web_search(self, state: AgentState):
        print("---WEB SEARCH---")
        
        # Fail fast if duckduckgo_search is not installed
        if ddg is None:
            raise ImportError(
                "duckduckgo_search is not installed. "
                "Please install it: pip install duckduckgo_search\n"
                "Or implement an alternative web search in _web_search()."
            )
        
        # Extract the original question - find the first message that's not a tool signal
        messages = state["messages"]
        original_question = None
        for msg in messages:
            content = msg.content
            if not content.startswith("TOOL:") and not content.startswith("Rewritten query"):
                original_question = content
                break
        
        if not original_question:
            # Fallback: use first message
            original_question = messages[0].content if messages else "iPhone 15"
        
        print(f"[DEBUG] web_search using question: {original_question}")
        
        try:
            from duckduckgo_search import DDGS
            print("[DEBUG] Initializing DDGS and searching...")
            results = list(DDGS().text(original_question, max_results=5))
            print(f"[DEBUG] DDGS returned {len(results)} results")
        except Exception as e:
            print(f"[DEBUG] Web search error: {type(e).__name__}: {e}")
            # Return fallback message instead of failing
            fallback = f"Unable to retrieve web search results for: {original_question}. Please try a different query."
            print(f"[DEBUG] Using fallback message: {fallback}")
            return {"messages": [HumanMessage(content=fallback)]}

        if not results:
            # Return fallback message instead of failing
            fallback = f"No web search results found for: {original_question}. The query might be too specific or no online sources are available."
            print(f"[DEBUG] Using fallback message: {fallback}")
            return {"messages": [HumanMessage(content=fallback)]}

        formatted = []
        for r in results:
            title = r.get("title") or r.get("text") or "N/A"
            snippet = r.get("body") or r.get("snippet") or ""
            href = r.get("href") or r.get("url") or ""
            formatted.append(f"Title: {title}\nURL: {href}\nSnippet: {snippet}")

        context = "\n\n--\n\n".join(formatted)
        print(f"[DEBUG] web search formatted {len(results)} results")
        return {"messages": [HumanMessage(content=context)]}

    #----------Node creation is completed above now Build the Workflow -----------
    def _build_workflow(self):
        workflow = StateGraph(self.AgentState)

        # Nodes
        workflow.add_node("Assistant", self._ai_assistant)
        workflow.add_node("Retriever", self._vector_retriever)
        workflow.add_node("WebSearch", self._web_search)
        workflow.add_node("Generator", self._generate)
        workflow.add_node("Rewriter", self._rewrite)

        # Edges
        workflow.add_edge(START, "Assistant")

        # Assistant -> Retriever or WebSearch depending on signal
        workflow.add_conditional_edges(
            "Assistant",
            lambda state: "Retriever" if "TOOL: retriever" in state["messages"][-1].content else "WebSearch",
            {"Retriever": "Retriever", "WebSearch": "WebSearch"},
        )

        # Retriever -> Grade (generator/rewriter)
        workflow.add_conditional_edges(
            "Retriever",
            self._grade_document,
            {"generator": "Generator", "rewriter": "Rewriter"},
        )

        # WebSearch -> Grade (same grading step)
        workflow.add_conditional_edges(
            "WebSearch",
            self._grade_document,
            {"generator": "Generator", "rewriter": "Rewriter"},
        )

        # Rewriter -> back to Assistant (which will check skip_retriever flag)
        workflow.add_edge("Rewriter", "Assistant")

        # Generator ends
        workflow.add_edge("Generator", END)

        # Debug: summary
        try:
            print("[DEBUG] Built StateGraph - summary:")
            # try to print nodes/edges in a best-effort way
            nodes = getattr(workflow, "nodes", None)
            edges = getattr(workflow, "edges", None)
            if nodes is not None:
                print("[DEBUG] nodes:", nodes)
            if edges is not None:
                print("[DEBUG] edges:", edges)
            public = [a for a in dir(workflow) if not a.startswith("_")]
            print("[DEBUG] workflow public attributes:", public)
        except Exception as _e:
            print("[DEBUG] Error while summarizing StateGraph:", _e)

        return workflow

    # --------Public Run -----------
    def run_workflow(self, query: str, thread_id: str='default_thread') -> str:
        """Run the workflow for a given query and return the final answer"""
        # Reset per-run counters and flags
        self.rewrite_count = 0
        self.skip_retriever = False
        # Invoke the compiled app. Use recursion_limit as a safety net.
        result = self.app.invoke({"messages": [HumanMessage(content=query)]}, 
                                 config={'configurable': {'recursion_limit': 50, 
                                                          'thread_id': thread_id}}) # Increased from default 25 to 50)
        
        # Extract and return the last message
        last_message = result["messages"][-1].content
        return last_message
    
        # Inorder to work with Evaluation metrics
        # function call will be associated like we have done in retreival code
        # we will get some score
        # then we can put some condition
        # if score > 0.75 
        #     return last_message# then generate output
        # else
        #     continue the loop again


# -----------Test the Workflow -----------
if __name__ == "__main__":
    rag_agent = AgenticRAG()
    answer = rag_agent.run_workflow("What is the review of iPhone 15?")
    print("\n Final Answer:\n", answer)