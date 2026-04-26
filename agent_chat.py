import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

system_message = SystemMessage(content="You are a helpful assistant that translates English to French.")


def main():
    chat = ChatOpenAI(model="gpt-4o-mini")

    print("Welcome to the GPT translator! Type 'exit' to quit.")
    print("Enter an English sentence to translate to French:")

    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        response = chat.invoke([system_message, HumanMessage(content=user_input)])
        print(f"GPT: {response.content}")


if __name__ == "__main__":
    main()
