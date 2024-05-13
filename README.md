# Distributed Token Management System

## Overview

This project implements a robust payment system as part of HUJI's Reliability in Distributed Systems course taught by Dr. Ittai Abraham. The system maintains 60 token objects, with functionalities to manage token transactions between clients, handle dynamic server-client role transformations, and ensure system integrity through fault tolerance and asynchrony tests.

### Key Features

- **Token Management:** Handles 60 unique tokens, each identified by an ID, a version number, and an owner.
- **Dynamic Role Transformation:** Supports dynamic changes in roles from server to client and vice versa, while maintaining system stability.
- **Fault Tolerance:** Includes mechanisms to handle omission faults with rigorous safety and liveness tests.
- **Asynchrony:** Simulates and handles asynchronous communication between servers.
- **Automated Testing:** Features automated and manual testing for both liveness and safety, ensuring reliability and robustness.

### Components

1. **Token Objects:** Each token is a tuple (`ID`, `version`, `owner`), uniquely identified by its `ID`, with `version` incrementing on transactions, and `owner` indicating the current owner.
2. **Clients and Servers:** System starts with 6 clients, each owning 10 tokens, and supports 3 to 7 servers with role flexibility.
3. **Network Simulation:** Simulates network delays and faults to test system's fault tolerance capabilities.

## Usage

### Setup

Clone the repository and navigate into the project directory:

```bash
git clone https://github.com/Barvaziyel/Distributed-System-Omission-Faults.git
cd Distributed-System-Omission-Faults
```

### Running the System

To start the system and interact with it through manual commands, run:

```bash
python main.py
```

Follow the on-screen prompts to execute operations like token transfers (`pay`), fetching token information (`gettokens`), and transforming roles between client and server.

## Implementation Details

### System Operations

- **Pay:** Transfers ownership of a token to another client, updating the token's version.
- **GetTokens:** Retrieves all tokens owned by a specific client.
- **Transform to Client/Server:** Dynamically changes the role of servers and clients based on the system's needs.
- **Status:** Displays the current state of all nodes within the system.
- **Token Status:** Provides a detailed view of the tokens each server is managing.
- **Help:** Lists available commands and their descriptions to assist users in navigating the system.
- **Close:** Safely terminates the system session and continues the run of the test.

### Fault Tolerance

Ensures that the system can handle up to `f < n/2` omission faults, where `n` is the number of servers, while handling:

- **Dynamic Role Adjustments:** Servers can downgrade to clients and vice versa, thus also changing which servers are faulty.
- **Asynchronous Network Simulation:** Tests system performance under varying network conditions to ensure consistent behavior.


## Acknowledgments

- Dr. Ittai Abraham for the leading this journey without fault - Byzantine or otherwise :)
