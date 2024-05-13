import queue
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from colorama import Fore, Back, Style


class NodeState:
    """ Abstract base class for node states. """

    def transform_role(self):
        raise NotImplementedError


class ServerState(NodeState):
    def __init__(self, node):
        self.node = node
        self.tokens = {i: Token(i, (i % 6) + 1) for i in range(60)}

    def handle_request(self, request):
        # print(f"Server {self.node.id} received request: {request}\n")
        if request['type'] == 'pay':
            response = self.handle_pay_request(request)
        elif request['type'] == 'gettokens':
            response = self.handle_get_tokens_request()
        elif request['type'] == 'sync_request':
            response = self.handle_sync_request()
        else:
            response = {"status": "error", "msg": "Unknown request type"}
        # print(f"Server {self.node.id} sending response: {response}\n")
        return response

    def handle_pay_request(self, request):
        token_id = request['token_id']
        new_owner_id = request['new_owner_id']
        version = request['version']
        token = self.tokens.get(token_id, None)
        if token and token.version == version:
            token.owner = new_owner_id
            token.version += 1
            return {"status": "OK", "token_id": token_id, "new_version": token.version}
        elif token and token.version < version:
            self.synchronize_state()
            return {"status": "error", "msg": "Syncing state with other servers"}
        else:
            return {"status": "error", "msg": "Token not found or version mismatch"}

    def handle_get_tokens_request(self):
        return {"tokens": self.tokens}

    def synchronize_state(self):
        request = {"type": "sync_request"}
        all_responses = self.node.network.broadcast_request_for_sync(request, self.node)

        majority_count = (len(self.node.network.servers) // 2) + 1
        collected_responses = []
        updated_tokens = self.tokens
        response_received = threading.Event()
        collected_responses.append(self.handle_sync_request())

        def collect_responses():
            attempts = 0
            max_attempts = 4
            for response in all_responses:
                if response:
                    collected_responses.append(response)
                    for token_id, token_data in response.items():
                        if token_data['version'] > updated_tokens[token_id].version:
                            updated_tokens[token_id] = Token(token_id, token_data['owner'], token_data['version'])
                    if len(collected_responses) >= majority_count:
                        response_received.set()
                        # print("Collected enough responses to satisfy majority.\n")
                        break
                else:
                    attempts += 1
                    if attempts >= max_attempts:
                        # print("Maximum attempts reached without collecting enough responses, breaking out.\n")
                        break

        # Start collecting responses after initiating the broadcast
        response_thread = threading.Thread(target=collect_responses)
        response_thread.start()
        response_thread.join()  # Wait for the thread to finish

        if response_received.is_set():
            self.tokens = updated_tokens
            # print("Server state synchronized with the most updated versions from other servers.\n")
        else:
            # print("Failed to synchronize state due to insufficient valid responses.\n")
            pass
        return updated_tokens if response_received.is_set() else {}

    def transform_role(self):
        if len(self.node.network.servers) > 3:
            self.node.state = ClientState(self.node)
            self.node.network.remove_server(self.node)
            print(f"Transformed from Server to Client. Current node state: {type(self.node.state).__name__}\n")
        else:
            print("Minimum server count reached; cannot transform to client.\n")

    def handle_sync_request(self):
        token_data = {token.id: {"owner": token.owner, "version": token.version} for token in self.tokens.values()}
        return token_data


class ClientState(NodeState):
    def __init__(self, node):
        self.node = node
        self.response_queue = Queue()
        self.response_received = threading.Event()

    def handle_request(self, request):
        response = None
        if request['type'] == 'pay':
            response = self.transfer_token(request)
        elif request['type'] == 'gettokens':
            response = self.get_tokens(request['owner_id'])
        return response

    def wait_for_responses(self, request):
        majority_count = (len(self.node.network.servers) // 2) + 1
        responses = []
        all_responses = self.node.network.broadcast_request(request, self.node.id)

        def collect_responses():
            attempts = 0
            max_attempts = 4

            while len(responses) < majority_count and attempts < max_attempts:
                try:
                    response = self.response_queue.get()
                    if response:
                        responses.append(response)
                    if len(responses) >= majority_count:
                        self.response_received.set()
                        # print("Collected enough responses to satisfy majority.\n")
                except queue.Empty:
                    # print("No new responses, incrementing attempt counter.\n")
                    attempts += 1  # Increment the attempts counter

            if attempts >= max_attempts:
                # print("Maximum attempts reached without collecting enough responses.\n")
                pass
            if not self.response_received.is_set() and len(responses) < majority_count:
                # print("Not enough responses collected, thread will terminate.\n")
                pass

        # Start collecting responses after initiating the broadcast
        for response in all_responses:
            self.response_queue.put(response)

        threading.Thread(target=collect_responses).start()
        self.response_received.wait()
        if not self.response_received.is_set():
            # print("Failed to collect majority.\n")
            pass
        else:
            # print(f"Majority responses collected: {responses}\n")
            pass

        return responses if self.response_received.is_set() else []

    def transfer_token(self, request):
        owned_tokens = self.get_tokens(self.node.id)
        token = [t for t in owned_tokens if t['id'] == request['token_id']]
        if len(token) == 0:
            print("Token not found or not owned by client.\n")
            return
        token = max(token, key=lambda t: t['version'])

        updated_request = {
            'type': 'pay',
            'token_id': token['id'],
            'version': token['version'],
            'new_owner_id': request['new_owner_id']
        }

        responses = self.wait_for_responses(updated_request)
        print(f"Received responses: {responses}\n")
        return responses

    def get_tokens(self, owner_id):
        request = {
            'type': 'gettokens',
            'owner_id': owner_id
        }

        responses = self.wait_for_responses(request)
        return self.process_token_responses(responses, owner_id)

    @staticmethod
    def process_token_responses(responses, owner_id):
        all_tokens = []
        for response in responses:
            if 'tokens' in response:
                all_tokens.append(response['tokens'])

        tokens_by_id = {}
        for tokens in all_tokens:
            for token_id in tokens.keys():
                if token_id not in tokens_by_id or tokens[token_id].version > tokens_by_id[token_id].version:
                    tokens_by_id[token_id] = tokens[token_id]
        owned_tokens = {}
        for token_id in tokens_by_id.keys():
            if tokens_by_id[token_id].owner == owner_id:
                owned_tokens[token_id] = {'id': token_id, 'version': tokens_by_id[token_id].version}
        return list(owned_tokens.values())

    def transform_role(self):
        if len(self.node.network.servers) < 7:
            self.node.state = ServerState(self.node)
            self.node.state.synchronize_state()
            self.node.network.add_server(self.node)
            print(f"Transformed from Client to Server. Current node state: {type(self.node.state).__name__}\n")
        else:
            print("Transformation to server failed: Max server count reached.\n")


class Node:
    def __init__(self, id, network, initial_state):
        self.id = id
        self.network = network
        self.state = initial_state(self)  # The state can be ClientState or ServerState

    def handle_request(self, request):
        return self.state.handle_request(request)

    def transform_role(self):
        self.state.transform_role()


class Network:
    def __init__(self):
        self.servers = []
        self.clients = []
        self.is_open = True
        self.max_faults = len(self.servers) - (len(self.servers) // 2 + 1)  # Maximum number of faults to tolerate
        self.faulty_servers = []
        self.faults_flag = True

    def broadcast_request(self, request, sender_id):
        # print(f"Starting to broadcast request to {len(self.servers)} servers: {request}\n")
        with ThreadPoolExecutor(max_workers=len(self.servers)) as executor:
            # Submit all requests to servers and store futures
            future_to_server = {executor.submit(server.handle_request, request): server for server in self.servers}
            responses = []
            majority_count = (len(self.servers) // 2) + 1
            print(f"Majority count required for responses: {majority_count}\n")

            # Collect responses as they become available
            for future in as_completed(future_to_server):
                try:
                    response = future.result()  # Wait for the future to return a result
                    if response:
                        responses.append(response)
                        # print(f"Received response from server {future_to_server[future].node.id}: {response}\n")
                    else:
                        # print(f"Received no or invalid response from server {future_to_server[future].node.id}\n")
                        pass
                    # Check if the majority of responses have been received to possibly break early
                    if len(responses) >= majority_count:
                        # print("Received majority of responses, breaking early.\n")
                        break
                except Exception as exc:
                    print(f"Server {future_to_server[future].node.id} failed: {str(exc)}\n")
                    pass
            # print(f"Total responses collected: {len(responses)} out of {len(self.servers)} servers\n")

        return responses

    def broadcast_request_for_sync(self, request, sender):
        responses = Queue()  # Thread-safe queue to collect responses
        response_count = threading.Event()  # Event to signal when majority is reached
        majority_count = len(self.servers) // 2
        responses_collected = 0

        def send_request(server):
            nonlocal responses_collected
            if server != sender:  # Avoid sending the request to the server initiating the sync
                response = server.handle_request(request)
                if response:
                    responses.put(response)
                    # Increment the response counter safely with lock
                    with threading.Lock():
                        responses_collected += 1
                        if responses_collected >= majority_count:
                            response_count.set()  # Signal that majority has been reached

        # Create a thread for each server to handle the request
        threads = [threading.Thread(target=send_request, args=(server,)) for server in self.servers if server != sender]
        for thread in threads:
            thread.start()

        # Wait for the majority of responses or continue if already reached
        response_count.wait()

        # Ensure all threads complete their task that have started before the event was set
        for thread in threads:
            thread.join()

        # Collect all responses that were put in the queue
        result_responses = []
        while not responses.empty():
            result_responses.append(responses.get())

        return result_responses

    def add_server(self, node):
        if len(self.servers) < 7:
            if node in self.clients:
                self.clients.remove(node)
                print(f"Removed client from network. Remaining clients: {len(self.clients)}\n")
            if node not in self.servers:
                self.servers.append(node)
                self.max_faults = len(self.servers) - (len(self.servers) // 2 + 1)  # Update max faults
                self.faulty_servers = []  # Reset faulty servers
                # Randomly select max_faults number of servers to be faulty
                if self.max_faults > 0:
                    self.faulty_servers = random.sample(self.servers, self.max_faults)
                print(f"Added new server to network, ID: {node.id}. Total servers: {len(self.servers)}\n")
        else:
            print("Maximum server count reached.\n")

    def remove_server(self, node):
        if len(self.servers) > 3 and node in self.servers:
            self.servers.remove(node)
            self.max_faults = len(self.servers) - (len(self.servers) // 2 + 1)  # Update max faults
            self.faulty_servers = []  # Reset faulty servers
            # Randomly select max_faults number of servers to be faulty
            if self.max_faults > 0:
                self.faulty_servers = random.sample(self.servers, self.max_faults)
            if node not in self.clients:
                self.clients.append(node)
            print(f"Transformed server to client. Remaining servers: {len(self.servers)}\n"
                  f"Remaining clients: {len(self.clients)}\n")
        else:
            if len(self.servers) <= 3:
                print("Cannot remove server; minimum server count would be breached.\n")
            else:
                print("Node is not a server or already removed.\n")

    def add_client(self, node):
        if node not in self.clients:  # Ensure node is not already listed as a client
            self.clients.append(node)
            print(f"Added new client to network, ID: {node.id}. Total clients: {len(self.clients)}\n")

    def close_system(self):
        self.is_open = False  # Simulate closing the network
        print("Network closed.\n")


class Token:
    def __init__(self, id, owner_id, version=1):
        self.id = id
        self.version = version
        self.owner = owner_id


class SimulatedNetwork(Network):
    def __init__(self, delay=0):
        super().__init__()
        self.delay = delay  # Simulated network delay in seconds

    def broadcast_request_for_sync(self, request, sender):
        print(
            f"Broadcasting request with simulated delay up to {self.delay} seconds: {request}\n")
        with ThreadPoolExecutor(max_workers=len(self.servers) - 1) as executor:
            future_to_server = {}
            for server in self.servers:
                if server == sender:
                    continue
                future = executor.submit(self.simulated_handle_request, server, request)
                future_to_server[future] = server
            # print(f"Tasks submitted for all servers.\n")

            responses = []
            majority_count = len(self.servers) // 2
            print(f"Majority count needed: {majority_count}\n")

            for future in as_completed(future_to_server):
                try:
                    response = future.result()
                    if response:
                        responses.append(response)
                        # print(f"Received valid response from server {future_to_server[future].id}: {response}\n")
                    else:
                        # print(f"No or invalid response received from server {future_to_server[future].id}\n")
                        pass
                    if len(responses) >= majority_count:
                        # print(f"Majority of responses received, breaking early.\n")
                        break  # Exit early if majority is reached
                except Exception as exc:
                    print(f"Server {future_to_server[future].id} failed: {str(exc)}\n")
                    pass

            print(f"Collected {len(responses)} responses out of {len(self.servers)} servers.\n requested: {request}\n")
        return responses

    def broadcast_request(self, request, sender_id):
        print(
            f"Broadcasting request with simulated delay up to {self.delay} seconds: {request}\n")
        with ThreadPoolExecutor(max_workers=len(self.servers)) as executor:
            future_to_server = {}
            for server in self.servers:
                future = executor.submit(self.simulated_handle_request, server, request)
                future_to_server[future] = server
            print(f"Tasks submitted for all servers.\n")

            responses = []
            majority_count = (len(self.servers) // 2) + 1
            print(f"Majority count needed: {majority_count}\n")

            for future in as_completed(future_to_server):
                try:
                    response = future.result()
                    if response:
                        responses.append(response)
                        # print(f"Request: {request} from {sender_id}\nReceived valid response from server {future_to_server[future].id}: {response}\n")
                    else:
                        # print(f"Request: {request} from {sender_id}\nNo or invalid response received from server {future_to_server[future].id}\n")
                        pass
                    if len(responses) >= majority_count:
                        # print(f"Majority of responses received, breaking early.\n")
                        break  # Exit early if majority is reached
                except Exception as exc:
                    print(f"Server {future_to_server[future].id} failed: {str(exc)}\n")
                    pass
            print(
                f"Collected {len(responses)} responses out of {len(self.servers)} servers.\n requested: {request}\n Senders ID: {sender_id}\n")
        return responses

    def simulated_handle_request(self, server, request):
        # Simulate network delay
        simulated_delay = random.uniform(0, self.delay)
        print(f"Simulating network delay of {simulated_delay:.2f} seconds for server {server.id}.\n")
        time.sleep(simulated_delay)

        # Simulate fault occurrence
        if self.faults_flag and server in self.faulty_servers:
            print(f"Fault occurred in communication with server {server.id}. Request will not be processed.\n")
            return None  # Simulate a failure that results in no response

        # Handle request if no fault occurred
        response = server.handle_request(request)
        # print(f"Server {server.id} processed request successfully, returning response: {response}\n")
        return response


# Manual Request Testing
def initialize_network(delay, num_servers=None):
    num_clients = 6
    if num_servers is None:
        while True:
            try:
                num_servers = int(input(Fore.BLUE + "Enter the number of servers (minimum 3, maximum 7): "))
                if num_servers < 3 or num_servers > 7:
                    print(Fore.RED + "Please ensure there are at least 3 servers and at most 7 servers.")
                    continue
                print(Style.RESET_ALL)
                break
            except ValueError:
                print(Fore.RED + "Invalid input. Please enter integer values.")
                print(Style.RESET_ALL)

    network = SimulatedNetwork(delay=delay)
    clients = [Node(i + 1, network, ClientState) for i in range(num_clients)]
    servers = [Node(num_clients + i + 1, network, ServerState) for i in range(num_servers)]

    for client in clients:
        network.add_client(client)
    for server in servers:
        network.add_server(server)

    return network, clients + servers, num_servers


def process_commands(nodes):
    command_history = []
    print(Fore.BLUE + "Hello! Welcome to the Safety Test.\n")
    print("Commands:\n"
          "1. <node_id> transform: Transform the role of a node\n"
          "2. <node_id> token_status: Get the status of the server's token ledger\n"
          "3. status: Get the states of all nodes\n"
          "4. help: Display this help message\n"
          "5. close: End the session\n"
          "6. <node_id> getTokens <owner_id>: Client <node_id> sends a getTokens request for <owner_id>'s tokens\n"
          "7. <node_id> pay <new_owner_id> <token_id>: Client <node_id> sends a pay request to transfer token <token_id> to "
          "<new_owner_id>\n")
    print(Style.RESET_ALL)
    while True:
        command = input(Fore.BLUE + "Enter command (or 'close' to end the session): ")
        print(Style.RESET_ALL)
        if command.lower() == 'close':
            break
        elif command.lower() == 'help':
            print(Fore.BLUE + "Commands:\n"
                              "1. <node_id> transform: Transform the role of a node\n"
                              "2. <node_id> token_status: Get the status of the server's token ledger\n"
                              "3. status: Get the states of all nodes\n"
                              "4. help: Display this help message\n"
                              "5. close: End the session\n"
                              "6. <node_id> getTokens <owner_id>: Client <node_id> sends a getTokens request for <owner_id>'s tokens\n"
                              "7. <node_id> pay <new_owner_id> <token_id>: Client <node_id> sends a pay request to transfer token <token_id> to <new_owner_id>\n")
            print(Style.RESET_ALL)
            continue
        elif command.lower() == 'status':
            for node in nodes:
                print(f'Node {node.id}: {type(node.state).__name__}')
            continue
        result = execute_command(command, nodes)
        if result != "Invalid command":
            command_history.append(command)
        print(result)

    return command_history


def execute_command(command, nodes):
    parts = command.split()
    if len(parts) < 2:
        return "Invalid command"

    node_id = int(parts[0])
    action = parts[1]

    if node_id > len(nodes) or node_id < 1:
        return "Invalid node ID"

    node = nodes[node_id - 1]

    if action == 'transform':
        node.transform_role()
        return f"Node {node_id} is now a {type(node.state).__name__}"
    elif action == 'token_status':
        if isinstance(node.state, ClientState):
            return "Invalid action: Clients cannot check token status. Please try again."
        for i in range(60):
            print(Fore.GREEN + f'token ID: {i}, owner ID: {node.state.tokens[i].owner}, version: {node.state.tokens[i].version}')
        return
    elif action == 'getTokens' or action == 'gettokens':
        if len(parts) != 3:
            return "Invalid command for getTokens"
        owner_id = int(parts[2])
        if isinstance(node.state, ServerState):
            return "Invalid action: Servers cannot send getTokens requests. Please try again."
        return str(node.handle_request({'type': 'gettokens', 'owner_id': owner_id}))
    elif action == 'pay':
        if len(parts) != 4:
            return "Invalid command for pay"
        new_owner_id = int(parts[2])
        token_id = int(parts[3])
        if isinstance(node.state, ServerState):
            return "Invalid action: Servers cannot initiate payments. Please try again."
        return str(node.handle_request({'type': 'pay', 'new_owner_id': new_owner_id, 'token_id': token_id}))
    else:
        return "Invalid command"


def rerun_commands(commands, num_servers):
    print(Fore.BLUE + "\nRerunning commands in a fault-free environment:")
    print(Style.RESET_ALL)
    network, nodes, _ = initialize_network(delay=3, num_servers=num_servers)
    network.faults_flag = False
    for command in commands:
        print(Fore.BLUE + f"##########\nCommand: {command}\n##########\n" + Style.RESET_ALL)
        result = execute_command(command, nodes)
        print(Fore.BLUE + f"##########\nCommand: {command} -> Result: {result}\n##########\n" + Style.RESET_ALL)
    print(Style.RESET_ALL)
    print(Back.GREEN + 'Final Node status:' + Style.RESET_ALL)
    for node in nodes:
        print(Fore.GREEN + f'Node {node.id}: {type(node.state).__name__}')
    print(Style.RESET_ALL)
    for node in nodes:
        if isinstance(node.state, ServerState):
            print(Style.RESET_ALL)
            print(Back.GREEN + f'Server {node.id} token status:' + Style.RESET_ALL)
            execute_command(f'{node.id} token_status', nodes)


network, nodes, num_servers = initialize_network(delay=3)
command_history = process_commands(nodes)
network.close_system()
rerun_commands(command_history, num_servers)


# Concurrent Random Automatic Request Testing
def perform_random_tests(nodes, num_requests):
    def run_command(client, target_client, command_type, delay):
        # Delay before sending the request
        time.sleep(delay)

        if command_type == 'pay':
            # First, retrieve owned tokens
            print(Fore.BLUE + f"Client {client.id} is retrieving owned tokens." + Style.RESET_ALL)
            owned_tokens_response = client.handle_request({'type': 'gettokens', 'owner_id': client.id})
            results.append((client.id, {'type': 'gettokens', 'owner_id': client.id}, owned_tokens_response, time.time(), client))
            if owned_tokens_response:
                token = random.choice(owned_tokens_response)
                # Construct the pay command
                command = {'type': 'pay', 'token_id': token['id'], 'new_owner_id': target_client.id}
                print(Fore.BLUE + f"Client {client.id} is paying token {token['id']} to client {target_client.id}." + Style.RESET_ALL)
                response = client.handle_request(command)
            else:
                print(Fore.BLUE + f"Client {client.id} has no tokens to pay with." + Style.RESET_ALL)
                return
        else:
            print(Fore.BLUE + f"Client {client.id} is retrieving tokens owned by client {target_client.id}." + Style.RESET_ALL)
            command = {'type': 'gettokens', 'owner_id': target_client.id}
            response = client.handle_request(command)

        results.append((client.id, command, response, time.time(), client))

    results = []
    clients = [node for node in nodes if isinstance(node.state, ClientState)]
    threads = []
    last_command_time = 0

    for _ in range(num_requests):
        client = random.choice(clients)
        target_client = random.choice([client_node for client_node in clients if client_node.id != client.id])
        command_type = random.choice(['gettokens', 'pay'])
        delay = random.uniform(0, 2)  # Random delay up to 2 seconds
        scheduled_time = last_command_time + delay
        last_command_time = scheduled_time

        thread = threading.Thread(target=run_command, args=(client, target_client, command_type, scheduled_time))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    for result in results:
        print(Fore.BLUE + f"Node {result[0]} with request {result[1]} got response {result[2]} at simulated time {result[3]:.2f}" + Style.RESET_ALL)

    return results


def rerun_random_commands(commands, num_clients, num_servers):
    print(Fore.BLUE + "\nRerunning commands in a fault-free environment:\n" + Style.RESET_ALL)

    # Create a new network with no delay or faults
    new_network = SimulatedNetwork(delay=10)
    new_network.faults_flag = False
    new_clients = [Node(i + 1, new_network, ClientState) for i in range(num_clients)]
    new_servers = [Node(num_clients + i + 1, new_network, ServerState) for i in range(num_servers)]

    # Reassign clients and servers to the new network
    for client in new_clients:
        new_network.add_client(client)
    for server in new_servers:
        new_network.add_server(server)

    results = []
    for _, command, _, _, client in commands:
        # Find the corresponding new client object with the same ID
        new_client = next((nc for nc in new_clients if nc.id == client.id), None)
        if new_client:
            response = new_client.handle_request(command)
            results.append((new_client.id, command, response))

    for result in results:
        print(Fore.BLUE + f"Node {result[0]} with request {result[1]} got response {result[2]}\n" + Style.RESET_ALL)


network, nodes, num_servers = initialize_network(delay=10)
num_clients = 6  # Assuming the number of clients
num_requests = int(input("Enter the number of requests to simulate: "))
commands = perform_random_tests(nodes, num_requests)
network.close_system()
rerun_random_commands(commands, num_clients, num_servers)
