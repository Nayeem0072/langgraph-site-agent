from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph
import operator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import os
import wikipediaapi
from config import OPENAI_API_KEY
from browser_use import Agent
import asyncio

# Set API key from config
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Initialize the LLM and Wikipedia API
llm = ChatOpenAI(model="gpt-4")
llm_for_browser = ChatOpenAI(
    model="gpt-4o",  
    max_tokens=256,  # Reduced max tokens
    temperature=0.7
)

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
    
    # print(f"State type: {type(state)}")
    # print(f"State content: {state}")
    
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

# Define the browser search node
async def browser_search_node(state: dict):
    messages = state["messages"]
    last_message = messages[-1].content
    
    # Remove "search" from the beginning of the message
    search_query = last_message.replace("search", "", 1).strip()
    
    try:
        agent = Agent(
            task=f"Search for '{search_query}'. Limit to first result only. Provide a brief 2-3 sentence summary.",  # Much more focused task
            llm=llm_for_browser
        )
        result = await agent.run()
        
        # Truncate result if it's too long
        result = result[:500] if len(result) > 500 else result
        
        return {
            "messages": messages,
            "next_step": "conversation",
            "wiki_content": f"Search summary:\n{result}"
        }
    except Exception as e:
        return {
            "messages": messages,
            "next_step": "conversation",
            "wiki_content": f"Error during search: {str(e)}"
        }

# Update the router function
def router(state: dict) -> dict:
    last_message = state["messages"][-1].content.lower()
    
    if last_message.startswith("search"):
        next_step = "browser_search"
    else:
        # Existing logic for question words
        question_words = ["what", "who", "where", "when", "why", "how"]
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
workflow.add_node("browser_search", browser_search_node)

# Add edges
workflow.set_entry_point("router")
workflow.add_conditional_edges(
    "router",
    lambda x: x["next_step"],
    {
        "wiki_search": "wiki_search",
        "browser_search": "browser_search",
        "conversation": "conversation"
    }
)
workflow.add_edge("wiki_search", "conversation")
workflow.add_edge("browser_search", "conversation")

# Set finish point
workflow.set_finish_point("conversation")

# Compile the workflow
chain = workflow.compile()

# Example usage
if __name__ == "__main__":
    # Initial state
    initial_state = {
        "messages": [HumanMessage(content="Hello!")],
        "next_step": "router",
        "wiki_content": ""
    }
    
    async def run_chain():
        # Run the initial conversation
        current_state = await chain.ainvoke(initial_state)
        
        # Print the assistant's greeting
        print(f"Assistant: {current_state['messages'][-1].content}")
        
        # Continue conversation until user types 'exit'
        while True:
            # Get user input
            user_input = input("Human: ")
            
            # Check for exit condition
            if user_input.lower() == "exit":
                print("Assistant: Goodbye!")
                break
            
            # Update state with new user message
            current_state["messages"] = current_state["messages"] + [HumanMessage(content=user_input)]
            current_state["next_step"] = "router"
            current_state["wiki_content"] = ""
            
            # Run the chain
            current_state = await chain.ainvoke(current_state)
            
            # Print the assistant's response
            print(f"Assistant: {current_state['messages'][-1].content}")

    # Run the async main function
    asyncio.run(run_chain())
