from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph
import operator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import os
import wikipediaapi
from config import OPENAI_API_KEY

# Set API key from config
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Initialize the LLM and Wikipedia API
llm = ChatOpenAI(model="gpt-4")
wiki = wikipediaapi.Wikipedia(
    user_agent='LangGraph Tutorial Bot/1.0 (nayeem.synesis@gmail.com)',  # Replace with your email
    language='en'
)

# Define the Wikipedia search node
def wiki_search_node(state: dict):
    # Type checking and validation
    if not isinstance(state, dict):
        raise TypeError("State must be a dictionary")
    
    messages = state.get("messages", [])
    if not isinstance(messages, (list, tuple)):
        raise TypeError("Messages must be a sequence")
    
    if not messages:
        return {
            "messages": messages,
            "next_step": "conversation",
            "wiki_content": "No messages found"
        }
        
    last_message = messages[-1].content
    
    print(f"State type: {type(state)}")
    print(f"State content: {state}")
    
    # Search Wikipedia
    try:
        page = wiki.page(last_message)
        if page.exists():
            summary = page.summary[0:1500]
            return {
                "messages": messages,
                "next_step": "conversation",
                "wiki_content": summary
            }
        else:
            return {
                "messages": messages,
                "next_step": "conversation",
                "wiki_content": "No Wikipedia information found for this topic."
            }
    except Exception as e:
        return {
            "messages": messages,
            "next_step": "conversation",
            "wiki_content": f"Error searching Wikipedia: {str(e)}"
        }

# Define the conversation node
def conversation_node(state: dict):
    messages = state["messages"]
    wiki_content = state["wiki_content"]
    
    # Create a prompt that includes Wikipedia information
    if wiki_content:
        system_context = f"Here's some relevant information from Wikipedia:\n{wiki_content}\n\nPlease use this information to provide a detailed response."
        messages = list(messages) + [HumanMessage(content=system_context)]
    
    # Call the LLM
    response = llm.invoke(messages)
    
    # Add the response to the messages
    new_messages = list(messages[:-1] if wiki_content else messages) + [response]
    
    return {
        "messages": new_messages,
        "next_step": "end",
        "wiki_content": ""
    }

# Update the router function
def router(state: dict) -> dict:
    # If the message contains question words, route to wiki search
    question_words = ["what", "who", "where", "when", "why", "how"]
    last_message = state["messages"][-1].content.lower()
    
    next_step = "wiki_search" if any(word in last_message for word in question_words) else "conversation"
    
    return {
        **state,
        "next_step": next_step
    }

# Define the workflow
workflow = StateGraph(dict)  # Use dict instead of custom class

# Add nodes to the workflow
workflow.add_node("router", router)
workflow.add_node("wiki_search", wiki_search_node)
workflow.add_node("conversation", conversation_node)

# Add edges
workflow.set_entry_point("router")
workflow.add_conditional_edges(
    "router",
    lambda x: x["next_step"],
    {
        "wiki_search": "wiki_search",
        "conversation": "conversation"
    }
)
workflow.add_edge("wiki_search", "conversation")

# Set finish point
workflow.set_finish_point("conversation")

# Compile the workflow
chain = workflow.compile()

# Example usage
if __name__ == "__main__":
    # Initial state
    initial_state = {
        "messages": [HumanMessage(content="What is quantum computing?")],
        "next_step": "router",
        "wiki_content": ""
    }
    
    # Run the chain
    result = chain.invoke(initial_state)
    
    # Print the conversation
    for message in result["messages"]:
        if isinstance(message, HumanMessage):
            if "Wikipedia" not in message.content:
                print(f"Human: {message.content}")
        else:
            print(f"Assistant: {message.content}")
