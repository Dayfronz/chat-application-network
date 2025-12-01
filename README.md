This project is focused oon using Python to create a chat application that can support 2 clients

================================
AUGMENTATION PLAN
================================

Augmentation Plan for Chat Application

1. Introduction

This document outlines the enhancements I added to the base chat application. The original assignment required a working multi-client chat program, and then several additional features to extend the functionality. These augmentations were chosen to resemble real-world messaging applications while still being realistic to implement within the project timeline.

2. Baseline System Before Augmentation

Before adding new features, the program already supported:

Multiple clients connecting through a central server

Unique client ID assignment

Direct messaging between clients

A command to view the list of connected clients

Clean connection and disconnection handling

This basic functionality created a good foundation for extending the system.

3. Augmented Features Added

Message Delivery Receipts
The server assigns an ID to each message and sends a confirmation back to the sender once the message is forwarded.

Reply System
Clients can reference and reply to specific messages using their message ID.

Message Searching
Clients can search their local history using keywords.

Temporary Messages
Clients can send messages that automatically delete from their own history after a set number of seconds.

These features provide a mix of convenience, interactivity, and realism similar to modern chat apps.

4. Text-Based Class Diagram

ChatServer

clients

message_counter

start()

handle_new_client()

route_chat_message()

send_json()

ChatClient

client_id

history

connect()

listen_loop()

input_loop()

send_chat()

search_history()

send_reply()

5. Text-Based Flow Chart Description

Client starts
→ Connect to server
→ Receive welcome message and client list
→ Begin listener thread
→ User enters commands
→ Client sends JSON packet to server
→ Server processes message
→ Server routes chat or sends receipt
→ Client displays incoming messages


=========================================
FINAL REPORT 
=========================================

Final Report: Python Client–Server Chat Application

1. Introduction

The purpose of this project was to design and implement a working chat application using Python and TCP sockets. The assignment required a server application that accepts multiple client connections, assigns each client a unique identifier, and routes messages between them. All communication had to pass through a central server, and the clients needed to be able to see who else was connected and send messages directly to each other.

After building the basic working version, I was also required to add several “modern” messaging features. These additions were meant to extend the original functionality and make the system resemble real-world chat programs. The features I chose included message delivery receipts, replies to previous messages, message searching, and temporary messages that delete themselves after a set period of time.

Overall, the project helped me understand how TCP communication works at a lower level, how to manage multiple concurrent users, and how to extend a basic protocol to support new features. Throughout the report I explain how the system is designed, how it works, and how each feature was implemented.

2. System Architecture and Design

This chat system is made up of two Python files: server.py and client.py. Both files use the Python socket library to handle network communication and the threading library to allow concurrent processing.

The server is responsible for accepting new clients, keeping track of which clients are connected, assigning them IDs like C001 or C002, and routing messages between them. Each time a new client connects, the server creates a new thread so that one client’s activity does not block other clients.

The client program connects to the server, receives its assigned ID, and then starts two loops: a listening loop and a user input loop. The listening loop receives JSON-formatted messages from the server, while the input loop waits for the user to type commands like /msg, /reply, /search, and /temp. This design allows the client to receive messages at any time, even while the user is typing.

To keep communication structured and easy to parse, every message between the server and clients is sent as JSON and separated by newline characters. This makes it easier to add fields like message_id, reply_to, or timestamps.

3. Data Structures and Protocol

The server stores all connected clients in a dictionary structured like this:

clients = {
"C001": {"socket": sock, "address": ('127.0.0.1', 50001), "name": "C001"},
"C002": {"socket": sock, "address": ('127.0.0.1', 50002), "name": "C002"}
}

The server also uses a global message_counter so that each message gets a unique message_id. This ID is used for receipts, replies, and local message history.

On the client side, every sent or received message is stored in a history list:

history = [
{
"id": 5,
"direction": "in",
"peer": "C002",
"text": "hey",
"timestamp": 1733012345,
"reply_to": None,
"temp_until": None,
"deleted": False
}
]

This history structure allows me to search messages, reply to specific messages, and delete temporary ones when their expiration time is reached.

Communication uses JSON packets such as:

{"type": "chat", "from": "C001", "to": "C002", "text": "Hello!", "message_id": 7}

This packet-based design made it much easier to add new features without rewriting major parts of the code.

4. Augmented Features

The modern messaging features I added were chosen because they were realistic but also manageable to implement using the existing structure.

Delivery Receipts
The server generates a message ID for every message and sends back a receipt packet to the sender after the target client receives it. The client prints confirmations like:
[RECEIPT] Message #7 delivered to C002.

Replies to Previous Messages
Since all messages are saved in local history with message IDs, I implemented a /reply command. When the user runs /reply 5 ok sounds good, the program figures out who message #5 was from and sends a new chat message with reply_to set to 5. The recipient sees something like:
C001 (reply to #5): ok sounds good.

Message Searching
The /search command scans the text of the messages stored in the local history list and prints matches. This works only on the local client and does not require server support.

Temporary Messages
The /temp command sends a message that is marked with a future expiration time. A background thread removes the message from the sender’s local history after that time passes. The recipient still keeps the message. This feature gives the effect of self-destructing messages.

5. Evaluation

After completing the project, I was able to verify that the system meets the assignment requirements. Multiple clients can connect at the same time, messages route correctly through the server, and the augmented features work as expected.

One strength of the system is that the JSON protocol made it very easy to add new fields. Another benefit is the separation of the listener thread and the user input thread, which lets users receive incoming messages even when they are typing something else.

There are also areas for improvement. The system does not include any sort of encryption, so everything is sent in plain text. The server also does not store anything permanently; all data resets when the server shuts down. Additionally, although the command-line interface works, it would be more user-friendly with a graphical interface.

Overall, the project helped me better understand how multi-client applications work, how protocols are designed, and how to structure communication between independent programs.

6. Running and Installation Instructions

Install Python 3 on your machine.

Place server.py and client.py in the same folder.

Open a terminal and start the server with:
python server.py

Open two or more terminals and start clients with:
python client.py

Use commands like:
/msg C002 hello
/reply 3 sure
/search hello
/temp C002 10 this will expire soon
/exit
